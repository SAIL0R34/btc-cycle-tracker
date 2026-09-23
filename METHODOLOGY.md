# BTC Swing Cycle Tracker - Methodology

This document explains the methodology behind pivot detection, cycle
analysis, and pattern recognition in this project.

## Pivot Detection (ZigZag, reversal-threshold)

Pivots are detected with a classic reversal-threshold ZigZag, run as a
single pass over the candles:

1. After the last confirmed pivot, the detector tracks the **running
   extreme** of the forming leg (highest high on an up leg, lowest low on
   a down leg).
2. When price retraces from that extreme by at least the **reversal
   threshold**, the extreme is confirmed as a pivot and the direction
   flips.
3. The pivot's `confirmation_candle_index` records the bar that confirmed
   it — the point where the swing became knowable without lookahead.

Because a pivot is only emitted after a threshold reversal:

- pivots are true swing extremes (not the first local fractal that
  happens to pass a filter),
- they alternate high/low by construction,
- and the tail of the series is honest: whatever is still moving after
  the last confirmed pivot is exposed as the **forming leg** (last pivot
  → latest close) rather than pretend-confirmed as a pivot.

### Reversal threshold

```
threshold = max(min_move_pct, ATR / price × 100 × atr_multiplier)   [percent]
```

With the ATR filter enabled the threshold is volatility-adaptive:
high-volatility tape demands deeper reversals before a pivot counts,
quiet tape needs less. `min_move_pct` floors the threshold everywhere.

### Alternative methods

- **Fractal** — a candle whose high (low) exceeds N bars on both sides.
- **Fixed window** — extreme of a sliding window plus min-move filter.

### Pivot spacing

`min_candles_between` and `min_leg_duration_bars` enforce a minimum gap
between consecutive pivots; a reversal that completes too close to the
previous pivot keeps tracking until the spacing requirement is met.

## Noise Filtering

### ATR Filter (post-detection)

Drops legs whose pivot-to-pivot move is smaller than `ATR × multiplier`
(average true range over `atr_period` bars):

```
TR = max(high - low, |high - prev_close|, |low - prev_close|)
ATR = mean(TR, atr_period)
```

### Percent Change Filter

Only pivots whose move from the previous pivot exceeds `min_move_pct`
are accepted.

## Swing Legs

A swing leg connects two consecutive pivots:

- **Up leg**: swing low → swing high (positive percent change)
- **Down leg**: swing high → swing low (negative percent change)

Metrics per leg: percent change, duration (minutes and bars).

### Forming leg

The provisional leg from the last confirmed pivot to the latest close.
It is displayed dashed on the chart and excluded from pattern history —
it has no confirming reversal yet.

## Summary Statistics

| Metric | Meaning |
| --- | --- |
| Net change % | close-to-close move over the whole leg path |
| Efficiency ratio | \|net move\| ÷ Σ\|leg moves\| — 1.0 = perfectly directional, →0 = choppy (Kaufman) |
| Realized vol % / bar | std of per-bar log returns of the candle closes |
| Max drawdown % | worst peak-to-trough decline of the closes |
| Up/down asymmetry | signed imbalance between average up-leg size and average down-leg size (+1 = bulls carry the bigger swings) |
| Amplitude·duration corr | Pearson correlation of \|leg %\| vs duration (absolute moves — signed change mixes the two mirrored clouds) |

## Pattern Recognition (v2)

The pattern engine matches the recent leg sequence against history and
forecasts the next legs, then validates itself with walk-forward
backtests.

### Signatures — self-normalising

A signature encodes the last `pattern_length` legs:

```
v2:UDU|MML|SML        directions | relative move size | relative duration
```

Move and duration buckets (S/M/L/X) are cut at the quartiles of the
**run's own leg distribution**, so a signature means "small *for this
market and timeframe*". Fixed percent buckets would silently break
between a 5m and a 1d chart. The `v2:` prefix versions the format —
memory persisted under the old absolute buckets is never matched again.

### Analog matching

Candidates are scored by weighted similarity (direction 0.45, amplitude
0.35, duration 0.20) and the top `pattern_max_matches` above 0.55
become the analog set. The insight reports the **weighted expected**
next-leg and horizon moves *and their interquartile spread* (p25–p75
across matches), because a mean without a range hides most of the
uncertainty.

### Walk-forward validation

Every historical window is predicted using only the data before it.
For each prediction the engine records direction, horizon direction,
expected vs realized magnitude, and the market regime at the time.

### Honest baselines

Zigzag legs alternate by construction, so "predict the next leg
opposite to the last one" (reversion) is a near-perfect null for
*next-leg direction* — that metric is structural, not skill. The
learning summary therefore reports the engine's hit rates **against the
reversion and majority-class baselines**, and elevates the metrics that
are genuinely uncertain:

- **horizon hit rate** — sign of the cumulative move over the next
  `forecast_horizon` legs (not determined by alternation),
- **next-move MAE** — mean absolute error between expected and realized
  next-leg percent change.

### Adaptive confidence & memory

