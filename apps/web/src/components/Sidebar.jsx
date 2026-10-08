import React from 'react';

const CHAT_ICON = <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>;

function sinceLabel(iso) {
  if (!iso) return '';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '';
  const minutes = Math.max(0, Math.round((Date.now() - at.getTime()) / 60000));
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} 时`;
  return `${Math.round(minutes / (60 * 24))} 天`;
}

/**
 * 侧栏：品牌 / 新的研究 / 视图切换 / 会话历史（真实数据：agent 服务的运行记录）/ 图谱状态。
 * 历史里标着「持久化后可用」以外的部分一律来自真实接口，不放假数据。
 */
export default function Sidebar({ view, onView, runs, activeRunId, onOpenRun, onNewRun, agentHealth, theme, onToggleTheme }) {
  const ready = Boolean(agentHealth?.agentReady);
  const kgReady = agentHealth?.status ? agentHealth.status === 'ready' : null;
  const history = (runs || []).filter((r) => r.status !== 'running');
  return (
    <aside className="sb" data-testid="sidebar">
      <div className="sb-brand"><span className="logo">N</span>NOESIS Research</div>

      <button type="button" className="sb-new" data-testid="new-research" onClick={onNewRun}>
        <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
        新的研究
      </button>

      <button
        type="button"
        className={`sb-nav ${view === 'agent' ? 'is-active' : ''}`}
        data-testid="view-tab"
        data-view="agent"
        data-active={view === 'agent' ? 'true' : 'false'}
        onClick={() => onView('agent')}
      >
        {CHAT_ICON}
        科研助手
      </button>
      <button
        type="button"
        className={`sb-nav ${view === 'library' ? 'is-active' : ''}`}
        data-testid="view-tab"
        data-view="library"
        data-active={view === 'library' ? 'true' : 'false'}
        onClick={() => onView('library')}
      >
        <svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
        论文库与图谱
      </button>

      <div className="sb-cap">本次会话</div>
      {history.length === 0 ? (
        <div className="sb-item" style={{ cursor: 'default', color: 'var(--text-muted)' }}>
          还没有检索记录
        </div>
      ) : (
        history.map((item) => (
          <button
            key={item.runId}
            type="button"
            className={`sb-item ${item.runId === activeRunId ? 'is-active' : ''}`}
            data-testid="history-run"
            data-run-id={item.runId}
            onClick={() => onOpenRun(item.runId)}
            title={item.question}
          >
            {CHAT_ICON}
            {item.question}
            <span className="when">{sinceLabel(item.createdAt)}</span>
          </button>
        ))
      )}

      <div className="sb-foot">
        <div className="row">
          <span>
            <span className={`dot ${ready ? '' : 'is-down'}`} />
            Agent {ready ? '就绪' : '未就绪'}
          </span>
          <span className="mono">{agentHealth?.model || '—'}</span>
        </div>
        <div className="row" style={{ marginTop: 3 }}>
          <span>
            <span className={`dot ${kgReady === false ? 'is-down' : ''}`} />
            图谱 {kgReady === null ? '…' : kgReady ? '就绪' : '不可用'}
          </span>
          <button
            type="button"
            data-testid="theme-toggle"
            onClick={onToggleTheme}
            style={{ color: 'var(--text-tertiary)' }}
          >
            {theme === 'dark' ? '浅色' : '深色'}
          </button>
        </div>
        <div className="row" style={{ marginTop: 3 }}>
          <span>书目 {agentHealth?.scope?.bibliographyTitles ?? '—'}</span>
          <span>候选断言 {agentHealth?.scope?.candidateAssertions ?? '—'}</span>
        </div>
      </div>
    </aside>
  );
}
