import { useEffect, useRef, useState } from 'react';
import type { AnalysisResult } from '../api/client';
import HelpDot from './HelpDot';
import { bollinger, donchian, ema, sma, vwap } from '../lib/indicators';

const COLORS = {
  up: '#2ecc71',
  down: '#e74c3c',
  pivotHigh: '#f39c12',
  pivotLow: '#3498db',
  forming: '#f7931a',
  sma: '#f1c40f',
  ema: '#9b59b6',
  bb: '#3b82f6',
  vwap: '#1abc9c',
  donchian: '#8791a3',
};

type Overlay = 'legs' | 'pivots' | 'zones' | 'events' | 'volume';

// ── Indicator configuration (persisted per browser) ────────────────────

interface IndicatorsConfig {
  sma: { on: boolean; period: number };
  ema: { on: boolean; period: number };
  bb: { on: boolean; period: number; mult: number };
  vwap: { on: boolean };
  donchian: { on: boolean; period: number };
}

const DEFAULT_INDICATORS: IndicatorsConfig = {
  sma: { on: false, period: 20 },
  ema: { on: false, period: 21 },
  bb: { on: true, period: 20, mult: 2 },
  vwap: { on: false },
  donchian: { on: false, period: 20 },
};

const INDICATORS_KEY = 'btc-indicators-v1';

function loadIndicators(): IndicatorsConfig {
  try {
    const raw = localStorage.getItem(INDICATORS_KEY);
    if (raw) return { ...DEFAULT_INDICATORS, ...JSON.parse(raw) };
  } catch { /* fall back to defaults */ }
  return DEFAULT_INDICATORS;
}

const INDICATOR_HELP: Record<string, string> = {
  sma: 'Simple Moving Average — the average close over the last N candles, drawn as a smooth line. The classic "is price above or below its average" read.',
  ema: 'Exponential Moving Average — like the SMA but reacting faster to recent candles. Shorter period = twitchier line.',
  bb: 'Bollinger Bands — an envelope around the average price: the middle line is the average, the outer bands are ±2 typical deviations. Wide bands = jumpy market; pinched bands = quiet, often before a big move.',
  vwap: 'Volume-Weighted Average Price — the average price weighted by how much traded there. Institutions care about it; price above VWAP = buyers in control over the window.',
  donchian: 'Donchian Channel — the highest high and lowest low of the last N candles. The classic breakout-turtle envelope.',
};

const OVERLAYS: Array<{ key: Overlay; label: string; help: string }> = [
  { key: 'legs', label: 'Legs', help: 'The completed swings: a line drawn from each confirmed turnaround to the next. Green = up-swing, red = down-swing.' },
  { key: 'pivots', label: 'Pivots', help: 'Confirmed turning points. Orange down-triangles = swing tops, blue up-triangles = swing bottoms.' },
  { key: 'zones', label: 'S/R zones', help: 'Support/resistance: price shelves where the market bounced more than once. Below price = support (bounces up off it); above = resistance (bounces down off it).' },
  { key: 'events', label: 'BOS / CHoCH', help: 'Break of Structure (price pushed past the previous swing level — trend continues) and Change of Character (first break the other way — possible trend change).' },
  { key: 'volume', label: 'Volume', help: 'How much traded each candle. Tall bars = crowded, move-worthy candles.' },
];

