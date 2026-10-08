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

/**
 * 证据徽标 —— **可点击**。
 *
 * 评审指出的问题（成立）：它原来只是个 `<span>`，展示了 id 却点不开，
 * 浏览器测试也只断言了属性存在，等于"每条都带可点击证据"这句话是空话。
 * 现在它是一个真按钮，点开 {@link EvidenceDrawer}，能看到来源、深度、核验状态、
 * 图谱版本，并能跳到那篇论文。
 */
export function EvidenceChip({ reference, compact = false, context, onInspect }) {
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

  const open = () => onInspect?.({ reference, context: context || null });

  if (compact) {
    return (
      <button
        type="button"
        onClick={open}
        className="inline-flex items-center gap-1 rounded border border-[var(--accent-soft)] bg-[var(--accent-soft)] px-1.5 py-0.5 text-[11px] text-[var(--accent)] hover:underline"
        data-testid="evidence-chip"
        data-citable="true"
        data-clickable="true"
        data-source-id={info.sourceId}
        title={`${info.caveat}（点击查看证据详情）`}
      >
        <span>{info.label}</span>
        <span className="opacity-60">·</span>
        <span>{info.verificationLabel}</span>
        {info.assertionLabel ? (
          <span className="rounded bg-[var(--candidate-soft)] px-1 text-[var(--candidate)]">
            {info.assertionLabel}
          </span>
        ) : null}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={open}
      className="inline-flex flex-wrap items-center gap-1 rounded border border-[var(--accent-soft)] bg-[var(--accent-soft)] px-1.5 py-0.5 text-[11px] text-[var(--accent)] hover:underline"
      data-testid="evidence-chip"
      data-clickable="true"
      data-source-id={info.sourceId}
      title={`${info.caveat}（点击查看证据详情）`}
    >
      <span>{info.label}</span>
      <span className="opacity-60">·</span>
      <span>{info.levelLabel}</span>
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
    </button>
  );
}

/**
 * 证据抽屉：点开一条证据后，把"它到底是什么、能证明什么、不能证明什么"讲清楚。
 *
 * 这里刻意把**限制说明**放在第一屏 —— 评审要求的"未支持的断言不能作为已核验结论交付"，
 * 落到 UI 上就是：题名级证据必须让人一眼看到它不能证明什么。
 */
export function EvidenceDrawer({ inspection, onClose, onOpenPaper }) {
  if (!inspection) return null;
  const info = describeEvidence(inspection.reference);
  const context = inspection.context || {};
  const title = context.title || info.sourceId;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/25"
        data-testid="evidence-drawer-backdrop"
        onClick={onClose}
      />
      <aside
        className="fixed top-0 right-0 z-50 h-full w-[420px] overflow-auto border-l border-[var(--line)] bg-[var(--panel)] px-5 py-4"
        data-testid="evidence-drawer"
        role="dialog"
        aria-label="证据详情"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-[14px] font-semibold">证据详情</h2>
          <button
            type="button"
            onClick={onClose}
            data-testid="evidence-drawer-close"
            className="rounded border border-[var(--line)] px-2 py-0.5 text-[12px] hover:border-[var(--ink-muted)]"
          >
            关闭
          </button>
        </div>

        <p className="mt-3 text-[13px] leading-snug" data-testid="drawer-title">
          {title}
        </p>

        <dl className="mt-3 space-y-2 text-[12px]" data-testid="drawer-fields">
          <Row label="来源 id">
            <code className="mono break-all text-[var(--ink)]">{info.sourceId}</code>
          </Row>
          <Row label="来源类型">{info.label}</Row>
          <Row label="证据深度">
            {info.levelLabel}
            {inspection.reference?.evidenceLevel === 'title' ? (
              <span className="ml-1 text-[var(--candidate)]">（仅题名）</span>
            ) : null}
          </Row>
          <Row label="核验状态">{info.verificationLabel}</Row>
          {info.assertionLabel ? (
            <Row label="断言状态">
              <span className="rounded bg-[var(--candidate-soft)] px-1.5 py-0.5 text-[var(--candidate)]">
                {info.assertionLabel}
              </span>
            </Row>
          ) : null}
          {info.graphId ? (
            <Row label="图谱版本">
              <code className="mono">{info.graphId}</code>
            </Row>
          ) : null}
          {context.predicate ? <Row label="关系谓词">{context.predicate}</Row> : null}
          {context.head || context.tail ? (
            <Row label="候选关系">
              {context.head} → {context.tail}
            </Row>
          ) : null}
        </dl>

        <div className="mt-3 rounded border border-[var(--candidate-soft)] bg-[var(--candidate-soft)] px-3 py-2 text-[12px] text-[var(--candidate)]">
          {info.caveat}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {info.publicationId && onOpenPaper ? (
            <button
              type="button"
              onClick={() => {
                onOpenPaper(info.publicationId);
                onClose();
              }}
              data-testid="drawer-open-paper"
              className="rounded bg-[var(--accent)] px-3 py-1.5 text-[12px] font-medium text-white"
            >
              查看论文详情
            </button>
          ) : null}
          <a
            href={`https://dblp.org/search?q=${encodeURIComponent(info.sourceId)}`}
            target="_blank"
            rel="noreferrer noopener"
            data-testid="drawer-open-source"
            className="rounded border border-[var(--line)] px-3 py-1.5 text-[12px]"
          >
            在 DBLP 打开来源
          </a>
        </div>
      </aside>
    </>
  );
}

function Row({ label, children }) {
  return (
    <div className="grid grid-cols-[84px_1fr] gap-2">
      <dt className="text-[var(--ink-muted)]">{label}</dt>
      <dd>{children}</dd>
    </div>
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
