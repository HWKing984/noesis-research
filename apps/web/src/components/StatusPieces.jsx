import React, { useState } from 'react';
import { describeEvidence, evidenceState } from '../lib/evidence.js';

/** 顶部图谱状态条（论文库视图用）：graphId 与计数只能来自 /api/health。 */
export function GraphHeader({ health, error }) {
  if (error) {
    return (
      <div className="top" data-testid="graph-header-error">
        <span style={{ color: 'var(--danger)' }}>图谱状态未知：{error.title}</span>
      </div>
    );
  }
  if (!health) {
    return <div className="top" data-testid="graph-header-loading">正在读取图谱状态…</div>;
  }
  return (
    <div className="top" data-testid="graph-header">
      <span className="crumb">论文库与图谱</span>
      <span className="chip">
        <span
          className="dot"
          style={{ background: health.status === 'ready' ? 'var(--success)' : 'var(--danger)' }}
        />
        {health.status}
      </span>
      <span>
        graphId <code className="mono" style={{ color: 'var(--text-primary)' }}>{health.graphId}</code>
      </span>
      {health.pinnedGraphId ? (
        <span data-testid="pin-state">
          版本锁定 <code className="mono">{String(health.pinnedGraphId).slice(0, 18)}…</code>
        </span>
      ) : (
        <span data-testid="pin-state" style={{ color: 'var(--warning)' }}>未锁定图谱版本</span>
      )}
      <span>
        书目 <b>{health.scope?.bibliographyTitles}</b> · 已建模型 <b>{health.scope?.modelTitles}</b> · 候选断言{' '}
        <b>{health.scope?.candidateAssertions}</b>
      </span>
    </div>
  );
}

/** 失败横幅：永远不把失败说成"没有结果"。 */
export function ErrorBanner({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="banner" data-testid="error-banner" data-error-kind={error.kind} role="alert">
      <div className="t">{error.title}</div>
      <div className="d">{error.detail}</div>
      {onRetry ? <button type="button" onClick={onRetry}>重试</button> : null}
    </div>
  );
}

/** 系统边界说明：把「本系统不做/做不到」直接写给用户看。 */
export function BoundaryNotice() {
  return (
    <details className="notice" data-testid="boundary-notice">
      <summary>本系统能做什么、不能做什么</summary>
      <ul>
        <li>
          图谱是<b>候选断言图</b>：方法—任务 / 方法—数据集关系为{' '}
          <code className="mono">status: candidate</code>，一律标「候选」，不会被讲成已核实事实。
        </li>
        <li>证据深度目前只有<b>题名</b>：题名级证据只能证明论文存在、题名里出现了相关词。</li>
        <li>只有书目与题名；摘要仅 75 篇，全文 0 篇，本系统不托管 PDF。</li>
        <li>没有引用数据，因此<b>不提供</b>「是否必引 / 被引次数 / 引用链 / 影响力排序」。</li>
        <li>图谱不可用时会明确报错（503），<b>不会</b>回退成"没有搜到"。</li>
      </ul>
    </details>
  );
}

/** 证据徽标：可点击，打开证据抽屉。三个维度（来源类型/深度/核验）分开显示。 */
export function EvidenceChip({ reference, compact = false, context, onInspect }) {
  const info = describeEvidence(reference);
  if (!info.citable) {
    return (
      <span
        className="chip"
        data-testid="evidence-chip"
        data-citable="false"
        style={{ color: 'var(--text-muted)' }}
      >
        无来源
      </span>
    );
  }
  const open = () => onInspect?.({ reference, context: context || null });
  return (
    <button
      type="button"
      onClick={open}
      className="chip"
      data-testid="evidence-chip"
      data-citable="true"
      data-clickable="true"
      data-source-id={info.sourceId}
      title={`${info.caveat}（点击查看证据详情）`}
    >
      <span>{info.label}</span>
      {!compact ? <span>· {info.levelLabel}</span> : null}
      <span>· {info.verificationLabel}</span>
      {info.assertionLabel ? (
        <span style={{ color: 'var(--candidate)' }}>{info.assertionLabel}</span>
      ) : null}
    </button>
  );
}

