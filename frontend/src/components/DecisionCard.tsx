import { useState } from 'react';
import type { DecisionBrief, DecisionContribution, DecisionTrackRecord } from '../api/client';
import { analysisApi } from '../api/client';
import { apiError } from '../lib/apiError';
import { renderMarkdown } from '../lib/markdown';
import HelpDot from './HelpDot';

const ACTION_LABEL: Record<string, string> = {
  strong_invest: 'STRONG INVEST',
  invest: 'INVEST',
  hold: 'HOLD',
  divest: 'DIVEST',
  strong_divest: 'STRONG DIVEST',
};

const ACTION_TONE: Record<string, string> = {
  strong_invest: '#1e8e4e',
  invest: 'var(--up)',
  hold: 'var(--text-muted)',
  divest: 'var(--down)',
  strong_divest: '#b0342a',
};

const SOURCE_LABEL: Record<string, string> = {
  structure_trend: 'Swing structure',
  structure_break: 'BOS / CHoCH',
  zone_position: 'S/R location',
  pattern_evidence: 'Pattern (validated)',
  regime_momentum: 'Regime momentum',
  forming_leg: 'Forming leg',
  cross_asset: 'Cross-asset',
};

const SOURCE_HELP: Record<string, string> = {
  structure_trend: 'Are the recent tops and bottoms stair-stepping up or down? Up-stairs = bullish.',
  structure_break: 'Break of Structure / Change of Character — price pushed past the last swing level. The most direct "the trend is real" signal.',
  zone_position: 'Where you are relative to price shelves: buying near support is good location, buying into resistance is chasing.',
  pattern_evidence: 'History looked like this before — what happened next? Only counts when its track record beats a coin flip.',
  regime_momentum: 'The net drift and whether bulls or bears are hitting harder over the whole window.',
  forming_leg: 'The move happening right now. Unfinished, so it counts the least.',
  cross_asset: 'Whether BTC is outperforming or lagging assets it usually moves with (gold, Nasdaq).',
};

/** Semicircular -100..+100 gauge drawn as an SVG arc. */
function Gauge({ score, action }: { score: number; action: string }) {
  const clamped = Math.max(-100, Math.min(100, score));
  // Map score to 180° sweep: -100 → left, 0 → top, +100 → right.
  const angle = ((clamped + 100) / 200) * Math.PI;
  const cx = 110, cy = 100, r = 84;
  const x = cx - r * Math.cos(angle);
  const y = cy - r * Math.sin(angle);
  const color = ACTION_TONE[action] || 'var(--text-muted)';
  return (
    <svg viewBox="0 -14 224 158" width="224" height="158" aria-label={`Decision score ${score.toFixed(0)}`}>
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="var(--bg-hover)" strokeWidth="16" strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx - r * Math.cos(Math.PI * 0.82)} ${cy - r * Math.sin(Math.PI * 0.82)}`}
        fill="none" stroke="rgba(231,76,60,0.35)" strokeWidth="16" strokeLinecap="round" />
      <path d={`M ${cx - r * Math.cos(Math.PI * 0.18)} ${cy - r * Math.sin(Math.PI * 0.18)} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="rgba(46,204,113,0.35)" strokeWidth="16" strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={x} y2={y} stroke={color} strokeWidth="3.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="6" fill={color} />
      <text x={cx - r - 2} y={cy + 30} textAnchor="middle" fontSize="11" fill="var(--down)">−100</text>
      <text x={cx} y={-2} textAnchor="middle" fontSize="11" fill="var(--text-faint)">0</text>
      <text x={cx + r + 2} y={cy + 30} textAnchor="middle" fontSize="11" fill="var(--up)">+100</text>
    </svg>
  );
}

