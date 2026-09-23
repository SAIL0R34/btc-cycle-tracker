/**
 * Agent pane — ported from the opportunity_pipeline AgentPanel.
 *
 * Three tabs: Chat (tool-calling assistant with confirm-before-write),
 * Live (SSE activity feed, also shows analysis runs), and History
 * (persisted transcript).
 */

import { useState, useEffect, useRef } from 'react';
import { agentApi } from '../api/client';
import type { AgentChatMessage, AgentPendingAction, AgentTraceStep, AgentStoredMessage } from '../api/client';
import { apiError } from '../lib/apiError';
import { renderMarkdown } from '../lib/markdown';

interface AgentEvent {
  id: number;
  task_id: string;
  event_type: string;
  message: string;
  created_at: string;
}

interface AgentStatus {
  active: boolean;
  active_task: { task_id: string; started_at: string } | null;
  recent_events: AgentEvent[];
  history: AgentEvent[];
}

type View = 'chat' | 'log' | 'history';

interface ChatEntry {
  role: 'user' | 'assistant';
  content: string;
  trace?: AgentTraceStep[];
}

const EVENT_COLORS: Record<string, string> = {
  started: '#2563eb',
  subtask_started: '#7c3aed',
  subtask_completed: '#10b981',
  retry: '#f59e0b',
  completed: '#10b981',
  blocked: '#ef4444',
  log: '#6b7280',
};

const EVENT_ICONS: Record<string, string> = {
  started: '▶',
  subtask_started: '◆',
  subtask_completed: '✓',
  retry: '↻',
  completed: '✅',
  blocked: '❌',
  log: '›',
};

