import React from 'react';

import { EvidenceChip, EvidenceGate } from './StatusPieces.jsx';

/** 检索表单。字段与后端 `search_parameters()` 的白名单一一对应。 */
export function SearchBar({ value, onChange, onSubmit, busy }) {
  const field = (name, label, extra = {}) => (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] text-[var(--ink-muted)]">{label}</span>
      <input
        name={name}
        value={value[name] ?? ''}
        onChange={(event) => onChange({ ...value, [name]: event.target.value })}
        className="h-8 rounded border border-[var(--line)] bg-[var(--panel)] px-2 text-[13px] outline-none focus:border-[var(--accent)]"
        {...extra}
      />
    </label>
  );

  return (
    <form
      className="border-b border-[var(--line)] bg-[var(--panel)] px-5 py-3"
      data-testid="search-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {field('q', '关键词（题名）', { placeholder: 'transformer / 知识图谱' })}
        {field('method', '方法', { placeholder: '扩散模型' })}
        {field('task', '任务', { placeholder: 'image generation' })}
        {field('dataset', '数据集', { placeholder: 'ImageNet' })}
        {field('author', '作者', {})}
        {field('venue', '会议 / 期刊', {})}
        {field('year', '年份（2015–2025）', { inputMode: 'numeric' })}
        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-[var(--ink-muted)]">条数（1–25）</span>
          <input
            name="limit"
            value={value.limit ?? '10'}
            onChange={(event) => onChange({ ...value, limit: event.target.value })}
            inputMode="numeric"
            className="h-8 rounded border border-[var(--line)] bg-[var(--panel)] px-2 text-[13px] outline-none focus:border-[var(--accent)]"
          />
        </label>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="h-8 rounded bg-[var(--accent)] px-4 text-[13px] font-medium text-white disabled:opacity-50"
          data-testid="search-submit"
        >
          {busy ? '检索中…' : '检索'}
        </button>
        <span className="text-[11px] text-[var(--ink-muted)]">
          中文仅在 22 条固定别名上做精确展开（如「扩散模型」→ diffusion model(s)）；未知中文原样检索。
        </span>
      </div>
    </form>
  );
}

/** 参数回显：让用户看得见**实际**用了什么参数、展开了哪些别名。 */
export function AppliedEcho({ meta }) {
  if (!meta) return null;
  const applied = Object.entries(meta.applied || {});
  const expanded = Object.entries(meta.expandedTerms || {});
  return (
    <div
      className="border-b border-[var(--line)] bg-[var(--bg)] px-5 py-2 text-[11px] text-[var(--ink-muted)]"
      data-testid="applied-echo"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span>实参回显：</span>
        {applied.length === 0 ? <span>（无）</span> : null}
        {applied.map(([key, val]) => (
          <code key={key} className="mono rounded bg-[var(--panel)] px-1.5 py-0.5 text-[var(--ink)]">
            {key}={val}
          </code>
        ))}
        <span className="ml-2">source={meta.source}</span>
        {meta.aliasVersion ? <span>别名表={meta.aliasVersion}</span> : null}
      </div>
      {expanded.length > 0 ? (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1" data-testid="expanded-terms">
          <span>别名展开：</span>
          {expanded.map(([key, terms]) => (
            <code key={key} className="mono rounded bg-[var(--panel)] px-1.5 py-0.5 text-[var(--ink)]">
              {key} → {terms.join(' | ')}
            </code>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** 检索结果列表。每条都带一个可核对的证据引用（点击可打开证据抽屉）。 */
export function PaperList({ papers, selectedId, onSelect, onInspect }) {
  return (
    <ul className="divide-y divide-[var(--line)]" data-testid="paper-list">
      {papers.map((paper) => {
        const active = paper.publicationId === selectedId;
        return (
          <li key={paper.publicationId}>
            <button
              type="button"
              onClick={() => onSelect(paper.publicationId)}
              data-testid="paper-item"
              data-publication-id={paper.publicationId}
              aria-current={active ? 'true' : undefined}
              className={`w-full px-5 py-3 text-left transition-colors ${
                active ? 'bg-[var(--accent-soft)]' : 'bg-[var(--panel)] hover:bg-[var(--bg)]'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <span className="text-[13px] font-medium leading-snug">{paper.title}</span>
                <span className="shrink-0 text-[11px] text-[var(--ink-muted)]">{paper.year}</span>
              </div>
              <div className="mono mt-1 text-[11px] text-[var(--ink-muted)]">{paper.publicationId}</div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <EvidenceChip
                  reference={paper.evidence}
                  compact
                  context={{ title: paper.title, publicationId: paper.publicationId }}
                  onInspect={onInspect}
                />
                {paper.modelApplied ? (
                  <span className="rounded bg-[var(--bg)] px-1.5 py-0.5 text-[10px] text-[var(--ink-muted)]">
                    已建模型提及
                  </span>
                ) : (
                  <span className="rounded bg-[var(--bg)] px-1.5 py-0.5 text-[10px] text-[var(--ink-muted)]">
                    仅书目
                  </span>
                )}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export { EvidenceGate };
