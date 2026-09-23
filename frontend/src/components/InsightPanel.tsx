import { useState } from 'react';
import type { AnalysisResult, PatternInsight, PatternLearning } from '../api/client';
import { analysisApi } from '../api/client';
import { apiError } from '../lib/apiError';
import { renderMarkdown } from '../lib/markdown';
import HelpDot from './HelpDot';
import ModulePlaceholder from './ModulePlaceholder';

const pct = (v: number | null | undefined, digits = 1) =>
  v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(digits)}%`;

const signed = (v: number | null | undefined, digits = 2) =>
  v == null || Number.isNaN(v) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;

function Meter({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="meter" title={hint}>
      <div className="meter-head">
        <span>{label}</span>
        <span className="meter-value">{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </div>
    </div>
  );
}

/** Horizontal bull/bear probability bar. */
function BiasBar({ bull, bear }: { bull: number; bear: number }) {
  const bullPct = Math.max(0, Math.min(1, bull)) * 100;
  const bearPct = Math.max(0, Math.min(1, bear)) * 100;
  const rest = Math.max(0, 100 - bullPct - bearPct);
  return (
    <div className="bias-bar" title="Weighted share of analog matches whose next leg was up vs down">
      <div className="bias-seg bull" style={{ width: `${bullPct}%` }} />
      <div className="bias-seg rest" style={{ width: `${rest}%` }} />
      <div className="bias-seg bear" style={{ width: `${bearPct}%` }} />
      <span className="bias-label bull">{(bull * 100).toFixed(0)}% bull</span>
      <span className="bias-label bear">{(bear * 100).toFixed(0)}% bear</span>
    </div>
  );
}

/** Expected value with an interquartile-style range band. */
function RangeStat({ label, expected, p25, p75, sub }: {
  label: React.ReactNode; expected: number; p25: number | null; p75: number | null; sub?: string;
}) {
  const hasRange = p25 != null && p75 != null;
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value" style={{ color: expected >= 0 ? 'var(--up)' : 'var(--down)' }}>{signed(expected)}</div>
      <div className="sub">
        {hasRange ? <>range {signed(p25!)} … {signed(p75!)}</> : 'range n/a'}
        {sub ? <> · {sub}</> : null}
      </div>
    </div>
  );
}

function biasColor(bias: string): string {
  return bias === 'bullish' ? 'var(--up)' : bias === 'bearish' ? 'var(--down)' : 'var(--text-muted)';
}

function PatternCard({ pi, learning }: { pi: PatternInsight; learning: PatternLearning | null }) {
  const [showMatches, setShowMatches] = useState(false);
  return (
    <div className="card">
      <div className="card-head">
        <h3 style={{ margin: 0 }}>Pattern recognition</h3>
        <span className="badge" style={{ color: biasColor(pi.dominant_bias), borderColor: biasColor(pi.dominant_bias) }}>
          {pi.dominant_bias}
        </span>
      </div>

      <BiasBar bull={pi.bullish_probability} bear={pi.bearish_probability} />

      <div className="tile-grid">
        <RangeStat
          label={<>Next leg (expected)<HelpDot>The engine's best guess for the swing that hasn't finished yet, with the typical range (25th–75th percentile of what happened after similar setups).</HelpDot></>}
          expected={pi.expected_next_change_pct}
          p25={pi.next_change_p25_pct}
          p75={pi.next_change_p75_pct}
          sub={`~${Math.round(pi.expected_next_duration_bars)} bars`}
        />
        <RangeStat
          label={<>{pi.forecast_horizon}-leg horizon<HelpDot>The combined move expected over the next {pi.forecast_horizon} swings — a broader, more meaningful forecast than a single swing.</HelpDot></>}
          expected={pi.expected_horizon_change_pct}
          p25={pi.horizon_change_p25_pct}
          p75={pi.horizon_change_p75_pct}
        />
        <div className="tile">
          <div className="label">
            Analog matches
            <HelpDot>How many moments in history looked like right now (same recent pattern of swings) and were used for the forecast.</HelpDot>
          </div>
          <div className="value">{pi.matches_used}</div>
          <div className="sub">length {pi.pattern_length} · horizon {pi.forecast_horizon}</div>
        </div>
        <div className="tile">
          <div className="label">
            Next-move error (MAE)
            <HelpDot>On past calls, how far off the size guess was on average (in percentage points). Smaller = sharper sizing.</HelpDot>
          </div>
          <div className="value">{learning?.mean_abs_error_next_change_pct != null ? `${learning.mean_abs_error_next_change_pct.toFixed(2)}pp` : '—'}</div>
          <div className="sub">expected vs realized, in-run</div>
        </div>
      </div>

      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.2rem 0 0.7rem' }}>{pi.summary}</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem 1.2rem' }}>
        <Meter label="Base confidence" value={pi.base_confidence} hint="Analog agreement + match similarity" />
        <Meter label="Adaptive confidence" value={pi.adaptive_confidence} hint="Blended with persisted hit-rate memory" />
      </div>

      {learning && (
        <div className="learn-box">
          <div className="learn-title">
            Walk-forward validation
            <HelpDot>The pattern engine re-predicted at many points in history using only data it would have had at the time, then checked what actually happened. These are those scorecards.</HelpDot>
            <span className="badge">{learning.total_backtests} backtests</span>
            {learning.regime_label && <span className="badge">{learning.regime_label}</span>}
          </div>
          <table className="mini-table">
            <tbody>
              <tr>
                <td>Horizon direction hit rate
                  <HelpDot>How often the multi-swing forecast got the direction right — this is the genuinely uncertain call and the one that matters.</HelpDot>
                </td>
                <td className="hl">{pct(learning.horizon_hit_rate)}</td>
                <td className="muted">the genuinely uncertain call</td>
              </tr>
              <tr>
                <td>Next-leg direction hit rate
                  <HelpDot>How often the very next swing's direction was called right. Zigzag swings always alternate, so "guess the opposite of the last swing" (the reversion null) is nearly perfect here — that's why this row is read against its null, not against 100%.</HelpDot>
                </td>
                <td>{pct(learning.direction_hit_rate)}</td>
                <td className="muted">vs reversion null {pct(learning.baseline_reversion_hit_rate)} · majority {pct(learning.baseline_majority_hit_rate)}</td>
              </tr>
              <tr>
                <td>Persisted memory
                  <HelpDot>What the engine remembers from previous runs about patterns like this one (deduplicated, so re-runs don't inflate it).</HelpDot>
                </td>
                <td>{pct(learning.persistent_direction_hit_rate)} dir · {pct(learning.persistent_horizon_hit_rate)} horiz</td>
                <td className="muted">{learning.persistent_samples} unique outcomes{learning.regime_samples ? ` · ${learning.regime_samples} in regime` : ''}</td>
              </tr>
              {learning.median_next_change_pct != null && (
                <tr>
                  <td>Memory: median next move
                    <HelpDot>Across everything remembered about this pattern, the typical next move and its typical spread.</HelpDot>
                  </td>
                  <td className="hl">{signed(learning.median_next_change_pct)} <span className="muted">[{signed(learning.p25_next_change_pct)}, {signed(learning.p75_next_change_pct)}]</span></td>
                  <td className="muted">from persisted outcomes</td>
                </tr>
              )}
            </tbody>
          </table>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-faint)', marginTop: '0.4rem' }}>{learning.learning_note}</div>
        </div>
      )}

      <div style={{ marginTop: '0.6rem' }}>
        <button className="btn btn-secondary" style={{ fontSize: '0.75rem', padding: '0.3rem 0.7rem' }} onClick={() => setShowMatches(!showMatches)}>
          {showMatches ? 'Hide' : 'Show'} closest analogs ({pi.matches.length})
        </button>
      </div>
      {showMatches && pi.matches.length > 0 && (
        <div style={{ overflowX: 'auto', marginTop: '0.5rem' }}>
          <table className="data-table">
            <thead>
              <tr><th>Leg</th><th>Similarity</th><th>Next dir</th><th>Next move</th><th>Horizon</th><th>Signature</th></tr>
            </thead>
            <tbody>
              {pi.matches.map((m) => (
                <tr key={m.anchor_leg_id}>
                  <td>#{m.anchor_leg_id}</td>
                  <td>{(m.similarity_score * 100).toFixed(0)}%</td>
                  <td className={m.next_direction === 'up' ? 'dir-up' : 'dir-down'}>{m.next_direction === 'up' ? '▲' : '▼'}</td>
                  <td className={m.next_change_pct >= 0 ? 'dir-up' : 'dir-down'}>{signed(m.next_change_pct)}</td>
                  <td className={m.horizon_change_pct >= 0 ? 'dir-up' : 'dir-down'}>{signed(m.horizon_change_pct)}</td>
                  <td style={{ fontSize: '0.68rem', color: 'var(--text-faint)' }}>{m.match_signature}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ fontSize: '0.68rem', color: 'var(--text-faint)', marginTop: '0.6rem' }}>
        Signature <code style={{ fontSize: '0.66rem' }}>{pi.pattern_signature}</code>
      </div>
    </div>
  );
}

export default function InsightPanel({ result, onRerun }: { result: AnalysisResult; onRerun?: (config: Record<string, unknown>) => void }) {
  const [aiText, setAiText] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState('');

  async function fetchInsight() {
    setAiBusy(true);
    setAiError('');
    try {
      const res = await analysisApi.insight();
      setAiText(res.data.insight);
    } catch (err) {
      setAiError(apiError(err, 'The AI gateway could not be reached.'));
    } finally {
      setAiBusy(false);
    }
  }

  // One-click "Enable & re-run": patch config, run analysis with it.
  const [enabling, setEnabling] = useState(false);
  async function enableAndRun(fields: Record<string, unknown>) {
    if (enabling) return;
    setEnabling(true);
    try {
      await analysisApi.analyze({ config: fields });
      onRerun?.(fields);
    } catch (_err) {
      /* the dashboard error banner covers analyze failures on main runs */
    } finally {
      setEnabling(false);
    }
  }

  const pi = result.pattern_insight;
  const learning = result.pattern_learning;
  return (
    <div>
      {/* Provider-neutral AI read */}
      <div className="card">
        <div className="card-head">
          <h3 style={{ margin: 0 }}>AI read of the current screen</h3>
          <span className="badge">not financial advice</span>
        </div>
        {!aiText && !aiBusy && (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.3rem 0 0.6rem' }}>
            Generate a calm, four-part read of the current analysis.
          </p>
        )}
        {aiError && <div className="error-banner">{aiError}</div>}
        {aiText && (
          <div className="md-body" style={{ fontSize: '0.85rem' }}
            dangerouslySetInnerHTML={{ __html: renderMarkdown(aiText) }} />
        )}
        <button className="btn btn-secondary" onClick={fetchInsight} disabled={aiBusy} style={{ marginTop: '0.5rem' }}>
          {aiBusy ? 'Thinking…' : aiText ? 'Refresh read' : 'Generate read'}
        </button>
      </div>

      {pi ? (
        <PatternCard pi={pi} learning={learning} />
      ) : (
        <ModulePlaceholder
          title="Pattern recognition"
          hint="Match the recent leg sequence against history, with walk-forward validation and honest naive baselines."
          fields={{ enable_pattern_recognition: true }}
          onEnable={enableAndRun}
          busy={enabling}
        />
      )}

    </div>
  );
}
