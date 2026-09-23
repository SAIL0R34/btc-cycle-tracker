import type { StructureDiscovery } from '../api/client';

const tone = (direction: string) => direction === 'bullish' ? '#2ecc71' : direction === 'bearish' ? '#e74c3c' : '#60a5fa';

export default function StructureDiscoveries({ discoveries }: { discoveries: StructureDiscovery[] }) {
  if (!discoveries.length) return null;
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.7rem' }}>
        <h3 style={{ margin: 0 }}>Structures you may have missed</h3>
        <span style={{ fontSize: '0.68rem', color: 'var(--text-faint)' }} title="Detected from confirmed pivots only; % is evidence strength, not outcome probability">
          Confirmed pivots only · % = evidence strength
        </span>
      </div>
      <div className="tile-grid">
        {discoveries.slice(0, 6).map(item => (
          <div className="tile" key={item.discovery_id} style={{ borderLeft: `3px solid ${tone(item.direction)}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.4rem' }}>
              <strong style={{ fontSize: '0.82rem' }}>{item.title}</strong>
              <span style={{ fontSize: '0.65rem', color: tone(item.direction) }}>{Math.round(item.confidence * 100)}%</span>
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
              {item.status} · {item.direction}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
              {item.evidence[0]}
            </div>
            {Object.keys(item.measurements).length > 0 && (
              <div style={{ fontSize: '0.66rem', color: 'var(--text-faint)', marginTop: '0.25rem' }}>
                {Object.entries(item.measurements).slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(' · ')}
              </div>
            )}
            {item.invalidation_price != null && (
              <div style={{ fontSize: '0.66rem', color: 'var(--text-faint)', marginTop: '0.3rem' }} title="Price at which this structure is invalidated by the detector">
                Invalidation ${item.invalidation_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
