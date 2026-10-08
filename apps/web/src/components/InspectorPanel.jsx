import React, { useMemo, useState } from 'react';

import { EvidenceChip, EvidenceGate } from './StatusPieces.jsx';
import { countCandidates } from '../lib/evidence.js';

/** 论文详情。作者身份状态、候选断言、引文草稿都原样展示，不加工成"结论"。 */
export function DetailPanel({ detail, onInspect, onOpenPaper }) {
  if (!detail) return null;
  const { publication, authors, venues, mentions, assertions, citationDraft, notice } = detail;
  const candidates = countCandidates(assertions);
  const publicationContext = {
    title: publication.title,
    publicationId: publication.publicationId,
  };

  return (
    <div className="space-y-4 px-5 py-4" data-testid="detail-panel">
      <div>
        <h2 className="text-[15px] font-semibold leading-snug" data-testid="detail-title">
          {publication.title}
        </h2>
        <div className="mono mt-1 text-[11px] text-[var(--ink-muted)]" data-testid="detail-id">
          {publication.publicationId}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <EvidenceChip
            reference={publication.evidence}
            context={publicationContext}
            onInspect={onInspect}
          />
          {publication.doi ? (
            <a
              className="text-[11px] text-[var(--accent)] underline"
              href={`https://doi.org/${publication.doi}`}
              target="_blank"
              rel="noreferrer noopener"
            >
              DOI
            </a>
          ) : null}
          {publication.dblpUrl ? (
            <a
              className="text-[11px] text-[var(--accent)] underline"
              href={publication.dblpUrl}
              target="_blank"
              rel="noreferrer noopener"
            >
              DBLP
            </a>
          ) : null}
          {publication.urls?.map((url) => (
            <a
              key={url}
              className="text-[11px] text-[var(--accent)] underline"
              href={url}
              target="_blank"
              rel="noreferrer noopener"
            >
              外链
            </a>
          ))}
        </div>
      </div>

      <Section title={`作者（${authors.length}）`}>
        <ul className="space-y-1" data-testid="author-list">
          {authors.map((author) => (
            <li key={`${author.name}-${author.position}`} className="flex flex-wrap items-center gap-2 text-[12px]">
              <span className="text-[var(--ink-muted)]">{author.position}.</span>
              <span>{author.signatureName || author.name}</span>
              {author.identityStatus ? (
                <span className="rounded bg-[var(--bg)] px-1.5 py-0.5 text-[10px] text-[var(--ink-muted)]">
                  {author.identityStatus}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`会议 / 期刊（${venues.length}）`}>
        <div className="flex flex-wrap gap-1.5 text-[12px]">
          {venues.map((venue) => (
            <span key={venue.name} className="rounded border border-[var(--line)] px-1.5 py-0.5">
              {venue.name}
            </span>
          ))}
        </div>
      </Section>

      <Section title={`实体提及（${mentions.length}）`}>
        <div className="flex flex-wrap gap-1.5" data-testid="mention-list">
          {mentions.map((mention, index) => (
            <span
              key={`${mention.text}-${index}`}
              className="rounded border border-[var(--line)] bg-[var(--panel)] px-1.5 py-0.5 text-[11px]"
            >
              {mention.text}
              <span className="ml-1 text-[10px] text-[var(--ink-muted)]">{mention.label}</span>
            </span>
          ))}
        </div>
      </Section>

      <Section
        title={`候选断言（${assertions.length}${candidates ? ` · 其中候选 ${candidates}` : ''}）`}
        hint="方法—任务 / 方法—数据集关系由模型从题名抽取，状态恒为 candidate，不是已核实事实。"
      >
        {assertions.length === 0 ? (
          <p className="text-[12px] text-[var(--ink-muted)]">本篇没有抽取到候选断言。</p>
        ) : (
          <ul className="space-y-2" data-testid="assertion-list">
            {assertions.map((assertion) => (
              <li
                key={assertion.id}
                className="rounded-lg border border-[var(--line)] bg-[var(--panel)] px-3 py-2"
                data-testid="assertion-item"
                data-status={assertion.status}
              >
                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="rounded bg-[var(--candidate-soft)] px-1.5 py-0.5 text-[11px] text-[var(--candidate)]">
                    候选
                  </span>
                  <code className="mono">{assertion.predicate}</code>
                  <span className="text-[var(--ink-muted)]">
                    {assertion.head?.text} → {assertion.tail?.text}
                  </span>
                  {assertion.confidence != null ? (
                    <span className="text-[11px] text-[var(--ink-muted)]">
                      分数 {assertion.confidence.toFixed(4)}
                      {assertion.confidenceCalibrated ? '' : '（未校准）'}
                    </span>
                  ) : null}
                </div>
                <div className="mt-1.5">
                  <EvidenceChip
                    reference={assertion.evidence}
                    context={{
                      title: assertion.evidenceText || publication.title,
                      publicationId: publication.publicationId,
                      predicate: assertion.predicate,
                      head: assertion.head?.text,
                      tail: assertion.tail?.text,
                    }}
                    onInspect={onInspect}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {citationDraft ? (
        <Section title="引文草稿" hint="这是草稿，引用前须核对原文与书目信息。">
          <p className="mono text-[11px] leading-relaxed text-[var(--ink-muted)]" data-testid="citation-draft">
            {citationDraft}
          </p>
        </Section>
      ) : null}

      {notice ? (
        <p className="rounded border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-[11px] text-[var(--ink-muted)]">
          {notice}
        </p>
      ) : null}
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <section>
      <h3 className="mb-1.5 text-[12px] font-medium">{title}</h3>
      {hint ? <p className="mb-2 text-[11px] text-[var(--ink-muted)]">{hint}</p> : null}
      {children}
    </section>
  );
}

const MODE_LABELS = {
  paper: '本篇关系',
  coauthors: '共同作者',
  methods: '共享方法',
};

/**
 * 局部知识图谱。
 *
 * 这一版用**纯 SVG 环形布局**渲染，不引入图库依赖 —— 目的是先把"节点/边/证据/边界声明"
 * 的数据通路和文案定下来。真正的图交互（缩放、力导向、点击展开）应移植 NOESIS 的
 * `GraphPanel` / `KnowledgeGraphSigma`（同为 React 18 + Vite，属同栈可移植）。
 */
export function GraphPanel({ slice, busy, mode, onModeChange, onRefresh }) {
  const layout = useMemo(() => {
    if (!slice) return null;
    const size = 360;
    const center = size / 2;
    const radius = center - 52;
    const others = slice.nodes.filter((node) => node.id !== slice.rootId);
    const positions = new Map();
    positions.set(slice.rootId, { x: center, y: center });
    others.forEach((node, index) => {
      const angle = (index / Math.max(others.length, 1)) * Math.PI * 2 - Math.PI / 2;
      positions.set(node.id, {
        x: center + Math.cos(angle) * radius,
        y: center + Math.sin(angle) * radius,
      });
    });
    return { size, positions, others };
  }, [slice]);

  return (
    <div className="px-5 py-4" data-testid="graph-panel">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {Object.keys(MODE_LABELS).map((key) => (
          <button
            key={key}
            type="button"
            disabled={busy}
            onClick={() => onModeChange(key)}
            data-testid="graph-mode"
            data-mode={key}
            data-active={mode === key ? 'true' : 'false'}
            className={`h-7 rounded border px-2.5 text-[12px] disabled:opacity-50 ${
              mode === key
                ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]'
                : 'border-[var(--line)] bg-[var(--panel)]'
            }`}
          >
            {MODE_LABELS[key]}
          </button>
        ))}
        <button
          type="button"
          onClick={onRefresh}
          disabled={busy}
          className="h-7 rounded border border-[var(--line)] bg-[var(--panel)] px-2.5 text-[12px] disabled:opacity-50"
        >
          重新载入
        </button>
        {busy ? <span className="text-[11px] text-[var(--ink-muted)]">加载中…</span> : null}
      </div>

      {slice ? (
        <>
          <div className="rounded-lg border border-[var(--line)] bg-[var(--panel)] p-2">
            <svg viewBox={`0 0 ${layout.size} ${layout.size}`} className="h-[360px] w-full" role="img" aria-label="局部知识图谱">
              {slice.edges.map((edge) => {
                const from = layout.positions.get(edge.source);
                const to = layout.positions.get(edge.target);
                if (!from || !to) return null;
                return (
                  <line
                    key={edge.id}
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke="#d9dadd"
                    strokeWidth="1"
                    data-testid="graph-edge"
                  />
                );
              })}
              {slice.nodes.map((node) => {
                const point = layout.positions.get(node.id);
                if (!point) return null;
                const isRoot = node.id === slice.rootId;
                return (
                  <g key={node.id} data-testid="graph-node" data-kind={node.kind} data-root={String(isRoot)}>
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={isRoot ? 9 : 5}
                      fill={isRoot ? 'var(--accent)' : '#9aa0a6'}
                    />
                    <text
                      x={point.x}
                      y={point.y - (isRoot ? 14 : 10)}
                      textAnchor="middle"
                      fontSize="9"
                      fill="#6b6f76"
                    >
                      {node.kind}
                      {node.props?.name || node.props?.title
                        ? ` · ${String(node.props.name || node.props.title).slice(0, 12)}`
                        : ''}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-[var(--ink-muted)]">
            <div>
              节点 <b className="text-[var(--ink)]">{slice.nodes.length}</b> · 关系{' '}
              <b className="text-[var(--ink)]">{slice.edges.length}</b> · 路径{' '}
              <b className="text-[var(--ink)]">{slice.paths.length}</b>
            </div>
            <div>
              graphId <code className="mono text-[var(--ink)]">{slice.graphId}</code>
            </div>
            <div>
              还有更多路径：{slice.hasMorePaths ? '是（已截断）' : '否'} · 极局部：
              {slice.notice?.includes('局部') ? '是' : '否'}
            </div>
          </dl>
          <p className="mt-2 rounded border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-[11px] text-[var(--ink-muted)]">
            {slice.notice}
          </p>
        </>
      ) : (
        <p className="text-[12px] text-[var(--ink-muted)]">选择一篇论文后载入局部图谱。</p>
      )}
    </div>
  );
}

export { EvidenceGate };