/** 一段话的证据闸门状态灯（covered / missing / not_required）。 */
export function EvidenceGate({ references, required = true, label = '引用' }) {
  const state = evidenceState(references, { required });
  const text =
    state === 'covered' ? `${label}已覆盖` : state === 'missing' ? `${label}缺失` : `${label}不适用`;
  return (
    <span className="chip" data-testid="evidence-gate" data-state={state}>
      {text}
    </span>
  );
}

export function EmptyState({ children }) {
  return <div className="empty" data-testid="empty-state">{children}</div>;
}

export function Loading({ label = '加载中…' }) {
  return <div className="empty" data-testid="loading">{label}</div>;
}

/**
 * 证据抽屉：把「它到底是什么、能证明什么、不能证明什么」讲清楚。
 * 限制说明放第一屏 —— 未支持的断言不能作为已核验结论交付。
 */
export function EvidenceDrawer({ inspection, onClose, onOpenPaper }) {
  const [opened, setOpened] = useState(false);
  if (!inspection) return null;
  const info = describeEvidence(inspection.reference);
  const context = inspection.context || {};
  const title = context.title || info.sourceId;

  return (
    <>
      <div className="mask" data-testid="evidence-drawer-backdrop" onClick={onClose} />
      <aside className="drawer" data-testid="evidence-drawer" role="dialog" aria-label="证据详情">
        <button
          type="button"
          className="close"
          data-testid="evidence-drawer-close"
          onClick={onClose}
          aria-label="关闭"
        >
          <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12" /></svg>
        </button>
        <h3>证据详情</h3>
        <div className="id">{info.sourceId || '（无来源）'}</div>

        <div className="grid" data-testid="drawer-fields">
          <div className="r"><span className="k">论文</span><span data-testid="drawer-title">{title}</span></div>
          {info.citable ? (
            <>
              <div className="r"><span className="k">来源类型</span><span>{info.label}</span></div>
              <div className="r">
                <span className="k">证据深度</span>
                <span>
                  {info.levelLabel}
                  {inspection.reference?.evidenceLevel === 'title'
                    ? <span style={{ color: 'var(--warning)' }}>（仅题名）</span>
                    : null}
                </span>
              </div>
              <div className="r"><span className="k">核验状态</span><span>{info.verificationLabel}</span></div>
              {info.assertionLabel ? (
                <div className="r">
                  <span className="k">断言状态</span>
                  <span style={{ color: 'var(--candidate)' }}>{info.assertionLabel}</span>
                </div>
              ) : null}
              {info.graphId ? (
                <div className="r"><span className="k">图谱版本</span><span className="mono">{info.graphId}</span></div>
              ) : null}
              {context.predicate ? (
                <div className="r"><span className="k">关系谓词</span><span>{context.predicate}</span></div>
              ) : null}
              {context.head || context.tail ? (
                <div className="r"><span className="k">候选关系</span><span>{context.head} → {context.tail}</span></div>
              ) : null}
            </>
          ) : (
            <div className="r"><span className="k">状态</span><span>该处没有可引用的来源。</span></div>
          )}
        </div>

        <div className="note" data-testid="drawer-caveat">{info.caveat}</div>

        <div className="acts">
          {info.publicationId && onOpenPaper ? (
            <button
              type="button"
              className="pri"
              data-testid="drawer-open-paper"
              onClick={() => { onOpenPaper(info.publicationId); onClose(); }}
            >
              查看论文详情
            </button>
          ) : null}
          {info.citable ? (
            <button
              type="button"
              data-testid="drawer-open-source"
              onClick={() => {
                window.open(`https://dblp.org/search?q=${encodeURIComponent(info.sourceId)}`, '_blank', 'noopener');
                setOpened(true);
              }}
            >
              {opened ? '已在 DBLP 打开' : '在 DBLP 打开来源'}
            </button>
          ) : null}
        </div>
      </aside>
    </>
  );
}
