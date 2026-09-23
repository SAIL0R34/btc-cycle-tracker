import type { AppConfig, Options } from '../api/client';
import HelpDot from './HelpDot';

interface Props {
  config: AppConfig;
  options: Options | null;
  running: boolean;
  onChange: (fields: Partial<AppConfig>) => void;
  onRun: () => void;
}

const LOOKBACKS = ['7d', '14d', '30d', '60d', '90d', '26w', '12m', '1y', '2y'];

const TIMEFRAME_MINUTES: Record<string, number> = {
  '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440, '1w': 10080,
};

const PRESETS: Array<{ name: string; hint: string; fields: Partial<AppConfig> }> = [
  {
    name: 'Scalp',
    hint: '5m chart, small swings, tight noise floor',
    fields: { timeframe: '5m', lookback_period: '7d', min_move_pct: 0.6, left_bars: 4, right_bars: 4, use_atr_filter: true },
  },
  {
    name: 'Swing',
    hint: '1h chart, standard swing detection',
    fields: { timeframe: '1h', lookback_period: '60d', min_move_pct: 1.5, left_bars: 5, right_bars: 5, use_atr_filter: true },
  },
  {
    name: 'Macro',
    hint: '1d chart, only major swings',
    fields: { timeframe: '1d', lookback_period: '1y', min_move_pct: 5, left_bars: 5, right_bars: 5, use_atr_filter: false },
  },
];

function estimateCandles(lookback: string, timeframe: string): number | null {
  const m = lookback.match(/^(\d+)([dwmMy])$/);
  if (!m) return null;
  const n = Number(m[1]);
  const unitMinutes: Record<string, number> = { d: 1440, w: 10080, m: 43200, y: 525600 };
  const tf = TIMEFRAME_MINUTES[timeframe];
  if (!tf) return null;
  return Math.round((n * unitMinutes[m[2]]) / tf);
}

