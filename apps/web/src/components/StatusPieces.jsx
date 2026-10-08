import React from 'react';
import {
  EVIDENCE_STATES,
  describeEvidence,
  evidenceState,
} from '../lib/evidence.js';

/** 顶部图谱状态条：graphId 与 scope 计数**只能**来自 /api/health。 */
export function GraphHeader({ health, error }) {
  if (error) {
    return (
      <div className="border-b border-[var(--line)] bg-[var(--danger-soft)] px-5 py-2 text-[12px] text-[var(--danger)]">
        图谱状态未知：{error.title}
      </div>
    );
  }
  if (!health) {
    return (
      <div className="border-b border-[var(--line)] px-5 py-2 text-[12px] text-[var(--ink-muted)]">
        正在读取图谱状态…
      </div>
    );
  }
  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-[var(--line)] bg-[var(--panel)] px-5 py-2 text-[12px] text-[var(--ink-muted)]"
      data-testid="graph-header"
    >
      <span className="inline-flex items-center gap-1.5">
        <span className="size-1.5 rounded-full bg-[#1a7f37]" />
        {health.status}
      </span>
      <span>
        graphId <code className="mono text-[var(--ink)]">{health.graphId}</code>
      </span>
      {health.pinnedGraphId ? (
        <span data-testid="pin-state">
          版本锁定 <code className="mono">{health.pinnedGraphId.slice(0, 18)}…</code>
        </span>
      ) : (
        <span data-testid="pin-state" className="text-[var(--candidate)]">
          未锁定图谱版本
        </span>
      )}
      <span>
        书目 <b className="text-[var(--ink)]">{health.scope?.bibliographyTitles}</b> · 已建模型{' '}
        <b className="text-[var(--ink)]">{health.scope?.modelTitles}</b> · 候选断言{' '}
        <b className="text-[var(--ink)]">{health.scope?.candidateAssertions}</b>
      </span>
    </div>
  );
}

/** 失败横幅：永远不把失败说成"没有结果"。 */
export function ErrorBanner({ error, onRetry }) {
  if (!error) return null;
  return (
    <div
      className="mx-5 my-3 rounded-lg border border-[#f0c9c5] bg-[var(--danger-soft)] px-4 py-3 text-[13px]"
      data-testid="error-banner"
      data-error-kind={error.kind}
      role="alert"
    >
      <div className="font-medium text-[var(--danger)]">{error.title}</div>
      <div className="mt-0.5 text-[var(--ink-muted)]">{error.detail}</div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded border border-[var(--line)] bg-[var(--panel)] px-2.5 py-1 text-[12px] hover:border-[var(--ink-muted)]"
        >
          重试
        </button>
      ) : null}
    </div>
  );
}

/** 系统边界说明：这些是「本系统不做/做不到」的实情，直接写给用户看。 */
export function BoundaryNotice() {
  return (
    <details
      className="mx-5 my-3 rounded-lg border border-[var(--line)] bg-[var(--panel)] px-4 py-2.5 text-[12px] text-[var(--ink-muted)]"
      data-testid="boundary-notice"
    >
      <summary className="cursor-pointer select-none text-[12px] text-[var(--ink)]">
        本系统能做什么、不能做什么
      </summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>
          图谱是**候选断言图**，不是事实图：方法—任务 / 方法—数据集关系为 <code className="mono">status: candidate</code>
          ，一律标「候选」，不会被讲成已核实事实。
        </li>
        <li>
          证据深度目前只有<strong>题名</strong>：题名级证据只能证明「这篇论文存在、题名里出现了相关词」，
          不能证明论文真的做了某件事。
        </li>
        <li>只有书目与题名；摘要仅 75 篇，全文 0 篇，本系统不托管 PDF。</li>
        <li>没有引用数据，因此<b>不提供</b>「是否必引 / 被引次数 / 引用链 / 影响力排序」。</li>
        <li>图谱不可用时会明确报错（503），<b>不会</b>回退成"没有搜到"。</li>
      </ul>
    </details>
  );
}

/** 证据徽标：把「来源类型 / 证据深度 / 核验状态」三个维度分开显示。 */
export function EvidenceChip({ reference, compact = false }) {
  const info = describeEvidence(reference);
  if (!info.citable) {
    return (
      <span
        className="inline-flex items-center rounded border border-[var(--line)] px-1.5 py-0.5 text-[11px] text-[var(--ink-muted)]"
        data-testid="evidence-chip"
        data-citable="false"
      >
        无来源
      </span>
    );
  }
  return (
    <span
      className="inline-flex flex-wrap items-center gap-1 rounded border border-[var(--accent-soft)] bg-[var(--accent-soft)] px-1.5 py-0.5 text-[11px] text-[var(--accent)]"
      data-testid="evidence-chip"
      data-citable="true"
      data-source-id={info.sourceId}
      title={info.caveat}
    >
      <span>{info.label}</span>
      {!compact ? <span className="opacity-60">·</span> : null}
      {!compact ? <span>{info.levelLabel}</span> : null}
      <span className="opacity-60">·</span>
      <span>{info.verificationLabel}</span>
      {info.assertionLabel ? (
        <>
          <span className="opacity-60">·</span>
          <span className="rounded bg-[var(--candidate-soft)] px-1 text-[var(--candidate)]">
            {info.assertionLabel}
          </span>
        </>
      ) : null}
    </span>
  );
}

/** 一段话的证据闸门状态灯（三段式：covered / missing / not_required）。 */
export function EvidenceGate({ references, required = true, label = '引用' }) {
  const state = evidenceState(references, { required });
  const text =
    state === EVIDENCE_STATES.COVERED
      ? `${label}已覆盖`
      : state === EVIDENCE_STATES.MISSING
        ? `${label}缺失`
        : `${label}不适用`;
  const tone =
    state === EVIDENCE_STATES.COVERED
      ? 'text-[#1a7f37] border-[#bfe0c5]'
      : state === EVIDENCE_STATES.MISSING
        ? 'text-[var(--danger)] border-[#f0c9c5]'
        : 'text-[var(--ink-muted)] border-[var(--line)]';
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] ${tone}`}
      data-testid="evidence-gate"
      data-state={state}
    >
      {text}
    </span>
  );
}

export function EmptyState({ children }) {
  return (
    <div className="px-5 py-10 text-center text-[13px] text-[var(--ink-muted)]" data-testid="empty-state">
      {children}
    </div>
  );
}

export function Loading({ label = '加载中…' }) {
  return (
    <div className="px-5 py-8 text-center text-[13px] text-[var(--ink-muted)]" data-testid="loading">
      {label}
    </div>
  );
}
