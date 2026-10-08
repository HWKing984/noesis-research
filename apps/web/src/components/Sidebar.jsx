import React from 'react';
import SpiralMark from './SpiralMark.jsx';

const CHAT_ICON = <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>;

function sinceLabel(iso) {
  if (!iso) return '';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '';
  const minutes = Math.max(0, Math.round((Date.now() - at.getTime()) / 60000));
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} 小时前`;
  return `${Math.round(minutes / (60 * 24))} 天前`;
}

/**
 * 侧栏 —— 照搬 NOESIS：可折叠（260px ↔ 60px 图标轨）、分组导航、
 * 「对话记录」区（真实运行记录）、底部状态与主题开关。
 */
export default function Sidebar({
  view, onView, runs, activeRunId, onOpenRun, onNewRun,
  agentHealth, theme, onToggleTheme, collapsed, onToggleCollapse,
}) {
  const ready = Boolean(agentHealth?.agentReady);
  const kgReady = agentHealth?.status ? agentHealth.status === 'ready' : null;
  const history = (runs || []).filter((r) => r.status !== 'running');

  return (
    <aside className={`sidebar ${collapsed ? 'is-collapsed' : ''}`} data-testid="sidebar" data-collapsed={collapsed ? 'true' : 'false'}>
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <span className="sidebar-logo-mark"><SpiralMark size={22} strokeWidth={2} /></span>
          <span className="sidebar-logo-name">research</span>
          <button
            type="button"
            className="sidebar-toggle"
            data-testid="sidebar-toggle"
            onClick={onToggleCollapse}
            aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m11 17-5-5 5-5M18 17l-5-5 5-5" /></svg>
          </button>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-nav-group">
          <div className="sidebar-nav-group-label">研究区</div>
          <button
            type="button"
            className={`sidebar-nav-item ${view === 'agent' ? 'is-active' : ''}`}
            data-testid="view-tab"
            data-view="agent"
            data-active={view === 'agent' ? 'true' : 'false'}
            data-label="科研助手"
            onClick={() => onView('agent')}
          >
            {CHAT_ICON}
            <span>科研助手</span>
          </button>
          <button
            type="button"
            className={`sidebar-nav-item ${view === 'library' ? 'is-active' : ''}`}
            data-testid="view-tab"
            data-view="library"
            data-active={view === 'library' ? 'true' : 'false'}
            data-label="论文库与图谱"
            onClick={() => onView('library')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
            <span>论文库与图谱</span>
          </button>
        </div>
      </nav>

      <div className="sidebar-section-label">
        对话记录
        <button type="button" className="sidebar-new-btn" data-testid="new-research" onClick={onNewRun} aria-label="新的研究">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 5v14M5 12h14" /></svg>
        </button>
      </div>
      <div className="sidebar-sessions" data-testid="session-list">
        {history.length === 0 ? (
          <div className="sidebar-sessions-empty">还没有检索记录</div>
        ) : (
          history.map((item) => (
            <button
              key={item.runId}
              type="button"
              className={`session-item ${item.runId === activeRunId ? 'is-active' : ''}`}
              data-testid="history-run"
              data-run-id={item.runId}
              onClick={() => onOpenRun(item.runId)}
              title={item.question}
            >
              <span className="session-item-icon">{CHAT_ICON}</span>
              <span className="session-item-content">
                <span className="session-item-title">{item.question}</span>
                <span className="session-item-time">{sinceLabel(item.createdAt)}</span>
              </span>
            </button>
          ))
        )}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-footer-hint">
          <span className={`dot ${ready ? '' : 'is-down'}`} />
          <span>Agent {ready ? '就绪' : '未就绪'} · {agentHealth?.model || '—'}</span>
        </div>
        <button
          type="button"
          data-testid="theme-toggle"
          onClick={onToggleTheme}
          aria-label="切换深浅色"
          style={{ color: 'var(--text-tertiary)', display: 'inline-flex' }}
        >
          {theme === 'dark'
            ? <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
            : <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>}
        </button>
      </div>
    </aside>
  );
}
