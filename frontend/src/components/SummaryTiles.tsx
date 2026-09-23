import type { ReactNode } from 'react';
import type { Summary, Metadata } from '../api/client';
import HelpDot from './HelpDot';

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

function fmtMinutes(v: number): string {
  if (!Number.isFinite(v)) return '—';
  if (v >= 1440) return `${(v / 1440).toFixed(1)}d`;
  if (v >= 60) return `${(v / 60).toFixed(1)}h`;
  return `${Math.round(v)}m`;
}

function effLabel(v: number): string {
  if (v >= 0.6) return 'trending';
  if (v >= 0.3) return 'mixed';
  return 'choppy';
}

export default function SummaryTiles({ summary, metadata }: { summary: Summary; metadata: Metadata }) {
  const netPositive = summary.net_change_pct >= 0;
  const tiles: Array<{ label: string; help?: string; value: ReactNode; sub: string }> = [
    {
      label: 'Net move',
      help: 'Total price change from the start to the end of the window — the one number most people mean by "how did it do".',
      value: <span style={{ color: netPositive ? 'var(--up)' : 'var(--down)' }}>{fmtPct(summary.net_change_pct)}</span>,
      sub: `${metadata.total_pivots} pivots · ${metadata.total_candles} candles`,
    },
    {
      label: 'Efficiency',
      help: 'How straight the path was. 1.0 = one clean push to the end; near 0 = lots of back-and-forth going nowhere. Also called the Kaufman efficiency ratio: |net move| ÷ total distance travelled.',
      value: summary.efficiency_ratio.toFixed(2),
      sub: `${effLabel(summary.efficiency_ratio)} — |net| ÷ path travelled`,
    },
    {
      label: 'Realized vol',
      help: 'The typical candle-to-candle move, in %. Higher = jumpier market. Bigger swings should be expected (and sized for) when this is high.',
      value: `${summary.realized_vol_pct_per_bar.toFixed(2)}%`,
      sub: 'per bar, close-to-close',
    },
    {
      label: 'Max drawdown',
      help: 'The worst fall from a local high to the following low within the window — what holding through this period actually felt like.',
      value: `−${summary.max_drawdown_pct.toFixed(2)}%`,
      sub: 'peak-to-trough on closes',
    },
    {
      label: 'Legs',
      help: 'A leg is one full move between two turnarounds (a swing). This counts how many completed swings the detector found.',
      value: String(summary.total_legs),
      sub: `avg ${fmtPct(summary.avg_percent_change)} · median ${fmtPct(summary.median_percent_change)}`,
    },
    {
      label: 'Duration',
      help: 'How long a typical swing lasted, measured on completed legs. Median is shown because one huge swing can skew an average.',
      value: fmtMinutes(summary.avg_duration_minutes),
      sub: `median ${fmtMinutes(summary.median_duration_minutes)} per leg`,
    },
    {
      label: 'Up / Down',
      help: 'How many upward vs downward swings were counted, with their average sizes.',
      value: `${summary.up_legs_count} / ${summary.down_legs_count}`,
      sub: `avg ${fmtPct(summary.up_legs_avg_change)} / ${fmtPct(summary.down_legs_avg_change)}`,
    },
    {
      label: 'Magnitude skew',
      help: 'Do up-moves or down-moves carry more force? +1 = bulls hit much harder, −1 = bears do, 0 = evenly matched. The small "amp·dur corr" number underneath asks a different question: do bigger swings take longer? +1 = always, 0 = no relationship.',
      value: (
        <span style={{ color: summary.up_down_asymmetry >= 0 ? 'var(--up)' : 'var(--down)' }}>
          {summary.up_down_asymmetry >= 0 ? '+' : ''}{summary.up_down_asymmetry.toFixed(2)}
        </span>
      ),
      sub: `amp·dur corr ${summary.amplitude_duration_correlation.toFixed(2)}`,
    },
    {
      label: 'Extremes',
      help: 'The biggest single up-swing and down-swing in the window.',
      value: fmtPct(summary.max_percent_change),
      sub: `worst ${fmtPct(summary.min_percent_change)}`,
    },
  ];

  return (
    <div className="tile-grid">
      {tiles.map((t) => (
        <div className="tile" key={t.label}>
          <div className="label">
            {t.label}
            {t.help && <HelpDot>{t.help}</HelpDot>}
          </div>
          <div className="value">{t.value}</div>
          <div className="sub">{t.sub}</div>
        </div>
      ))}
    </div>
  );
}