function ContributionRow({ c }: { c: DecisionContribution }) {
  const width = Math.min(100, Math.abs(c.score) / 40 * 100); // 40 pts ≈ full bar
  const tone = c.stance === 'invest' ? 'var(--up)' : c.stance === 'divest' ? 'var(--down)' : 'var(--text-faint)';
  return (
    <tr>
      <td className="src">
        {SOURCE_LABEL[c.source] || c.source}
        <HelpDot>{SOURCE_HELP[c.source] || c.source}</HelpDot>
      </td>
      <td>
        <div className="dec-cell">
          <span style={{ color: tone, fontWeight: 600, minWidth: '3.4rem', textAlign: 'right' }}>
            {c.score >= 0 ? '+' : ''}{c.score.toFixed(1)}
          </span>
          <span className="dec-bar">
            <span
              className={c.stance === 'divest' ? 'dec-fill neg' : 'dec-fill pos'}
              style={{ width: `${width}%`, background: tone }}
            />
          </span>
          <span className="muted" style={{ minWidth: '2.2rem' }}>w{Math.round(c.weight)}</span>
          {c.learned_multiplier != null && (
            <span
              className="learned-chip"
              title={`Learned from ${c.alignment_samples ?? 0} graded calls: this evidence's weight was multiplied by ${c.learned_multiplier.toFixed(2)} (baseline ${Math.round(c.prior_weight ?? 0)})`}
            >
              ×{c.learned_multiplier.toFixed(2)}
            </span>
          )}
        </div>
      </td>
      <td className="why">{c.rationale}{c.detail ? <span className="muted"> · {c.detail}</span> : null}</td>
    </tr>
  );
}

