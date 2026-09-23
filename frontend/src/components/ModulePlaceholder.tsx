/** Card shown when an insight module is off or its data failed to load —
 * keeps the module visible and offers a one-click enable + re-run. */
export default function ModulePlaceholder({
  title, hint, fields, onEnable, busy,
}: {
  title: string;
  hint: string;
  fields: Record<string, unknown>;
  onEnable: (fields: Record<string, unknown>) => void;
  busy: boolean;
}) {
  return (
    <div className="card">
      <div className="card-head">
        <h3 style={{ margin: 0 }}>{title}</h3>
        <span className="badge">off</span>
      </div>
      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '0 0 0.6rem' }}>{hint}</p>
      <button
        className="btn btn-secondary"
        style={{ fontSize: '0.78rem' }}
        disabled={busy}
        onClick={() => onEnable(fields)}
      >
        {busy ? 'Running…' : 'Enable & re-run'}
      </button>
    </div>
  );
}
