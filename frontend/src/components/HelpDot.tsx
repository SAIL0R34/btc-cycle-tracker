import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { ReactNode } from 'react';

/**
 * A small "?" affordance that reveals a plain-English explanation on hover
 * (or keyboard focus). The tooltip is rendered in a portal at the viewport
 * level and opens to the RIGHT of the "?" (flipping left only when the
 * viewport edge leaves no room), so it is never clipped by the sidebar,
 * cards, or tables — no matter where the term sits.
 */
export default function HelpDot({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; flip: boolean } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);

  function show() {
    const dot = ref.current;
    if (!dot) return;
    const rect = dot.getBoundingClientRect();
    const margin = 9;
    const tipWidth = 258; // matches the CSS max-width
    let left = rect.right + margin;
    let flip = false;
    if (left + tipWidth > window.innerWidth - 8) {
      // No room on the right — flip to the left of the "?".
      left = Math.max(8, rect.left - margin - tipWidth);
      flip = true;
    }
    const top = Math.min(Math.max(rect.top + rect.height / 2, 60), window.innerHeight - 24);
    setPos({ top, left, flip });
    setOpen(true);
  }

  function hide() {
    setOpen(false);
  }

  return (
    <>
      <span
        ref={ref}
        className="helpdot"
        tabIndex={0}
        role="note"
        aria-label="Explanation"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
      >
        <span className="helpdot-mark" aria-hidden="true">?</span>
      </span>
      {open && pos && createPortal(
        <div
          className={`helpdot-float${pos.flip ? ' flip' : ''}`}
          style={{ top: pos.top, left: pos.left }}
          role="tooltip"
        >
          {children}
        </div>,
        document.body,
      )}
    </>
  );
}