function fmtTime(ts: string): string {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function PriceChart({ result }: { result: AnalysisResult }) {
  const el = useRef<HTMLDivElement>(null);
  const [on, setOn] = useState<Record<Overlay, boolean>>({
    legs: true, pivots: true, zones: true, events: true, volume: true,
  });
  const [indicators, setIndicators] = useState<IndicatorsConfig>(loadIndicators);
  const [showIndicators, setShowIndicators] = useState(false);

  const toggle = (key: Overlay) => setOn(prev => ({ ...prev, [key]: !prev[key] }));

  useEffect(() => {
    localStorage.setItem(INDICATORS_KEY, JSON.stringify(indicators));
  }, [indicators]);

  const patchIndicator = <K extends keyof IndicatorsConfig>(key: K, fields: Partial<IndicatorsConfig[K]>) => {
    setIndicators(prev => ({ ...prev, [key]: { ...prev[key], ...fields } }));
  };

  useEffect(() => {
    const node = el.current;
    if (!node || !window.Plotly) return;

    const candles = result.candles || [];
    const data: Array<Record<string, unknown>> = [
      {
        type: 'candlestick',
        name: result.metadata.symbol,
        x: candles.map((c) => c.t),
        open: candles.map((c) => c.o),
        high: candles.map((c) => c.h),
        low: candles.map((c) => c.l),
        close: candles.map((c) => c.c),
        increasing: { line: { color: COLORS.up } },
        decreasing: { line: { color: COLORS.down } },
        opacity: 0.85,
      },
    ];

    if (on.volume && candles.length) {
      const maxVol = Math.max(...candles.map((c) => c.v), 1);
      data.push({
        type: 'bar',
        name: 'Volume',
        x: candles.map((c) => c.t),
        y: candles.map((c) => c.v / maxVol),       // 0..1, drawn on a slim overlay axis
        marker: { color: candles.map((c) => (c.c >= c.o ? 'rgba(46,204,113,0.35)' : 'rgba(231,76,60,0.35)')) },
        yaxis: 'y2',
        hoverinfo: 'skip',
        showlegend: false,
      });
    }

    // Leg lines pivot-to-pivot (solid = confirmed)
    if (on.legs) {
      for (const leg of result.legs) {
        data.push({
          type: 'scatter',
          mode: 'lines',
          x: [leg.start_timestamp, leg.end_timestamp],
          y: [leg.start_price, leg.end_price],
          line: { color: leg.direction === 'up' ? COLORS.up : COLORS.down, width: 2 },
          hoverinfo: 'text',
          text: `Leg ${leg.leg_id}: ${leg.direction} ${leg.percent_change.toFixed(2)}% in ${Math.round(leg.duration_minutes)}m`,
          showlegend: false,
        });
      }
    }

    // ── Classic indicator overlays (computed client-side) ─────────────
    const closes = candles.map((c) => c.c);
    const xs = candles.map((c) => c.t);
    const indicatorTraces: Array<Record<string, unknown>> = [];

    if (indicators.bb.on && candles.length > indicators.bb.period) {
      const bb = bollinger(closes, indicators.bb.period, indicators.bb.mult);
      indicatorTraces.push(
        {
          type: 'scatter', mode: 'lines', name: `BB upper (${indicators.bb.period}, ${indicators.bb.mult}σ)`,
          x: xs, y: bb.upper, line: { color: COLORS.bb, width: 1 }, hoverinfo: 'skip',
        },
        {
          type: 'scatter', mode: 'lines', name: `BB lower (${indicators.bb.period})`,
          x: xs, y: bb.lower, line: { color: COLORS.bb, width: 1 },
          fill: 'tonexty', fillcolor: 'rgba(59, 130, 246, 0.08)', hoverinfo: 'skip',
        },
        {
          type: 'scatter', mode: 'lines', name: `BB basis`,
          x: xs, y: bb.mid, line: { color: COLORS.bb, width: 1, dash: 'dot' }, hoverinfo: 'skip',
        },
      );
    }
    if (indicators.sma.on && candles.length > indicators.sma.period) {
      indicatorTraces.push({
        type: 'scatter', mode: 'lines', name: `SMA ${indicators.sma.period}`,
        x: xs, y: sma(closes, indicators.sma.period),
        line: { color: COLORS.sma, width: 1.5 },
      });
    }
    if (indicators.ema.on && candles.length > indicators.ema.period) {
      indicatorTraces.push({
        type: 'scatter', mode: 'lines', name: `EMA ${indicators.ema.period}`,
        x: xs, y: ema(closes, indicators.ema.period),
        line: { color: COLORS.ema, width: 1.5 },
      });
    }
    if (indicators.vwap.on) {
      indicatorTraces.push({
        type: 'scatter', mode: 'lines', name: 'VWAP (window)',
        x: xs, y: vwap(candles),
        line: { color: COLORS.vwap, width: 1.8, dash: 'dash' },
      });
    }
    if (indicators.donchian.on && candles.length > indicators.donchian.period) {
      const dc = donchian(candles, indicators.donchian.period);
      indicatorTraces.push(
        {
          type: 'scatter', mode: 'lines', name: `Donchian ${indicators.donchian.period} high`,
          x: xs, y: dc.upper, line: { color: COLORS.donchian, width: 1, dash: 'dash' }, hoverinfo: 'skip',
        },
        {
          type: 'scatter', mode: 'lines', name: `Donchian ${indicators.donchian.period} low`,
          x: xs, y: dc.lower, line: { color: COLORS.donchian, width: 1, dash: 'dash' }, hoverinfo: 'skip',
        },
      );
    }
    data.push(...indicatorTraces);

    // The leg still forming after the last confirmed pivot — dashed, live.
    const fl = result.forming_leg;
    if (fl) {
      data.push({
        type: 'scatter',
        mode: 'lines+text',
        x: [fl.start_timestamp, fl.end_timestamp],
        y: [fl.start_price, fl.end_price],
        line: { color: COLORS.forming, width: 2, dash: 'dot' },
        hoverinfo: 'text',
        text: ['', 'forming'],
        textposition: 'top center',
        textfont: { size: 10, color: COLORS.forming },
        showlegend: false,
        hoverlabel: { namelength: -1 },
        hovertemplate: `Forming leg: ${fl.direction} ${fl.percent_change.toFixed(2)}% so far (${fl.duration_bars} bars)<extra></extra>`,
      });
    }

    if (on.pivots) {
      const highs = result.pivots.filter((p) => p.pivot_type === 'swing_high');
      const lows = result.pivots.filter((p) => p.pivot_type === 'swing_low');
      data.push(
        {
          type: 'scatter',
          mode: 'markers',
          name: 'Swing highs',
          x: highs.map((p) => p.timestamp),
          y: highs.map((p) => p.price),
          marker: { symbol: 'triangle-down', size: 10, color: COLORS.pivotHigh },
        },
        {
          type: 'scatter',
          mode: 'markers',
          name: 'Swing lows',
          x: lows.map((p) => p.timestamp),
          y: lows.map((p) => p.price),
          marker: { symbol: 'triangle-up', size: 10, color: COLORS.pivotLow },
        },
      );
    }

    const shapes: Array<Record<string, unknown>> = [];
    for (const item of result.structure_discoveries || []) {
      const color = item.direction === 'bullish' ? '#2ecc71' : item.direction === 'bearish' ? '#e74c3c' : '#60a5fa';
      if (on.zones && item.zone_low != null && item.zone_high != null) {
        shapes.push({ type: 'rect', xref: 'x', yref: 'y', x0: item.start_timestamp, x1: candles.at(-1)?.t || item.end_timestamp,
          y0: item.zone_low, y1: item.zone_high, fillcolor: color, opacity: 0.1, line: { color, width: 1, dash: 'dot' } });
      }
      if (on.events && (item.structure_type.includes('break') || item.structure_type.includes('character')) && item.anchors.length >= 2) {
        data.push({ type: 'scatter', mode: 'markers+text', x: [item.anchors.at(-1)?.timestamp], y: [item.anchors.at(-1)?.price],
          text: [item.structure_type === 'change_of_character' ? 'CHoCH' : 'BOS'], textposition: 'top center',
          marker: { size: 12, symbol: 'diamond', color }, name: item.title, hovertext: item.evidence.join('<br>') });
      }
    }

    // Last price marker
    const last = candles.at(-1);
    if (last) {
      shapes.push({
        type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: last.c, y1: last.c,
        line: { color: 'rgba(247,147,26,0.55)', width: 1, dash: 'dot' },
      });
    }

    const layout = {
      margin: { l: 55, r: 15, t: 48, b: 30 },
      height: 520,
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#b6bfcd', size: 11 },
      xaxis: {
        rangeslider: { visible: false },
        gridcolor: '#232b38',
        rangeselector: {
          buttons: [
            { count: 12, label: '12h', step: 'hour', stepmode: 'backward' },
            { count: 1, label: '1d', step: 'day', stepmode: 'backward' },
            { count: 7, label: '7d', step: 'day', stepmode: 'backward' },
            { count: 1, label: '1m', step: 'month', stepmode: 'backward' },
            { step: 'all', label: 'All' },
          ],
          bgcolor: '#12161f',
          activecolor: '#f7931a',
          font: { color: '#b6bfcd', size: 10 },
          borderwidth: 0,
          x: 1,
          xanchor: 'right',
          y: 1.16,
        },
      },
      yaxis: { gridcolor: '#232b38', tickprefix: '$', domain: on.volume ? [0.22, 1] : [0, 1] },
      yaxis2: { domain: [0, 0.16], visible: false },
      legend: { orientation: 'h', y: 1.16, x: 0 },
      dragmode: 'zoom',
      hovermode: 'x unified',
      shapes,
    };

    window.Plotly.react(node, data, layout, { responsive: true, displaylogo: false });

    return () => {
      if (node) window.Plotly.purge(node);
    };
  }, [result, on, indicators]);

  const fl = result.forming_leg;
  const activeIndicators = [
    indicators.sma.on && 'SMA',
    indicators.ema.on && 'EMA',
    indicators.bb.on && 'BB',
    indicators.vwap.on && 'VWAP',
    indicators.donchian.on && 'Donchian',
  ].filter(Boolean) as string[];

  return (
    <div className="card" style={{ padding: '0.5rem' }}>
      <div className="chart-toolbar">
        <div className="chart-toggles">
          {OVERLAYS.map(({ key, label, help }) => (
            <span key={key} className="chart-toggle-wrap">
              <button
                className={`chart-toggle${on[key] ? ' active' : ''}`}
                onClick={() => toggle(key)}
              >
                {label}
              </button>
              <HelpDot>{help}</HelpDot>
            </span>
          ))}
          <span className="chart-toggle-wrap">
            <button
              className={`chart-toggle${activeIndicators.length ? ' active' : ''}`}
              onClick={() => setShowIndicators(!showIndicators)}
            >
              ƒ Indicators{activeIndicators.length ? ` · ${activeIndicators.join(' ')}` : ''}
            </button>
            <HelpDot>Classic tools from familiar charting apps — Bollinger Bands, moving averages, VWAP, Donchian channels. Your setup is remembered.</HelpDot>
          </span>
        </div>
        {fl && (
          <span className="forming-badge" title={`Leg still forming after the last confirmed pivot (since ${fmtTime(fl.start_timestamp)})`}>
            <span className="forming-dot" /> forming {fl.direction} {fl.percent_change >= 0 ? '+' : ''}{fl.percent_change.toFixed(2)}%
            <HelpDot>The move happening right now. It is unfinished — no reversal has confirmed it — so it is drawn dashed and never used as history.</HelpDot>
          </span>
        )}
      </div>
      {result.candles_resampled && (
        <div style={{ fontSize: '0.68rem', color: 'var(--text-faint)', padding: '0.2rem 0.5rem' }}>
          Candles resampled for display — pivots and legs remain exact.
        </div>
      )}
      {showIndicators && (
        <div className="indicator-popover">
          <div className="ind-row">
            <label className="check-row" style={{ marginBottom: 0 }}>
              <input type="checkbox" checked={indicators.bb.on}
                onChange={(e) => patchIndicator('bb', { on: e.target.checked })} />
              Bollinger Bands
              <HelpDot>{INDICATOR_HELP.bb}</HelpDot>
            </label>
            <label className="ind-field">period
              <input type="number" min="2" max="200" value={indicators.bb.period}
                onChange={(e) => patchIndicator('bb', { period: Number(e.target.value) || 20 })} />
            </label>
            <label className="ind-field">σ
              <input type="number" min="0.5" max="4" step="0.5" value={indicators.bb.mult}
                onChange={(e) => patchIndicator('bb', { mult: Number(e.target.value) || 2 })} />
            </label>
          </div>
          <div className="ind-row">
            <label className="check-row" style={{ marginBottom: 0 }}>
              <input type="checkbox" checked={indicators.sma.on}
                onChange={(e) => patchIndicator('sma', { on: e.target.checked })} />
              SMA
              <HelpDot>{INDICATOR_HELP.sma}</HelpDot>
            </label>
            <label className="ind-field">period
              <input type="number" min="2" max="400" value={indicators.sma.period}
                onChange={(e) => patchIndicator('sma', { period: Number(e.target.value) || 20 })} />
            </label>
          </div>
          <div className="ind-row">
            <label className="check-row" style={{ marginBottom: 0 }}>
              <input type="checkbox" checked={indicators.ema.on}
                onChange={(e) => patchIndicator('ema', { on: e.target.checked })} />
              EMA
              <HelpDot>{INDICATOR_HELP.ema}</HelpDot>
            </label>
            <label className="ind-field">period
              <input type="number" min="2" max="400" value={indicators.ema.period}
                onChange={(e) => patchIndicator('ema', { period: Number(e.target.value) || 21 })} />
            </label>
          </div>
          <div className="ind-row">
            <label className="check-row" style={{ marginBottom: 0 }}>
              <input type="checkbox" checked={indicators.vwap.on}
                onChange={(e) => patchIndicator('vwap', { on: e.target.checked })} />
              VWAP
              <HelpDot>{INDICATOR_HELP.vwap}</HelpDot>
            </label>
          </div>
          <div className="ind-row">
            <label className="check-row" style={{ marginBottom: 0 }}>
              <input type="checkbox" checked={indicators.donchian.on}
                onChange={(e) => patchIndicator('donchian', { on: e.target.checked })} />
              Donchian
              <HelpDot>{INDICATOR_HELP.donchian}</HelpDot>
            </label>
            <label className="ind-field">period
              <input type="number" min="2" max="200" value={indicators.donchian.period}
                onChange={(e) => patchIndicator('donchian', { period: Number(e.target.value) || 20 })} />
            </label>
          </div>
          <div style={{ fontSize: '0.64rem', color: 'var(--text-faint)' }}>
            Settings are saved in this browser. Indicators are visual aids only — they play no part in the decision engine.
          </div>
        </div>
      )}
      <div ref={el} />
    </div>
  );
}
