/**
 * Moon-phase module tab: the price line with major-phase markers and the
 * per-phase statistics. Entertainment module — deliberately excluded from
 * the decision engine, and labelled as such.
 */
import { useEffect, useRef, useState } from 'react';
import type { AnalysisResult } from '../api/client';
import ModulePlaceholder from './ModulePlaceholder';
import HelpDot from './HelpDot';

const PHASE_STYLE: Record<string, { color: string; symbol: string }> = {
  new: { color: '#8791a3', symbol: 'circle' },
  first_quarter: { color: '#3b82f6', symbol: 'triangle-up' },
  full: { color: '#f7931a', symbol: 'circle' },
  last_quarter: { color: '#9b59b6', symbol: 'triangle-down' },
};

function MoonChart({ result }: { result: AnalysisResult }) {
  const el = useRef<HTMLDivElement>(null);
  const moon = result.moon_phase_insight;

  useEffect(() => {
    const node = el.current;
    if (!node || !window.Plotly || !moon) return;

    const candles = result.candles || [];
    const closes = {
      x: candles.map(c => c.t),
      y: candles.map(c => c.c),
    };

    const data: Array<Record<string, unknown>> = [
      {
        type: 'scatter', mode: 'lines', name: `${result.metadata.symbol} close`,
        x: closes.x, y: closes.y,
        line: { color: '#b6bfcd', width: 1.5 },
        hovertemplate: '$%{y:,.0f}<extra></extra>',
      },
    ];
    const shapes: Array<Record<string, unknown>> = [];

    for (const ev of moon.events) {
      const style = PHASE_STYLE[ev.phase_code] || { color: '#8791a3', symbol: 'circle' };
      shapes.push({
        type: 'line', xref: 'x', x0: ev.timestamp, x1: ev.timestamp,
        yref: 'paper', y0: 0, y1: 1,
        line: { color: style.color, width: 1, dash: 'dot' },
        opacity: 0.55,
      });
      const parts = [ev.phase_name];
      if (ev.nearest_pivot_type) parts.push(`nearest swing: ${ev.nearest_pivot_type.replace('swing_', '')} ${ev.hours_to_nearest_pivot != null ? `(${ev.hours_to_nearest_pivot.toFixed(1)}h away)` : ''}`);
      if (ev.aligned_within_window) parts.push('within alignment window');
      if (ev.next_leg_direction) parts.push(`next leg: ${ev.next_leg_direction} ${ev.next_leg_percent_change != null ? `${ev.next_leg_percent_change >= 0 ? '+' : ''}${ev.next_leg_percent_change.toFixed(2)}%` : ''}`);
      data.push({
        type: 'scatter', mode: 'markers', name: ev.phase_name,
        x: [ev.timestamp],
        y: [candles.length ? candles[Math.min(candles.length - 1, Math.max(0, candles.findIndex(c => c.t >= ev.timestamp)))].c : 0],
        marker: {
          symbol: style.symbol, size: ev.aligned_within_window ? 11 : 8,
          color: style.color,
          line: ev.aligned_within_window ? { color: '#ffffff', width: 1.5 } : undefined,
        },
        hoverinfo: 'text',
        text: parts.join(' · '),
        showlegend: false,
      });
    }

    const layout = {
      margin: { l: 55, r: 15, t: 8, b: 30 },
      height: 400,
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#b6bfcd', size: 11 },
      xaxis: { gridcolor: '#232b38', rangeslider: { visible: false } },
      yaxis: { gridcolor: '#232b38', tickprefix: '$' },
      legend: { orientation: 'h', y: 1.1, x: 0 },
      hovermode: 'closest',
      shapes,
    };

    window.Plotly.react(node, data, layout, { responsive: true, displaylogo: false });
    return () => { if (node) window.Plotly.purge(node); };
  }, [result, moon]);

  return <div ref={el} />;
}