Per-signature outcomes persist across runs in `pattern_memory.json`
(regime-keyed). Hit rates are **Laplace-smoothed** (a 2/2 bucket is
~75%, not 100%), and identical historical windows re-run under
overlapping lookbacks are **deduplicated** so memory doesn't inflate on
every run. Adaptive confidence blends fresh analog similarity with the
persisted, smoothed hit rates as the sample grows.

## Cycle Analysis

A cycle is an up leg followed by a down leg (or the reverse). Metrics:
cycle duration, cumulative % change, leg count.

## Decision Engine

The decision engine aggregates every evidence source into a single
auditable scorecard. Nothing is hidden: each contribution's weight,
direction, and rationale are shown in the UI, and the composite is just
the weight-normalised signed sum on a −100…+100 scale.

### Evidence and weights (Σ = 100)

| Source | Weight | What it measures |
| --- | --- | --- |
| Swing structure | 22 | rising/falling pivot structure (HH+HL vs LH+LL) |
| BOS / CHoCH | 18 | most recent confirmed break of structure, scaled by confidence |
| S/R location | 15 | distance to nearest support/resistance zone (good vs poor location) |
| Pattern (validated) | 15 | analog bias **scaled by adaptive confidence × validated horizon edge** — a bias with no edge over the naive null contributes nothing |
| Regime momentum | 15 | window net change + magnitude skew |
| Forming leg | 8 | current unconfirmed move |
| Cross-asset | 7 | BTC relative strength vs gold/Nasdaq, weighted by return correlation |

**Moon phases are excluded** from the decision (display-only; no known
causal edge) — the brief lists them under "excluded" for transparency.

### Gates

- **Chop gate** — when the Kaufman efficiency ratio < 0.12, all
  trend-following contributions are halved (trend signals are noise in
  chop) and the summary says so.
- **Quality gate** — low evidence quality (few legs, few matches,
  conflicting signals, from `build_market_intelligence`) caps the action
  at the inner bands and holds unless agreement is strong.
- **Conflicts** — every intelligence conflict is carried into the brief
  and damps conviction.

### Action bands

`±45` → strong invest/divest · `±18` → invest/divest · between → hold.

### Walk-forward replay

The same scorecard is re-evaluated at up to 12 historical checkpoints,
each using **only the candles available at that moment** (no lookahead),
and every replayed call is scored against the realised forward move over
the horizon. Band stats (count, average forward return, alignment rate)
are shown next to the window's drift benchmark — read the bands against
drift, not against zero. The replay uses structural + regime evidence
only (the pattern engine is excluded: too slow to replay, and it has its
own independent walk-forward test).

### AI narrative

An optional LLM brief (local OpenAI-compatible gateway, configured via
`BTC_LLM_BASE_URL`/`BTC_LLM_MODEL`) explains the scorecard
in plain language under a strict grounding prompt: it may not change the
call or invent numbers. Not financial advice.

## Decision Learning Loop (memory, grading, adaptation)

Every decision is accountable to its own future:

1. **Log** — each analysis run logs its decision (and each walk-forward
   replay checkpoint logs a `replay`-flagged copy) with the grading
   horizon *frozen at log time*. Records persist in
   `outputs/decision_memory.json`, deduplicated by
   (source, symbol, timeframe, candle timestamp) — re-runs update in
   place and never double-count.
2. **Grade** — once later candles cover the outcome window, the record is
   graded once (one-shot; first verdict sticks): realised forward return,
   whether a **structure-break** invalidation level was breached inside
   the window (zone edges being traded into are informational — entering
   a support/resistance area is normal market behaviour, not a flip),
   and an `aligned` verdict (invest/divest by direction, hold by staying
   within a volatility-scaled band; breaches count against alignment).
3. **Learn** — per-evidence-source alignment rates over graded records
   (only where the source actually contributed, hold outcomes excluded)
   are shrunk toward 0.5 (prior strength 10), doubled into weight
   multipliers, hard-capped at ×0.5–×1.5, and renormalised so weights
   still sum to 100. The engine-level alignment rate calibrates
   conviction (capped ×0.7–×1.2). Adaptation stays off until
   `decision_learning_min_samples` decisions are graded.
4. **Acknowledge** — the track record (alignment, live/replay split,
   per-source multipliers, invalidated calls, recent graded decisions)
   is shown on the card and injected into the AI brief prompt, which is
   instructed to acknowledge it explicitly and to call out thin samples.

Guards against self-deception: grading reads only candles up to each
record's frozen due timestamp (no lookahead); the walk-forward replay
always scores with the fixed baseline weights (never the adaptive ones)
so it stays an honest out-of-sample control; heavy shrinkage plus caps
prevent runaway feedback; the bounded store evicts old replay records
before live ones (live history is irreplaceable, replay is re-seedable).

## Data Requirements

- OHLCV data; at least ~100 candles for meaningful analysis
- Pattern recognition needs `pattern_length + forecast_horizon + 1`
  completed legs

## Output Files

- `pivots.csv` — index, timestamp, price, type, confirmation candle
- `legs.csv` — start/end timestamps, prices, % change, duration, direction
- `summary.csv` / `analysis.json` — summary statistics and insights
- `chart.html` — interactive candlestick chart with legs and pivots
