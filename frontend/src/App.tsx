import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { AnalysisResult, AppConfig, Options } from './api/client';
import { analysisApi } from './api/client';
import { apiError } from './lib/apiError';
import ControlPanel from './components/ControlPanel';
import PriceChart from './components/PriceChart';
import SummaryTiles from './components/SummaryTiles';
import DecisionCard from './components/DecisionCard';
import { LegsTable, PivotsTable } from './components/LegsTable';
import InsightPanel from './components/InsightPanel';
import CorrelationPanel from './components/CorrelationPanel';
import MoonPanel from './components/MoonPanel';
import AgentPanel from './components/AgentPanel';
import StructureDiscoveries from './components/StructureDiscoveries';
import DashboardSection from './components/DashboardSection';

type Tab = 'legs' | 'pivots' | 'crossasset' | 'moon' | 'insights';

// ── Layout customization ───────────────────────────────────────────────
// Module ids in the main column; order + visibility persist to localStorage.

type ModuleId = 'summary' | 'decision' | 'structures' | 'chart' | 'tables';
const DEFAULT_ORDER: ModuleId[] = ['summary', 'decision', 'structures', 'chart', 'tables'];
const MODULE_TITLES: Record<ModuleId, string> = {
  summary: 'Summary tiles',
  decision: 'Decision engine',
  structures: 'Market structures',
  chart: 'Price chart',
  tables: 'Data & module tabs',
};

const LAYOUT_KEY = 'btc-dash-layout-v1';
const SIDEBAR_KEY = 'btc-sidebar-hidden-v1';