function PhaseBars({ moon }: { moon: NonNullable<AnalysisResult['moon_phase_insight']> }) {
  const el = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = el.current;
    if (!node || !window.Plotly) return;
    const stats = moon.phase_stats;
    if (!stats.length) return;

    const data = [
      {
        type: 'bar', name: 'swings landed near phase',
        x: stats.map(s => s.phase_name), y: stats.map(s => s.alignment_rate * 100),
        marker: { color: '#3b82f6' },
        hovertemplate: '%{x}: %{y:.0f}% of phases landed near a swing<extra></extra>',
      },
      {
        type: 'bar', name: 'next leg was up',
        x: stats.map(s => s.phase_name), y: stats.map(s => s.bullish_next_leg_rate * 100),
        marker: { color: '#2ecc71' },
        hovertemplate: '%{x}: %{y:.0f}% of next legs were up<extra></extra>',
      },
    ];
    const layout = {
      margin: { l: 40, r: 10, t: 8, b: 30 },
      height: 230,
      barmode: 'group',
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#b6bfcd', size: 10 },
      xaxis: { gridcolor: '#232b38' },
      yaxis: { gridcolor: '#232b38', ticksuffix: '%', range: [0, 100] },
      legend: { orientation: 'h', y: 1.2, x: 0, font: { size: 9 } },
    };
    window.Plotly.react(node, data, layout, { responsive: true, displaylogo: false });
    return () => { if (node) window.Plotly.purge(node); };
  }, [moon]);

  return <div ref={el} />;
}

export default function MoonPanel({
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

  const moon = result.moon_phase_insight;

  if (!moon) {
    return (
      <ModulePlaceholder
        title="Moon phase"
        hint="Lunar cycles vs swing timing — price chart with phase markers, alignment stats, and per-phase behaviour. Entertainment only; deliberately excluded from the decision engine."
        fields={{ enable_moon_phase_analysis: true }}
        onEnable={enableAndRun}
        busy={enabling}
      />
    );
  }

  const pct = (v: number | null | undefined) => v == null ? '—' : `${(v * 100).toFixed(0)}%`;

  return (
    <div>
      <div className="card">
        <div className="card-head">
          <h3 style={{ margin: 0 }}>
            Moon phases on price
            <HelpDot>Vertical dotted lines mark the four major phases (new/first quarter/full/last quarter). Outlined markers mean the phase landed inside the swing-alignment window. Hover a marker for details.</HelpDot>
          </h3>
          <span className="badge">entertainment · not in the decision</span>
        </div>
        <div className="tile-grid" style={{ marginBottom: '0.4rem' }}>
          <div className="tile">
            <div className="label">Pivot alignment
              <HelpDot>How often a major moon phase landed close to a swing turning point — within the matching window shown below.</HelpDot>
            </div>
            <div className="value">{pct(moon.alignment_rate)}</div>
            <div className="sub">{moon.aligned_events}/{moon.total_events} events within {moon.phase_window_hours}h</div>
          </div>
          <div className="tile">
            <div className="label">Avg hours to pivot</div>
            <div className="value">{moon.avg_hours_to_pivot != null ? moon.avg_hours_to_pivot.toFixed(1) : '—'}</div>
            <div className="sub">phase → nearest swing</div>
          </div>
          <div className="tile">
            <div className="label">Strongest phase</div>
            <div className="value" style={{ fontSize: '0.9rem' }}>{moon.strongest_phase ?? '—'}</div>
            <div className="sub">{moon.strongest_bias ?? '—'} bias {pct(moon.strongest_bias_score)}</div>
          </div>
        </div>
        <MoonChart result={result} />
      </div>

      <div className="card">
        <h3>
          Per-phase behaviour
          <HelpDot>For each major phase: how often swings landed near it, and how often the swing that followed pointed up. Tiny samples — read as trivia.</HelpDot>
        </h3>
        <PhaseBars moon={moon} />
        <div style={{ overflowX: 'auto', marginTop: '0.5rem' }}>
          <table className="data-table">
            <thead><tr><th>Phase</th><th>Events</th><th>Aligned</th><th>High rate</th><th>Low rate</th><th>Bull next</th><th>Bear next</th></tr></thead>
            <tbody>
              {moon.phase_stats.map(p => (
                <tr key={p.phase_name}>
                  <td>{p.phase_name}</td>
                  <td>{p.occurrences}</td>
                  <td>{pct(p.alignment_rate)}</td>
                  <td>{pct(p.swing_high_rate)}</td>
                  <td>{pct(p.swing_low_rate)}</td>
                  <td>{pct(p.bullish_next_leg_rate)}</td>
                  <td>{pct(p.bearish_next_leg_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>{moon.summary}</div>
      </div>
    </div>
  );
}