function TrackRecordSection({ tr }: { tr: DecisionTrackRecord }) {
  return (
    <div className="dec-trackrecord">
      <div className="learn-title">
        Track record
        <HelpDot>Every call this engine has made, graded against what the market actually did afterwards. The engine uses this history to re-weight its evidence and calibrate its conviction — and shows you the numbers.</HelpDot>
        <span className="badge">{tr.graded_total} graded</span>
        <span className="badge">{tr.live_graded} live</span>
        <span className="badge">{tr.replay_graded} replay</span>
        {tr.pending > 0 && <span className="badge" title="Calls still waiting for their outcome window to pass">{tr.pending} pending</span>}
      </div>

      <div className="tile-grid" style={{ marginBottom: '0.5rem' }}>
        <div className="tile">
          <div className="label">Alignment
            <HelpDot>How often past calls matched what actually happened. Smoothed so tiny samples can't pretend to be perfect.</HelpDot>
          </div>
          <div className="value">{tr.alignment_rate != null ? `${(tr.alignment_rate * 100).toFixed(0)}%` : '—'}</div>
          <div className="sub">{tr.aligned_total}/{tr.graded_total} aligned · {tr.invalidated_total} invalidated</div>
        </div>
        <div className="tile">
          <div className="label">Calibration
            <HelpDot>Conviction is scaled by the alignment rate: a good track record earns a little more confidence, a bad one costs some. Capped at ×0.7–×1.2.</HelpDot>
          </div>
          <div className="value">×{tr.calibration_factor.toFixed(2)}</div>
          <div className="sub">applied to conviction</div>
        </div>
        <div className="tile">
          <div className="label">Avg forward move
            <HelpDot>The average price change that followed all graded calls, over their outcome windows.</HelpDot>
          </div>
          <div className="value" style={{ color: (tr.avg_forward_return_pct ?? 0) >= 0 ? 'var(--up)' : 'var(--down)' }}>
            {tr.avg_forward_return_pct != null ? `${tr.avg_forward_return_pct >= 0 ? '+' : ''}${tr.avg_forward_return_pct.toFixed(2)}%` : '—'}
          </div>
          <div className="sub">after graded calls</div>
        </div>
      </div>

      {tr.source_stats.filter(s => s.samples > 0).length > 0 && (
        <details style={{ marginBottom: '0.5rem' }}>
          <summary className="muted" style={{ cursor: 'pointer', fontSize: '0.72rem' }}>
            What the engine learned per evidence source
            <HelpDot>Each evidence type is re-weighted by its own graded hit rate — shrunk toward neutral for small samples, hard-capped at ×0.5–×1.5 so nothing runs away.</HelpDot>
          </summary>
          <table className="mini-table" style={{ marginTop: '0.4rem' }}>
            <tbody>
              {tr.source_stats.filter(s => s.samples > 0).map(s => (
                <tr key={s.source}>
                  <td>{SOURCE_LABEL[s.source] || s.source}</td>
                  <td className="hl">×{s.multiplier.toFixed(2)} <span className="muted">(was w{Math.round(s.prior_weight)} → {s.effective_weight.toFixed(1)})</span></td>
                  <td className="muted">{s.hits}/{s.samples} right · {s.live_samples} live + {s.replay_samples} replay</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {tr.recent_graded.length > 0 && (
        <details>
          <summary className="muted" style={{ cursor: 'pointer', fontSize: '0.72rem' }}>Recent graded calls</summary>
          <table className="mini-table" style={{ marginTop: '0.4rem' }}>
            <tbody>
              {tr.recent_graded.slice().reverse().map((g, i) => (
                <tr key={i}>
                  <td>{new Date(g.candle_timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                  <td style={{ color: ACTION_TONE[g.action], fontWeight: 700 }}>{ACTION_LABEL[g.action] || g.action}</td>
                  <td>{g.forward_return_pct != null ? `${g.forward_return_pct >= 0 ? '+' : ''}${g.forward_return_pct.toFixed(2)}% after` : '—'}</td>
                  <td>
                    {g.aligned ? <span className="badge badge-up">aligned</span> : <span className="badge badge-down">missed</span>}
                    {g.invalidated && <span className="badge badge-down" title="An invalidation level was hit before the outcome window ended"> invalidated</span>}
                    <span className="muted" style={{ marginLeft: '0.3rem' }}>{g.source === 'live' ? 'live' : 'replay'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      <div className="muted" style={{ fontSize: '0.66rem', marginTop: '0.4rem' }}>{tr.note}</div>
    </div>
  );
}

export default function DecisionCard({ brief }: { brief: DecisionBrief }) {
  const [aiText, setAiText] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState('');

  async function fetchBrief() {
    setAiBusy(true);
    setAiError('');
    try {
      const res = await analysisApi.decisionBrief();
      setAiText(res.data.brief);
    } catch (err) {
      setAiError(apiError(err, 'The AI gateway could not be reached.'));
    } finally {
      setAiBusy(false);
    }
  }

  const tone = ACTION_TONE[brief.action] || 'var(--text-muted)';
  const wf = brief.walk_forward;
  const tr = brief.track_record;

  return (
    <div className="card decision-card">
      <div className="decision-top">
        <div className="decision-gauge">
          <Gauge score={brief.composite_score} action={brief.action} />
        </div>
        <div className="decision-headline">
          <div className="decision-action" style={{ color: tone, borderColor: tone }}>
            {ACTION_LABEL[brief.action] || brief.action}
          </div>
          <div className="decision-score">
            score <strong style={{ color: tone }}>{brief.composite_score >= 0 ? '+' : ''}{brief.composite_score.toFixed(0)}</strong>
            <span className="muted"> / ±100</span>
            <HelpDot>All evidence added up. −100 = strongly reduce, +100 = strongly add. ±18 = lean, ±45 = strong.</HelpDot>
          </div>
          <div className="meter" title="Evidence agreement × evidence quality, calibrated by the graded track record">
            <div className="meter-head">
              <span>Conviction
                <HelpDot>How much the evidence agrees with itself — then scaled by the engine's real track record.</HelpDot>
              </span>
              <span className="meter-value">
                {(brief.conviction * 100).toFixed(0)}%
                {brief.conviction_uncalibrated != null && (
                  <span className="muted" title={`Before track-record calibration: ${(brief.conviction_uncalibrated * 100).toFixed(0)}%`}>
                    {' '}(raw {(brief.conviction_uncalibrated * 100).toFixed(0)}%)
                  </span>
                )}
              </span>
            </div>
            <div className="meter-track"><div className="meter-fill" style={{ width: `${brief.conviction * 100}%` }} /></div>
          </div>
          <div className="muted" style={{ fontSize: '0.7rem' }}>
            evidence quality: <strong>{brief.quality}</strong>
            {brief.conflicts.length > 0 && <> · {brief.conflicts.length} conflict(s)</>}
          </div>
        </div>
        <div className="decision-summary">
          <p style={{ margin: 0, fontSize: '0.84rem' }}>{brief.summary}</p>
          {brief.conflicts.length > 0 && (
            <ul className="conflict-list">
              {brief.conflicts.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          )}
        </div>
      </div>

      <table className="dec-table">
        <thead>
          <tr>
            <th>Evidence</th>
            <th style={{ width: '38%' }}>
              Contribution (weight)
              <HelpDot>Each row's pull on the final score. The ×chip, when present, is a weight learned from graded history.</HelpDot>
            </th>
            <th>Why</th>
          </tr>
        </thead>
        <tbody>
          {[...brief.contributions].sort((a, b) => Math.abs(b.score) - Math.abs(a.score)).map(c => (
            <ContributionRow key={c.source} c={c} />
          ))}
        </tbody>
      </table>

      <div className="decision-bottom">
        {brief.invalidations.length > 0 && (
          <div className="dec-invalidation">
            <div className="learn-title">
              What would flip it
              <HelpDot>"break" levels are where the call is considered wrong — a structure actually breaking flips the engine to the other side. "watch" levels are support/resistance areas worth observing; price trading into them is normal, and grading only counts the break levels as failures.</HelpDot>
            </div>
            {brief.invalidations.map((inv, i) => (
              <div key={i} className="inv-row">
                <span className="inv-price">${inv.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                {inv.kind === 'zone_edge' ? (
                  <span className="badge" title="A support/resistance area being traded into is expected, not a flip — but watch how price behaves there.">
                    watch → {inv.flips_toward}
                  </span>
                ) : (
                  <span className={`badge ${inv.flips_toward === 'invest' ? 'badge-up' : 'badge-down'}`}>
                    break → {inv.flips_toward}
                  </span>
                )}
                <span className="muted" style={{ fontSize: '0.68rem' }}>{inv.rationale}</span>
              </div>
            ))}
          </div>
        )}
        {wf && wf.band_stats.length > 0 && (
          <div className="dec-walkforward">
            <div className="learn-title" title={wf.note}>
              Walk-forward replay · {wf.checkpoints.length} checkpoints · {wf.horizon_bars}-bar forward window
              <HelpDot>The engine re-made this call at points in history using only data it would have had then, and was scored on what followed. Uses fixed baseline weights — an honesty check, not a fit.</HelpDot>
            </div>
            <table className="mini-table">
              <tbody>
                {wf.band_stats.map(s => (
                  <tr key={s.action}>
                    <td>{ACTION_LABEL[s.action] || s.action}</td>
                    <td>{s.count}×</td>
                    <td className="hl">avg fwd {s.avg_forward_return_pct != null ? `${s.avg_forward_return_pct >= 0 ? '+' : ''}${s.avg_forward_return_pct.toFixed(2)}%` : '—'}</td>
                    <td className="muted">aligned {s.aligned_rate != null ? `${(s.aligned_rate * 100).toFixed(0)}%` : '—'}</td>
                  </tr>
                ))}
                <tr>
                  <td>Window drift (benchmark)</td>
                  <td />
                  <td className="hl">{wf.benchmark_return_pct != null ? `${wf.benchmark_return_pct >= 0 ? '+' : ''}${wf.benchmark_return_pct.toFixed(2)}%` : '—'}</td>
                  <td className="muted">compare bands against this, not zero</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>

      {tr && <TrackRecordSection tr={tr} />}

      <div className="decision-ai">
        <div className="card-head">
          <h3 style={{ margin: 0, fontSize: '0.85rem' }}>
            AI decision brief
            <HelpDot>A plain-language walkthrough of the call above, written by the local AI but restricted to the numbers in this card — including the track record.</HelpDot>
          </h3>
          <span className="badge">not financial advice</span>
        </div>
        {aiError && <div className="error-banner">{aiError}</div>}
        {aiText && (
          <div className="md-body" style={{ fontSize: '0.82rem' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(aiText) }} />
        )}
        <button className="btn btn-secondary" style={{ marginTop: '0.4rem', fontSize: '0.78rem' }} onClick={fetchBrief} disabled={aiBusy}>
          {aiBusy ? 'Thinking…' : aiText ? 'Refresh brief' : 'Generate brief'}
        </button>
      </div>

      <div className="muted" style={{ fontSize: '0.66rem' }}>
        Deterministic scorecard — every weight and rationale above is the actual math behind the call.
        {brief.excluded.map(e => ` Excluded: ${e}`)}
      </div>
    </div>
  );
}