export default function ControlPanel({ config, options, running, onChange, onRun }: Props) {
  const timeframes = options?.timeframes ?? ['1m', '5m', '15m', '1h', '4h', '1d', '1w'];
  const methods = options?.pivot_methods ?? ['zigzag', 'fractal', 'fixed_window'];
  const symbols = options?.symbols ?? ['BTC-USD'];

  const num = (v: string, fallback: number) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
  };

  const est = estimateCandles(config.lookback_period, config.timeframe);

  return (
    <div>
      <div className="section-title">Market</div>

      <div className="preset-row">
        {PRESETS.map((p) => (
          <button
            key={p.name}
            className="btn preset-btn"
            title={p.hint}
            disabled={running}
            onClick={() => onChange(p.fields)}
          >
            {p.name}
          </button>
        ))}
      </div>

      <div className="field">
        <label>Symbol</label>
        <input
          className="input"
          list="symbol-presets"
          value={config.symbol}
          onChange={(e) => onChange({ symbol: e.target.value })}
        />
        <datalist id="symbol-presets">
          {symbols.map((s) => <option key={s} value={s} />)}
        </datalist>
      </div>

      <div className="field">
        <label>Timeframe</label>
        <select className="input" value={config.timeframe} onChange={(e) => onChange({ timeframe: e.target.value })}>
          {timeframes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      <div className="field">
        <label>Lookback {est != null && <span className="est-chip" title="Estimated candle count for this lookback + timeframe">~{est.toLocaleString()} candles</span>}</label>
        <select className="input" value={config.lookback_period} onChange={(e) => onChange({ lookback_period: e.target.value })}>
          {!LOOKBACKS.includes(config.lookback_period) && <option value={config.lookback_period}>{config.lookback_period}</option>}
          {LOOKBACKS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>

      <div className="section-title">Pivot detection</div>

      <div className="field">
        <label>Method</label>
        <select className="input" value={config.pivot_method} onChange={(e) => onChange({ pivot_method: e.target.value })}>
          {methods.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <div className="field-help">ZigZag confirms a pivot only after price reverses by the threshold — true swing extremes, alternating by construction.</div>
      </div>

      <div className="field">
        <label>
          Min move %
          <HelpDot>Ignore-the-wiggles dial: a turn only counts as a real swing if price reversed by at least this much. Bigger number = fewer, larger swings.</HelpDot>
        </label>
        <input
          className="input" type="number" step="0.1" min="0.1"
          value={config.min_move_pct}
          onChange={(e) => onChange({ min_move_pct: num(e.target.value, config.min_move_pct) })}
        />
      </div>

      {config.pivot_method !== 'zigzag' && (
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <div className="field" style={{ flex: 1 }}>
            <label>
              Left bars
              <HelpDot>How many candles before a candidate must be lower (for a top) or higher (for a bottom).</HelpDot>
            </label>
            <input className="input" type="number" min="1" value={config.left_bars}
              onChange={(e) => onChange({ left_bars: num(e.target.value, config.left_bars) })} />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>
              Right bars
              <HelpDot>How many candles after a candidate must stay lower/higher for the turn to count.</HelpDot>
            </label>
            <input className="input" type="number" min="1" value={config.right_bars}
              onChange={(e) => onChange({ right_bars: num(e.target.value, config.right_bars) })} />
          </div>
        </div>
      )}

      <label className="check-row">
        <input type="checkbox" checked={config.use_atr_filter}
          onChange={(e) => onChange({ use_atr_filter: e.target.checked })} />
        <span>
          ATR-adaptive threshold
          <HelpDot>ATR = how much price typically moves per candle. With this on, the ignore-the-wiggles dial automatically demands deeper reversals when the market is jumpy and shallower ones when it is calm.</HelpDot>
        </span>
      </label>

      {config.use_atr_filter && (
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <div className="field" style={{ flex: 1 }}>
            <label>
              ATR period
              <HelpDot>How many candles are averaged to measure "typical" movement.</HelpDot>
            </label>
            <input className="input" type="number" min="2" value={config.atr_period}
              onChange={(e) => onChange({ atr_period: num(e.target.value, config.atr_period) })} />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>
              Multiplier
              <HelpDot>How many "typical moves" the reversal must exceed before a turn counts.</HelpDot>
            </label>
            <input className="input" type="number" step="0.1" min="0.1" value={config.atr_multiplier}
              onChange={(e) => onChange({ atr_multiplier: num(e.target.value, config.atr_multiplier) })} />
          </div>
        </div>
      )}

      <div className="section-title">Insights</div>

      <label className="check-row">
        <input type="checkbox" checked={config.enable_decision_engine}
          onChange={(e) => onChange({ enable_decision_engine: e.target.checked })} />
        <span>
          Decision engine
          <HelpDot>The invest/divest scorecard at the top of the dashboard: every signal weighted, with flip-levels and a graded track record.</HelpDot>
        </span>
      </label>

      {config.enable_decision_engine && (
        <>
          <div className="field">
            <label>
              Walk-forward checkpoints
              <HelpDot>How many points in history to re-make the decision at, for the honesty table. More = slower runs. 0 = off.</HelpDot>
            </label>
            <input className="input" type="number" min="0" max="24" value={config.decision_walk_forward_checkpoints}
              onChange={(e) => onChange({ decision_walk_forward_checkpoints: num(e.target.value, config.decision_walk_forward_checkpoints) })} />
          </div>
          <label className="check-row">
            <input type="checkbox" checked={config.enable_decision_memory}
              onChange={(e) => onChange({ enable_decision_memory: e.target.checked })} />
            <span>
              Decision memory
              <HelpDot>Log every call, later grade it against what actually happened, and show the track record. This is the engine's accountability journal.</HelpDot>
            </span>
          </label>
          {config.enable_decision_memory && (
            <>
              <label className="check-row">
                <input type="checkbox" checked={config.enable_adaptive_decision_weights}
                  onChange={(e) => onChange({ enable_adaptive_decision_weights: e.target.checked })} />
                <span>
                  Learn from outcomes
                  <HelpDot>Let the graded track record re-weight the evidence (each type earns or loses trust, capped at ×0.5–×1.5) and calibrate conviction.</HelpDot>
                </span>
              </label>
              <div className="field">
                <label>
                  Min samples to adapt
                  <HelpDot>How many graded calls are needed before learning kicks in. Keeps tiny samples from steering.</HelpDot>
                </label>
                <input className="input" type="number" min="0" max="100" value={config.decision_learning_min_samples}
                  onChange={(e) => onChange({ decision_learning_min_samples: num(e.target.value, config.decision_learning_min_samples) })} />
              </div>
            </>
          )}
        </>
      )}

      <label className="check-row">
        <input type="checkbox" checked={config.enable_pattern_recognition}
          onChange={(e) => onChange({ enable_pattern_recognition: e.target.checked })} />
        <span>
          Pattern recognition
          <HelpDot>"History looked like this before — what happened next?" Matches the recent swings against the past and forecasts the next moves, with honest scorekeeping.</HelpDot>
        </span>
      </label>

      {config.enable_pattern_recognition && (
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <div className="field" style={{ flex: 1 }}>
            <label>
              Length
              <HelpDot>How many recent swings form the "fingerprint" being matched against history.</HelpDot>
            </label>
            <input className="input" type="number" min="2" max="6" value={config.pattern_length}
              onChange={(e) => onChange({ pattern_length: num(e.target.value, config.pattern_length) })} />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>
              Horizon
              <HelpDot>How many future swings the forecast covers.</HelpDot>
            </label>
            <input className="input" type="number" min="1" max="6" value={config.pattern_forecast_horizon}
              onChange={(e) => onChange({ pattern_forecast_horizon: num(e.target.value, config.pattern_forecast_horizon) })} />
          </div>
        </div>
      )}

      <label className="check-row">
        <input type="checkbox" checked={config.enable_moon_phase_analysis}
          onChange={(e) => onChange({ enable_moon_phase_analysis: e.target.checked })} />
        <span>
          Moon phase analysis
          <HelpDot>Lunar cycles vs swing timing. For fun — deliberately excluded from the decision engine.</HelpDot>
        </span>
      </label>
      <label className="check-row">
        <input type="checkbox" checked={config.enable_gold_correlation_analysis}
          onChange={(e) => onChange({ enable_gold_correlation_analysis: e.target.checked })} />
        <span>
          Gold correlation
          <HelpDot>Compare BTC with gold over the same window — do they move together, and who won?</HelpDot>
        </span>
      </label>
      <label className="check-row">
        <input type="checkbox" checked={config.enable_nasdaq_correlation_analysis}
          onChange={(e) => onChange({ enable_nasdaq_correlation_analysis: e.target.checked })} />
        <span>
          Nasdaq correlation
          <HelpDot>Compare BTC with the tech-heavy Nasdaq index — is BTC just riding the risk trade?</HelpDot>
        </span>
      </label>
      <label className="check-row">
        <input type="checkbox" checked={config.enable_oil_correlation_analysis}
          onChange={(e) => onChange({ enable_oil_correlation_analysis: e.target.checked })} />
        <span>
          Oil correlation
          <HelpDot>Compare BTC with crude oil futures over the same window.</HelpDot>
        </span>
      </label>

      <div style={{ marginTop: '1.1rem' }}>
        <button className="btn btn-primary btn-block" onClick={onRun} disabled={running}>
          {running ? 'Running…' : 'Run analysis  (R)'}
        </button>
      </div>
    </div>
  );
}
