/**
 * Cross-asset module tab: per-asset comparison charts + the stat rows.
 *
 * Charts (Plotly): top subplot = BTC and the asset rebased to 100 so the
 * shapes are comparable; bottom subplot = the rolling return correlation.
 */
import { useEffect, useRef, useState } from 'react';
import type { AnalysisResult, AssetCorrelation } from '../api/client';
import ModulePlaceholder from './ModulePlaceholder';
import HelpDot from './HelpDot';

const signed = (v: number | null | undefined, digits = 2) =>
  v == null || Number.isNaN(v) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;

function corrTone(v: number | null) {
  if (v == null) return 'var(--text-muted)';
  return v >= 0.5 ? 'var(--up)' : v <= -0.5 ? 'var(--down)' : 'var(--text-secondary)';
}

function CorrelationChart({ name, c }: { name: string; c: AssetCorrelation }) {
  const el = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = el.current;
    if (!node || !window.Plotly || c.observations.length === 0) return;

    const obs = c.observations;
    const hasRolling = obs.some(o => o.rolling_return_correlation != null);

    const data: Array<Record<string, unknown>> = [
      {
        type: 'scatter', mode: 'lines', name: `BTC (rebased)`,
        x: obs.map(o => o.timestamp), y: obs.map(o => o.btc_normalized),
        line: { color: '#f7931a', width: 2 },
      },
      {
        type: 'scatter', mode: 'lines', name: `${c.asset_name} (rebased)`,
        x: obs.map(o => o.timestamp), y: obs.map(o => o.asset_normalized),
        line: { color: '#3b82f6', width: 2, dash: 'dot' },
      },
    ];
    if (hasRolling) {
      data.push({
        type: 'scatter', mode: 'lines', name: `rolling corr (${c.rolling_window_days}d)`,
        x: obs.map(o => o.timestamp),
        y: obs.map(o => o.rolling_return_correlation),
        line: { color: '#8791a3', width: 1.5 },
        yaxis: 'y2',
        hovertemplate: 'rolling corr %{y:.2f}<extra></extra>',
      });
    }

    const layout = {
      margin: { l: 50, r: 15, t: 8, b: 30 },
      height: 380,
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#b6bfcd', size: 11 },
      showlegend: true,
      legend: { orientation: 'h', y: 1.12, x: 0 },
      hovermode: 'x unified',
      xaxis: { gridcolor: '#232b38' },
      yaxis: {
        gridcolor: '#232b38', title: { text: 'rebased to 100', font: { size: 10 } },
        domain: hasRolling ? [0.34, 1] : [0, 1],
      },
      ...(hasRolling ? {
        yaxis2: {
          gridcolor: '#232b38', range: [-1.05, 1.05], domain: [0, 0.24],
          title: { text: 'rolling corr', font: { size: 10 } },
          zerolinecolor: '#5b6474',
        },
      } : {}),
    };

    window.Plotly.react(node, data, layout, { responsive: true, displaylogo: false });
    return () => { if (node) window.Plotly.purge(node); };
  }, [c, name]);

  return <div ref={el} />;
}

export default function CorrelationPanel({
  result, onRerun,
}: {
  result: AnalysisResult;
  onRerun: (config: Record<string, unknown>) => void;
}) {
  const [enabling, setEnabling] = useState(false);
  async function enableAndRun(fields: Record<string, unknown>) {
    if (enabling) return;
    setEnabling(true);
    try {
      await import('../api/client').then(m => m.analysisApi.analyze({ config: fields }));
      onRerun(fields);
    } catch (_err) { /* main banner covers analyze failures */ }
    finally { setEnabling(false); }
  }

  const correlations = result.correlations || {};
  const errors = result.correlation_errors || {};
  const names = Object.keys(correlations);
  const [active, setActive] = useState<string>(names[0] || '');

  const currentName = names.includes(active) ? active : names[0];
  const current = currentName ? correlations[currentName] : null;

  // Nothing fetched and nothing attempted: modules are off entirely.
  if (names.length === 0 && Object.keys(errors).length === 0) {
    return (
      <ModulePlaceholder
        title="Cross-asset correlations"
        hint="Compare BTC with gold and the Nasdaq over the same window: rebased price comparison, rolling correlation, beta, and relative strength."
        fields={{ enable_gold_correlation_analysis: true, enable_nasdaq_correlation_analysis: true }}
        onEnable={enableAndRun}
        busy={enabling}
      />
    );
  }

  return (
    <div>
      <div className="card">
        <div className="card-head">
          <h3 style={{ margin: 0 }}>
            Cross-asset correlations
            <HelpDot>Does BTC move together with other big markets? The lines are both rebased to 100 at the start, so their shapes are directly comparable; the lower strip shows whether the day-to-day correlation is strengthening or fading.</HelpDot>
          </h3>
          <div className="chart-toggles">
            {names.map(n => (
              <button
                key={n}
                className={`chart-toggle${n === currentName ? ' active' : ''}`}
                onClick={() => setActive(n)}
              >
                {correlations[n].asset_name}
              </button>
            ))}
          </div>
        </div>

        {current && (
          <>
            <div className="corr-stats" style={{ marginBottom: '0.4rem' }}>
              <span>returns <strong style={{ color: corrTone(current.return_correlation) }}>{current.return_correlation != null ? current.return_correlation.toFixed(2) : '—'}</strong></span>
              <span>price <strong style={{ color: corrTone(current.price_correlation) }}>{current.price_correlation != null ? current.price_correlation.toFixed(2) : '—'}</strong></span>
              <span>β <strong>{current.beta_to_asset != null ? current.beta_to_asset.toFixed(2) : '—'}</strong></span>
              <span>rolling <strong style={{ color: corrTone(current.latest_rolling_correlation) }}>{current.latest_rolling_correlation != null ? current.latest_rolling_correlation.toFixed(2) : '—'}</strong></span>
              <span>BTC rel. <strong className={((current.latest_relative_strength_pct ?? 0) >= 0) ? 'dir-up' : 'dir-down'}>{signed(current.latest_relative_strength_pct)}</strong></span>
            </div>
            <CorrelationChart name={currentName} c={current} />
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
              {current.overlap_points} aligned daily points · {current.summary}
            </div>
          </>
        )}

        {Object.entries(errors).map(([name, err]) => (
          <div key={name} className="corr-row" style={{ marginTop: '0.4rem' }}>
            <div className="corr-name" style={{ textTransform: 'capitalize' }}>{name}</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--warning)' }}>Fetch failed: {err}</div>
          </div>
        ))}

        {!names.includes('oil') && !errors['oil'] && (
          <button
            className="btn btn-secondary" style={{ fontSize: '0.72rem', marginTop: '0.5rem' }}
            disabled={enabling}
            onClick={() => enableAndRun({ enable_oil_correlation_analysis: true })}
          >
            {enabling ? 'Running…' : '+ Add oil (CL=F)'}
          </button>
        )}
      </div>
    </div>
  );
}
