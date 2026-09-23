# BTC Swing Cycle Tracker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)]
[![React 19](https://img.shields.io/badge/frontend-React%2019-61dafb.svg)](https://react.dev)
[![Tests](https://img.shields.io/badge/tests-106%20passing-brightgreen.svg)](#testing)

![Dashboard — summary tiles, decision engine, and the chart with ZigZag legs and Bollinger Bands](docs/dashboard.png)

<p align="center">
  <img src="docs/decision-engine.png" width="49%" alt="Decision engine — track record, learned weights, graded calls" />
  <img src="docs/cross-asset.png" width="49%" alt="Cross-asset module — BTC vs Nasdaq rebased with rolling correlation" />
</p>

Detect noise-filtered BTC swing pivots, turn them into measurable pivot-to-pivot legs, and
condense everything — structure, patterns, regime, cross-asset context — into an **auditable
invest/divest decision** that is logged, graded against what actually happened, and re-weighted
by its own track record. Every number on the dashboard can be traced back to the math that
produced it, and every term has a plain-English "?" explainer on hover.

## Why it's different

Most dashboards show indicators. This one shows its **reasoning and its report card**:

- **Reversal-threshold ZigZag** — pivots are confirmed only after price actually reverses past
  an ATR-adaptive threshold, so they are true swing extremes, alternate by construction, and
  are knowable without lookahead. The move still in progress is shown honestly as a dashed
  *forming leg*, never mixed into history.
- **An auditable decision engine** — seven evidence sources (swing structure, breaks of
  structure, S/R location, validated pattern edge, regime momentum, forming leg, cross-asset
  relative strength) are weighted into a −100…+100 composite with explicit action bands, chop
  and quality gates, and invalidation levels ("what would flip this call"). Moon phases are
  deliberately excluded.
- **A learning loop with receipts** — every call is logged, graded one-shot against the
  realized outcome (structure breaks count as flips), and the graded history feeds back:
  evidence weights earn or lose trust (capped ×0.5–×1.5, shrunk on small samples) and
  conviction is calibrated by the engine's alignment rate. The AI narrative is required to
  acknowledge the track record — including when it's thin.
- **Honest statistics** — walk-forward validation against naive baselines (zigzag legs
  alternate, so "next-leg direction" is a near-deterministic null; horizon hit rate and
  next-move error carry the real signal), Laplace-smoothed hit rates, deduplicated memory.
- **Familiar charting, optional** — Bollinger Bands, SMA, EMA, VWAP, and Donchian channels
  with editable periods, remembered per browser; plus modular tabs for cross-asset
  correlation and moon-phase observation.
- **A conversational agent** that can read the analysis, re-run it, change config, and export
  data — with confirm-before-write for anything that changes state.
- **Customizable layout** — drag-and-drop the dashboard modules, hide what you don't use,
  collapse the sidebar; the layout persists.

## Quick start

```bash
git clone https://github.com/SAIL0R34/btc-cycle-tracker.git
cd btc-cycle-tracker

# Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -e . && pip install "fastapi>=0.110" "uvicorn>=0.29"

# Web app (builds the React frontend on first run, then serves)
./serve.sh
# open http://localhost:8010
```

The dashboard auto-runs an analysis on first load. Press `R` to re-run, or ask the agent in
the bottom-right corner. Set `BTC_HOST=0.0.0.0` before `./serve.sh` to expose it on your LAN.

### Command line

```bash
python -m btc_cycle_tracker.cli.main analyze \
    --symbol BTC-USD --timeframe 5m --lookback 30d \
    --pivot-method zigzag --min-move-pct 1.0
```

### Configuration

Optional features are toggled in the sidebar (and persist across restarts). Infrastructure
settings live in environment variables — a gitignored `.env` is loaded at startup
(see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `BTC_LLM_BASE_URL` / `BTC_LLM_MODEL` / `BTC_LLM_API_KEY` | Local OpenAI-compatible gateway for the agent and AI reads (any vLLM/Ollama/llama.cpp server works) |
| `BTC_HOST` / `BTC_PORT` | Web app bind address (default `127.0.0.1:8010`) |
| `COINBASE_API_KEY` / `COINBASE_API_SECRET` | Optional exchange credentials (public candle data needs none) |

All analytics run on public exchange data (Coinbase candles, Yahoo Finance for
gold/Nasdaq/oil) — no API keys required for the core experience.

## Architecture

```
btc_cycle_tracker/
├── data/          # Fetching (Coinbase), caching, normalization
├── pivots/        # ZigZag / fractal detection, ATR + confirmation filters
├── analytics/     # Legs, stats, structures, patterns v2, intelligence,
│                  # decision engine + decision memory (learning loop)
├── visualization/ # Plotly chart generation (exports)
├── export/        # CSV / JSON writers
├── services/      # Orchestration (AnalysisService)
├── web/           # FastAPI server, agent chat, LLM client, serializers
└── app/           # Legacy Streamlit UI
frontend/          # React 19 + Vite dashboard
```

## Methodology

The full methodology — pivot detection, honest baselines, the decision scorecard, gates,
walk-forward replay, and the learning loop — is documented in
[METHODOLOGY.md](METHODOLOGY.md).

## Testing

```bash
pytest                # 106 tests
pytest --cov=src --cov-report=html
```

## Roadmap

- [ ] Live/incremental data updates (websocket candle stream)
- [ ] Parameter sweep engine across timeframes/methods
- [ ] Background scheduler for hands-free decision logging
- [ ] Database persistence for decision memory

## Glossary

<details>
<summary>Every term the dashboard uses, in plain English (click to expand)</summary>

**Structure**

- **Swing High / Swing Low**: A local peak/trough where price turned around.
- **Pivot**: A detected turning point used to build swing legs.
- **Leg**: One full move from a pivot to the next pivot.
- **Forming Leg**: The provisional move after the last confirmed pivot — unconfirmed, shown dashed, never used as history.
- **Reversal Threshold**: The retracement (max of `min_move_pct` and an ATR-scaled floor) required to confirm a ZigZag pivot.
- **BOS / CHoCH**: Break of Structure (price pushed past the prior swing level) / Change of Character (first break the other way).
- **S/R Zone**: A price shelf where price bounced repeatedly — support below, resistance above.

**Statistics**

- **Efficiency Ratio**: |net move| ÷ Σ|leg moves|; 1.0 is a perfectly directional trend, →0 is chop.
- **Realized Volatility**: Standard deviation of per-bar close-to-close log returns.
- **Max Drawdown**: Worst peak-to-trough decline of the close series over the window.
- **Magnitude Skew**: Signed imbalance between average up-leg and down-leg size.
- **ATR**: Average True Range — how far price typically moves per candle.

**Pattern recognition**

- **Pattern Signature**: Compact code for recent legs — directions, relative sizes, relative durations (`v2:UDU|MML|SML`), bucketed by the run's own distribution so it works on any timeframe.
- **Analog Match**: A historical sequence that resembles the current one.
- **Forecast Horizon**: How many future swings the forecast covers.
- **Reversion Baseline**: The "next leg is opposite the last" null — near-perfect on alternating zigzag legs, which is why horizon hit rate and next-move error (MAE) carry the real signal.

**Decision engine**

- **Decision Composite**: Weight-normalized signed sum of all evidence, −100…+100.
- **Action Band**: strong_invest / invest / hold / divest / strong_divest, capped by evidence quality.
- **Chop Gate**: When efficiency is very low, trend-following evidence is halved.
- **Invalidation Level**: A price whose break flips the call ("break" levels flip; zone edges are "watch").
- **Walk-Forward Replay**: The scorecard re-run at historical checkpoints with no lookahead, scored against realized forward moves.
- **Decision Memory**: The persisted log of every call (`outputs/decision_memory.json`), graded once its outcome window passes.
- **Aligned / Invalidated**: A graded call matched the outcome / a flip level was breached first.
- **Learned Multiplier**: How much an evidence source's weight was scaled by its graded track record (×0.5–×1.5).
- **Calibration**: Conviction scaled by the engine's overall graded alignment rate (×0.7–×1.2).
- **Live vs Replay**: live = a real call at analysis time; replay = a historical practice call seeding the track record.

</details>

## Disclaimer

This project is an analytics and research tool. It is **not financial advice**, not a
recommendation to buy or sell anything, and its outputs — including the decision engine —
are statistical observations about historical price action with no guarantee of future
behavior. Markets can invalidate any model. Use your own judgment.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and pull requests are welcome. Please keep the project's core principle in mind:
**every signal must stay auditable** — weights, baselines, and track records belong on screen.

## Acknowledgments

- [Plotly](https://plotly.com/) for interactive charting
- [Pydantic](https://docs.pydantic.org/) for data validation
- [FastAPI](https://fastapi.tiangolo.com/) + [React](https://react.dev) for the web app