export default function AgentPanel({ onDataChanged }: { onDataChanged?: () => void }) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [collapsed, setCollapsed] = useState(true);
  const [view, setView] = useState<View>('chat');
  const logTopRef = useRef<HTMLDivElement>(null);

  // ── Chat state ─────────────────────────────────────────────
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<AgentPendingAction | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  // ── Conversation history (persisted transcript) ────────────
  const [transcript, setTranscript] = useState<AgentStoredMessage[]>([]);

  function loadTranscript() {
    agentApi.getHistory().then(res => setTranscript(res.data.messages || [])).catch(() => {});
  }

  // Fetch initial status (for the Live activity tab)
  useEffect(() => {
    agentApi.getStatus()
      .then(res => setStatus(res.data as AgentStatus))
      .catch(() => {});
  }, []);

  // Seed the Chat tab from the persisted transcript so a conversation resumes
  // across refreshes, and populate the History tab.
  useEffect(() => {
    agentApi.getHistory().then(res => {
      const stored = res.data.messages || [];
      setTranscript(stored);
      setMessages(stored.map(m => ({ role: m.role, content: m.content })));
    }).catch(() => {});
  }, []);

  // SSE stream for real-time events
  useEffect(() => {
    const es = new EventSource('/api/agent/events/stream');
    es.onmessage = (e) => {
      try {
        const event: AgentEvent = JSON.parse(e.data);
        setStatus(prev => {
          if (!prev) return prev;
          const isActive = event.event_type === 'started'
            ? true
            : (event.event_type === 'completed' || event.event_type === 'blocked')
              ? false
              : prev.active;
          return {
            ...prev,
            active: isActive,
            active_task: event.event_type === 'started'
              ? { task_id: event.task_id, started_at: event.created_at }
              : (event.event_type === 'completed' || event.event_type === 'blocked')
                ? null
                : prev.active_task,
            recent_events: [event, ...prev.recent_events].slice(0, 50),
            history: (event.event_type === 'completed' || event.event_type === 'blocked')
              ? [event, ...prev.history].slice(0, 10)
              : prev.history,
          };
        });
      } catch {
        /* ignore malformed frames */
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, []);

  useEffect(() => {
    logTopRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [status?.recent_events.length]);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, busy, pending]);

  const events = status?.recent_events || [];

  // ── Chat actions ───────────────────────────────────────────
  function toPayload(entries: ChatEntry[]): AgentChatMessage[] {
    return entries.map(({ role, content }) => ({ role, content }));
  }

  async function runUserMessage(text: string) {
    const t = text.trim();
    if (!t || busy) return;
    const next = [...messages, { role: 'user' as const, content: t }];
    setMessages(next);
    setInput('');
    setPending(null);
    await runTurn(toPayload(next));
  }

  function send() {
    runUserMessage(input);
  }

  async function runTurn(payload: AgentChatMessage[], confirm?: { tool: string; args: Record<string, unknown> }) {
    setBusy(true);
    try {
      const res = await agentApi.chat(payload, confirm);
      const data = res.data;
      if (data.type === 'confirm' && data.pending) {
        setPending(data.pending);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: data.content || 'Done.', trace: data.trace }]);
        loadTranscript();
        // A confirmed write may have re-run the analysis or changed config —
        // let the dashboard refresh itself.
        if (confirm && onDataChanged) onDataChanged();
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${apiError(err, 'The agent request failed.')}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function confirmAction() {
    if (!pending || busy) return;
    const action = pending;
    setPending(null);
    setMessages(prev => [...prev, { role: 'assistant', content: `✓ Confirmed: ${action.summary}` }]);
    await runTurn(toPayload(messages), { tool: action.tool, args: action.args });
  }

  function cancelAction() {
    if (!pending) return;
    const action = pending;
    setPending(null);
    setMessages(prev => [...prev, { role: 'assistant', content: `Cancelled: ${action.summary}` }]);
  }

  async function clearConversation() {
    if (!window.confirm('Clear the saved conversation history?')) return;
    try {
      await agentApi.clearHistory();
      setTranscript([]);
      setMessages([]);
    } catch {
      /* ignore */
    }
  }

  // Refresh the transcript whenever the History tab is opened.
  useEffect(() => {
    if (view === 'history') loadTranscript();
  }, [view]);

  return (
    <div className="agent-panel" style={{
      position: 'fixed',
      bottom: 0,
      right: 0,
      width: collapsed ? '280px' : 'min(420px, 100vw)',
      maxHeight: collapsed ? '40px' : '60vh',
      height: collapsed ? '40px' : (view === 'chat' ? '60vh' : 'auto'),
      background: 'var(--bg-secondary)',
      borderTop: '1px solid var(--border-subtle)',
      borderLeft: '1px solid var(--border-subtle)',
      borderTopLeftRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-float)',
      display: 'flex',
      flexDirection: 'column',
      transition: 'width 0.25s ease, max-height 0.25s ease',
      zIndex: 200,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.5rem 0.75rem',
          borderBottom: collapsed ? 'none' : '1px solid var(--border-subtle)',
          cursor: 'pointer',
          flexShrink: 0,
        }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: busy || status?.active ? '#10b981' : '#6b7280',
            display: 'inline-block',
            animation: busy || status?.active ? 'pulse 2s infinite' : 'none',
          }} />
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Agent
          </span>
          {busy && <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>thinking…</span>}
          {!busy && status?.active && status.active_task && (
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              → {status.active_task.task_id}
            </span>
          )}
          {!busy && !status?.active && (
            <span style={{ fontSize: '0.7rem', color: 'var(--text-faint)' }}>idle</span>
          )}
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-faint)' }}>
          {collapsed ? '▲' : '▼'}
        </span>
      </div>

      {!collapsed && (
        <>
          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)', flexShrink: 0 }}>
            {(['chat', 'log', 'history'] as View[]).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                style={{
                  flex: 1, padding: '0.45rem', fontSize: '0.7rem', fontWeight: 600,
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: view === v ? 'var(--accent-primary)' : 'var(--text-muted)',
                  borderBottom: view === v ? '2px solid var(--accent-primary)' : '2px solid transparent',
                }}
              >
                {v === 'chat' ? 'Chat' : v === 'log' ? 'Live' : `History (${transcript.length})`}
              </button>
            ))}
          </div>

          {/* ── Chat view ── */}
          {view === 'chat' && (
            <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
              <div style={{ flex: 1, overflow: 'auto', padding: '0.6rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {messages.length === 0 && !busy && (
                  <div className="empty-state" style={{ padding: '1.5rem 1rem', border: 'none', background: 'transparent' }}>
                    <span className="empty-icon">💬</span>
                    <span className="empty-title" style={{ fontSize: '0.85rem' }}>Ask the agent</span>
                    <span className="empty-sub" style={{ fontSize: '0.75rem' }}>
                      e.g. “what's the biggest down leg this month?”, “re-run on the 1h timeframe”, or “enable moon phase analysis”.
                    </span>
                  </div>
                )}

                {messages.map((m, i) => (
                  <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: m.role === 'user' ? 'flex-end' : 'flex-start', gap: '0.25rem' }}>
                    <div
                      className={m.role === 'assistant' ? 'md-body' : undefined}
                      style={{
                        maxWidth: '85%',
                        padding: '0.5rem 0.7rem',
                        borderRadius: '0.75rem',
                        fontSize: '0.8rem',
                        lineHeight: 1.5,
                        whiteSpace: m.role === 'user' ? 'pre-wrap' : undefined,
                        wordBreak: 'break-word',
                        background: m.role === 'user' ? 'var(--accent-primary)' : 'var(--bg-muted)',
                        color: m.role === 'user' ? '#14100a' : 'var(--text-primary)',
                        borderBottomRightRadius: m.role === 'user' ? '0.2rem' : '0.75rem',
                        borderBottomLeftRadius: m.role === 'user' ? '0.75rem' : '0.2rem',
                      }}
                      {...(m.role === 'assistant' ? { dangerouslySetInnerHTML: { __html: renderMarkdown(m.content) } } : {})}
                    >
                      {m.role === 'assistant' ? undefined : m.content}
                    </div>
                    {m.trace && m.trace.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', maxWidth: '85%' }}>
                        {m.trace.map((t, ti) => (
                          <span key={ti} title={t.result} style={{
                            fontSize: '0.62rem',
                            padding: '0.1rem 0.4rem',
                            borderRadius: '999px',
                            background: t.kind === 'write' ? 'var(--warning-bg)' : 'var(--info-bg)',
                            color: t.kind === 'write' ? 'var(--warning)' : 'var(--accent-secondary)',
                            border: `1px solid ${t.kind === 'write' ? 'var(--warning-border)' : 'var(--info-border)'}`,
                            whiteSpace: 'nowrap',
                          }}>
                            {t.kind === 'write' ? '✎' : '⚲'} {t.tool}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}

                {busy && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.78rem', padding: '0.25rem' }}>
                    <span className="spinner" style={{ width: 14, height: 14 }} /> working…
                  </div>
                )}

                {/* Confirmation card for a proposed write */}
                {pending && (
                  <div style={{
                    border: '1px solid var(--warning-border)',
                    background: 'var(--warning-bg)',
                    borderRadius: 'var(--radius-md)',
                    padding: '0.6rem 0.7rem',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.5rem',
                  }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      <strong style={{ color: 'var(--warning)' }}>Confirm change:</strong> {pending.summary}
                    </div>
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontFamily: 'monospace', wordBreak: 'break-word' }}>
                      {pending.tool}({JSON.stringify(pending.args)})
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button className="btn btn-primary" style={{ flex: 1, padding: '0.35rem' }} onClick={confirmAction} disabled={busy}>Confirm</button>
                      <button className="btn btn-secondary" style={{ flex: 1, padding: '0.35rem' }} onClick={cancelAction} disabled={busy}>Cancel</button>
                    </div>
                  </div>
                )}

                <div ref={chatBottomRef} />
              </div>

              {/* Input */}
              <div style={{ display: 'flex', gap: '0.4rem', padding: '0.5rem', borderTop: '1px solid var(--border-subtle)', flexShrink: 0 }}>
                <input
                  className="input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                  placeholder={pending ? 'Confirm or cancel above…' : 'Ask or tell the agent…'}
                  disabled={busy || !!pending}
                  style={{ flex: 1, fontSize: '0.8rem' }}
                />
                <button className="btn btn-primary" onClick={send} disabled={busy || !!pending || !input.trim()} style={{ whiteSpace: 'nowrap' }}>
                  Send
                </button>
              </div>
            </div>
          )}

          {/* ── Live Log view ── */}
          {view === 'log' && (
            <div style={{ flex: 1, overflow: 'auto', padding: '0.5rem', maxHeight: '50vh' }}>
              {events.length === 0 ? (
                <div style={{ color: 'var(--text-faint)', fontSize: '0.8rem', textAlign: 'center', padding: '2rem 0' }}>
                  No agent activity yet.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <div ref={logTopRef} />
                  {events.map((ev) => (
                    <div key={ev.id} style={{
                      display: 'flex',
                      gap: '0.4rem',
                      alignItems: 'flex-start',
                      padding: '0.2rem 0.3rem',
                      borderRadius: 'var(--radius-xs)',
                      background: ev.event_type === 'log' ? 'transparent' : 'var(--bg-muted)',
                      fontSize: '0.75rem',
                    }}>
                      <span style={{ color: EVENT_COLORS[ev.event_type] || '#6b7280', fontWeight: 700, flexShrink: 0, width: '14px', textAlign: 'center' }}>
                        {EVENT_ICONS[ev.event_type] || '•'}
                      </span>
                      <span style={{
                        color: ev.event_type === 'log' ? 'var(--text-muted)' : 'var(--text-primary)',
                        fontFamily: ev.event_type === 'log' ? 'monospace' : 'inherit',
                        fontSize: ev.event_type === 'log' ? '0.7rem' : '0.75rem',
                        wordBreak: 'break-word',
                        flex: 1,
                      }}>
                        {ev.message}
                      </span>
                      <span style={{ color: 'var(--text-faint)', fontSize: '0.6rem', flexShrink: 0, whiteSpace: 'nowrap' }}>
                        {new Date(ev.created_at.replace(' ', 'T') + 'Z').toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── History view: conversation transcript ── */}
          {view === 'history' && (
            <div style={{ flex: 1, overflow: 'auto', padding: '0.5rem', maxHeight: '50vh' }}>
              {transcript.length === 0 ? (
                <div style={{ color: 'var(--text-faint)', fontSize: '0.8rem', textAlign: 'center', padding: '2rem 0' }}>
                  No conversation yet.
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.4rem' }}>
                    <button
                      onClick={clearConversation}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-faint)', fontSize: '0.68rem', textDecoration: 'underline' }}
                    >
                      Clear history
                    </button>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {transcript.map((m) => (
                      <div key={m.id} style={{
                        padding: '0.5rem 0.6rem',
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--bg-muted)',
                        borderLeft: `3px solid ${m.role === 'user' ? 'var(--accent-primary)' : 'var(--accent-secondary)'}`,
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, color: m.role === 'user' ? 'var(--accent-primary)' : 'var(--accent-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            {m.role === 'user' ? 'You' : 'Agent'}
                          </span>
                          <span style={{ fontSize: '0.62rem', color: 'var(--text-faint)' }}>
                            {new Date(m.created_at.replace(' ', 'T') + 'Z').toLocaleString()}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {m.content}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}
