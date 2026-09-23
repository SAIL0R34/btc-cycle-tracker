import type { ReactNode } from 'react';

/**
 * A draggable, hideable dashboard module wrapper.
 *
 * In customize mode a control strip appears above the module with a drag
 * handle (desktop drag-and-drop), up/down arrows (touch-friendly), and a
 * hide button. The layout itself (order + visibility) lives in App and is
 * persisted to localStorage.
 */
export default function DashboardSection<T extends string>({
  id, title, customizing, onHide, onReorder, onMove, children,
}: {
  id: T;
  title: string;
  customizing: boolean;
  onHide: (id: T) => void;
  onReorder: (draggedId: T, targetId: T) => void;
  onMove: (id: T, delta: number) => void;
  children: ReactNode;
}) {
  if (!customizing) return <>{children}</>;

  return (
    <div
      className="dash-section"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const dragged = e.dataTransfer.getData('text/module-id') as T;
        if (dragged && dragged !== id) onReorder(dragged, id);
      }}
    >
      <div
        className="dash-section-strip"
        draggable
        onDragStart={(e) => e.dataTransfer.setData('text/module-id', id)}
      >
        <span className="drag-handle" title="Drag to rearrange">⠿</span>
        <span className="dash-section-title">{title}</span>
        <span style={{ flex: 1 }} />
        <button className="strip-btn" title="Move up" onClick={() => onMove(id, -1)}>▲</button>
        <button className="strip-btn" title="Move down" onClick={() => onMove(id, 1)}>▼</button>
        <button className="strip-btn danger" title="Hide this module" onClick={() => onHide(id)}>✕ hide</button>
      </div>
      <div className="dash-section-body">{children}</div>
    </div>
  );
}