function loadLayout(): { order: ModuleId[]; hidden: ModuleId[] } {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { order: ModuleId[]; hidden: ModuleId[] };
      const order = DEFAULT_ORDER.filter(m => !parsed.order?.includes(m)).concat(
        (parsed.order || []).filter(m => DEFAULT_ORDER.includes(m)),
      );
      const hidden = (parsed.hidden || []).filter(m => DEFAULT_ORDER.includes(m));
      return { order, hidden };
    }
  } catch { /* corrupt layout falls back to defaults */ }
  return { order: DEFAULT_ORDER, hidden: [] };
}

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<Tab>('legs');
  const [exportFiles, setExportFiles] = useState<Record<string, string>>({});
  const [exportMsg, setExportMsg] = useState('');
  const [sidebarHidden, setSidebarHidden] = useState(() => localStorage.getItem(SIDEBAR_KEY) === '1');
  const [customizing, setCustomizing] = useState(false);
  const [layout, setLayout] = useState(loadLayout);
  const bootedRef = useRef(false);
  const configRef = useRef<AppConfig | null>(null);
  configRef.current = config;

  useEffect(() => { localStorage.setItem(SIDEBAR_KEY, sidebarHidden ? '1' : '0'); }, [sidebarHidden]);
  useEffect(() => { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); }, [layout]);

  const reorderModule = useCallback((dragged: ModuleId, target: ModuleId) => {
    setLayout(prev => {
      const order = prev.order.filter(m => m !== dragged);
      order.splice(order.indexOf(target), 0, dragged);
      return { ...prev, order };
    });
  }, []);
  const moveModule = useCallback((id: ModuleId, delta: number) => {
    setLayout(prev => {
      const order = [...prev.order];
      const i = order.indexOf(id);
      const j = i + delta;
      if (i < 0 || j < 0 || j >= order.length) return prev;
      [order[i], order[j]] = [order[j], order[i]];
      return { ...prev, order };
    });
  }, []);
  const toggleModuleHidden = useCallback((id: ModuleId) => {
    setLayout(prev => ({
      ...prev,
      hidden: prev.hidden.includes(id) ? prev.hidden.filter(m => m !== id) : [...prev.hidden, id],
    }));
  }, []);
  const resetLayout = useCallback(() => setLayout({ order: DEFAULT_ORDER, hidden: [] }), []);

  // Initial load: options, server config, and any existing result — then
  // auto-run once so a fresh visit lands on a populated dashboard.
  useEffect(() => {
    analysisApi.options().then(res => setOptions(res.data)).catch(() => {});
    analysisApi.getConfig()
      .then(res => setConfig(res.data))
      .catch(() => {});
    analysisApi.result()
      .then(res => setResult(res.data))
      .catch(() => {
        if (!bootedRef.current) {
          bootedRef.current = true;
          // Wait for the config to load, then auto-run once.
          const wait = setInterval(() => {
            if (configRef.current) {
              clearInterval(wait);
              run();
            }
          }, 150);
          setTimeout(() => clearInterval(wait), 15000);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onConfigChange = useCallback((fields: Partial<AppConfig>) => {
    setConfig(prev => (prev ? { ...prev, ...fields } : prev));
  }, []);

  const run = useCallback(async () => {
    const cfg = configRef.current;
    if (!cfg) return;
    setRunning(true);
    setError('');
    try {
      const res = await analysisApi.analyze({ config: cfg });
      setResult(res.data);
    } catch (err) {
      setError(apiError(err, 'Analysis failed.'));
    } finally {
      setRunning(false);
    }
  }, []);

  // "R" runs the analysis (unless typing in a field)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'SELECT' || target.tagName === 'TEXTAREA') return;
      if (e.key === 'r' || e.key === 'R') run();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [run]);

  // Called by the AgentPanel after a confirmed write (re-run / config change /
  // export) so the dashboard reflects what the agent did.
  const refreshFromServer = useCallback(() => {
    analysisApi.getConfig().then(res => setConfig(res.data)).catch(() => {});
    analysisApi.result().then(res => setResult(res.data)).catch(() => {});
  }, []);

  async function doExport() {
    setExportMsg('');
    setExportFiles({});
    try {
      const res = await analysisApi.exportData();
      setExportFiles(res.data.files);
      setExportMsg(`Exported ${Object.keys(res.data.files).length} file(s):`);
    } catch (err) {
      setExportMsg(apiError(err, 'Export failed.'));
    }
  }

  const meta = result?.metadata;
  const forming = result?.forming_leg;
  const lastPrice = forming?.end_price ?? result?.legs.at(-1)?.end_price;

  // The main column, in the user's chosen order. Rendered via a memo so the
  // section content isn't rebuilt on every customize-mode toggle.
  const section = useMemo(() => {
    const tables = (
      <>
        <div className="tab-bar">
          <button className={tab === 'legs' ? 'active' : ''} onClick={() => setTab('legs')}>
            Legs ({result?.legs.length ?? 0})
          </button>
          <button className={tab === 'pivots' ? 'active' : ''} onClick={() => setTab('pivots')}>
            Pivots ({result?.pivots.length ?? 0})
          </button>
          <button className={tab === 'crossasset' ? 'active' : ''} onClick={() => setTab('crossasset')}>
            Cross-asset{result && Object.keys(result.correlations || {}).length > 0 ? ` (${Object.keys(result.correlations).length})` : ''}
          </button>
          <button className={tab === 'moon' ? 'active' : ''} onClick={() => setTab('moon')}>
            Moon{result?.moon_phase_insight ? ` (${result.moon_phase_insight.total_events})` : ''}
          </button>
          <button className={tab === 'insights' ? 'active' : ''} onClick={() => setTab('insights')}>
            Insights
          </button>
        </div>

        {!result ? (
          <div className="card" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Run an analysis to populate the tabs.</div>
        ) : (
          <>
            {tab === 'legs' && <div className="card"><LegsTable legs={result.legs} /></div>}
            {tab === 'pivots' && <div className="card"><PivotsTable pivots={result.pivots} /></div>}
            {tab === 'crossasset' && <CorrelationPanel result={result} onRerun={refreshFromServer} />}
            {tab === 'moon' && <MoonPanel result={result} onRerun={refreshFromServer} />}
            {tab === 'insights' && <InsightPanel result={result} onRerun={refreshFromServer} />}
          </>
        )}
      </>
    );

    return {
      summary: result
        ? <SummaryTiles summary={result.summary} metadata={result.metadata} />
        : <div className="card" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Run an analysis to see summary statistics.</div>,
      decision: result?.decision_brief
        ? <DecisionCard brief={result.decision_brief} />
        : <div className="card" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Decision engine output appears here after a run.</div>,
      structures: <StructureDiscoveries discoveries={result?.structure_discoveries || []} />,
      chart: result
        ? <PriceChart result={result} />
        : <div className="card" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>The chart appears after the first analysis.</div>,
      tables,
    } as Record<ModuleId, ReactNode>;
  }, [result, tab, refreshFromServer]);

  const visible = layout.order.filter(m => !layout.hidden.includes(m));

  return (
    <div className={`app-shell${sidebarHidden ? ' sidebar-hidden' : ''}`}>
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
          <button
            className="hamburger"
            title={sidebarHidden ? 'Show controls' : 'Hide controls'}
            onClick={() => setSidebarHidden(!sidebarHidden)}
          >
            ☰
          </button>
          <span style={{ fontSize: '1.05rem', fontWeight: 800 }}>
            ₿ Swing Cycle Tracker
          </span>
          {meta && (
            <span className="badge">
              {meta.symbol} · {meta.timeframe} · {meta.pivot_method}
            </span>
          )}
          {lastPrice != null && (
            <span className="price-chip">
              ${lastPrice.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              {forming && (
                <span className={forming.percent_change >= 0 ? 'dir-up' : 'dir-down'}>
                  {' '}{forming.percent_change >= 0 ? '+' : ''}{forming.percent_change.toFixed(2)}%
                </span>
              )}
            </span>
          )}
          {running && <span className="spinner" title="Analysis running…" />}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          {meta && (
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }} title="Analysis window (UTC-ish server timestamps)">
              {new Date(meta.start_date).toLocaleDateString()} → {new Date(meta.end_date).toLocaleDateString()}
            </span>
          )}
          {customizing && (
            <>
              {layout.hidden.length > 0 && (
                <span className="muted" style={{ fontSize: '0.7rem' }}>{layout.hidden.length} hidden</span>
              )}
              <button className="btn btn-secondary" style={{ fontSize: '0.72rem' }} onClick={resetLayout}>
                Reset layout
              </button>
            </>
          )}
          <button
            className={`btn ${customizing ? 'btn-primary' : 'btn-secondary'}`}
            style={{ fontSize: '0.72rem' }}
            title="Rearrange or hide the dashboard modules (drag the handles)"
            onClick={() => setCustomizing(!customizing)}
          >
            {customizing ? '✓ Done' : '⠿ Customize'}
          </button>
          <button className="btn btn-secondary" onClick={doExport} disabled={!result}>
            Export CSV/JSON
          </button>
        </div>
      </header>

      {exportMsg && (
        <div className="export-strip">
          <span style={{ color: 'var(--text-muted)' }}>{exportMsg}</span>
          {Object.entries(exportFiles).map(([kind, path]) => (
            <a key={kind} className="export-link" href={`/api/export/download?path=${encodeURIComponent(path)}`}>
              {kind} ↓
            </a>
          ))}
        </div>
      )}

      <div className="app-body">
        {!sidebarHidden && (
          <aside className="sidebar">
            {config ? (
              <ControlPanel
                config={config}
                options={options}
                running={running}
                onChange={onConfigChange}
                onRun={run}
              />
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                <span className="spinner" /> Loading configuration…
              </div>
            )}
          </aside>
        )}

        <main className="main">
          {error && <div className="error-banner">{error}</div>}

          {running && !result && (
            <div className="empty-state">
              <span className="spinner" style={{ width: 24, height: 24 }} />
              <span className="empty-title">Running analysis…</span>
              <span className="empty-sub">Fetching candles, detecting pivots, building legs.</span>
            </div>
          )}

          {!running && !result && !customizing && (
            <div className="empty-state">
              <span className="empty-icon">📈</span>
              <span className="empty-title">No analysis yet</span>
              <span className="empty-sub">
                Pick a symbol, timeframe and lookback in the sidebar and hit “Run analysis” —
                or just ask the agent in the bottom-right corner.
              </span>
            </div>
          )}

          {(result || customizing) && visible.map(id => (
            <DashboardSection
              key={id}
              id={id}
              title={MODULE_TITLES[id]}
              customizing={customizing}
              onHide={toggleModuleHidden}
              onReorder={reorderModule}
              onMove={moveModule}
            >
              {section[id]}
            </DashboardSection>
          ))}

          {customizing && layout.hidden.length > 0 && (
            <div className="card" style={{ borderStyle: 'dashed' }}>
              <h3 style={{ margin: '0 0 0.5rem' }}>Hidden modules</h3>
              {layout.hidden.map(id => (
                <button
                  key={id}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.74rem', marginRight: '0.4rem' }}
                  onClick={() => toggleModuleHidden(id)}
                >
                  + Show {MODULE_TITLES[id]}
                </button>
              ))}
            </div>
          )}
        </main>
      </div>

      <AgentPanel onDataChanged={refreshFromServer} />
    </div>
  );
}
