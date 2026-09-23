import { useMemo, useState } from 'react';
import type { Leg, Pivot } from '../api/client';
import HelpDot from './HelpDot';

type LegSortKey = 'leg_id' | 'percent_change' | 'duration_minutes';

function fmtTime(ts: string): string {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function LegsTable({ legs }: { legs: Leg[] }) {
  const [sortKey, setSortKey] = useState<LegSortKey>('leg_id');
  const [desc, setDesc] = useState(true);

  const sorted = useMemo(() => {
    const rows = [...legs];
    rows.sort((a, b) => {
      const av = sortKey === 'percent_change' ? Math.abs(a.percent_change) : a[sortKey];
      const bv = sortKey === 'percent_change' ? Math.abs(b.percent_change) : b[sortKey];
      return desc ? bv - av : av - bv;
    });
    return rows;
  }, [legs, sortKey, desc]);

  const maxAbs = useMemo(
    () => Math.max(...legs.map((l) => Math.abs(l.percent_change)), 0.0001),
    [legs],
  );

  const header = (label: string, key: LegSortKey, help?: string) => (
    <th onClick={() => (key === sortKey ? setDesc(!desc) : (setSortKey(key), setDesc(true)))}>
      {label}{sortKey === key ? (desc ? ' ↓' : ' ↑') : ''}
      {help && <HelpDot>{help}</HelpDot>}
    </th>
  );

  return (
    <table className="data-table">
      <thead>
        <tr>
          {header('#', 'leg_id', 'Swing number, oldest first.')}
          <th>Dir</th>
          {header('Change', 'percent_change', 'How far price moved during this swing. The bar shows its size relative to the biggest swing in the window. Click to sort.')}
          {header('Duration', 'duration_minutes', 'How long the swing lasted. Click to sort.')}
          <th>Bars</th>
          <th>From</th>
          <th>To</th>
          <th>Price range</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((leg) => (
          <tr key={leg.leg_id}>
            <td>{leg.leg_id}</td>
            <td className={leg.direction === 'up' ? 'dir-up' : 'dir-down'}>{leg.direction === 'up' ? '▲' : '▼'}</td>
            <td>
              <div className="leg-cell">
                <span className={leg.direction === 'up' ? 'dir-up' : 'dir-down'}>
                  {leg.percent_change >= 0 ? '+' : ''}{leg.percent_change.toFixed(2)}%
                </span>
                <span className="leg-bar" aria-hidden="true">
                  <span
                    className={leg.direction === 'up' ? 'leg-fill up' : 'leg-fill down'}
                    style={{ width: `${(Math.abs(leg.percent_change) / maxAbs) * 100}%` }}
                  />
                </span>
              </div>
            </td>
            <td>{leg.duration_minutes >= 60 ? `${(leg.duration_minutes / 60).toFixed(1)}h` : `${Math.round(leg.duration_minutes)}m`}</td>
            <td>{leg.duration_bars}</td>
            <td>{fmtTime(leg.start_timestamp)}</td>
            <td>{fmtTime(leg.end_timestamp)}</td>
            <td>${leg.start_price.toLocaleString()} → ${leg.end_price.toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function PivotsTable({ pivots }: { pivots: Pivot[] }) {
  const rows = useMemo(() => [...pivots].reverse(), [pivots]);
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Time</th>
          <th>
            Type
            <HelpDot>Swing high = a confirmed temporary top (price turned down after it). Swing low = a confirmed temporary bottom.</HelpDot>
          </th>
          <th>Price</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p, i) => (
          <tr key={`${p.timestamp}-${i}`}>
            <td>{fmtTime(p.timestamp)}</td>
            <td className={p.pivot_type === 'swing_high' ? 'dir-up' : 'dir-down'}>
              {p.pivot_type === 'swing_high' ? 'Swing high' : 'Swing low'}
            </td>
            <td>${p.price.toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
