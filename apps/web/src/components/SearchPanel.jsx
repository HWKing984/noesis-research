import React, { useEffect, useRef, useState } from 'react';

import { EvidenceChip, EvidenceGate } from './StatusPieces.jsx';

const FILTER_FIELDS = [
  ['method', '方法', '扩散模型'],
  ['task', '任务', 'image generation'],
  ['dataset', '数据集', 'ImageNet'],
  ['author', '作者', ''],
  ['venue', '会议 / 期刊', ''],
  ['year', '年份（2015–2025）', '2015–2025'],
];

const CHEVRON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m6 9 6 6 6-6" /></svg>
);
const SEARCH_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
    <path d="M21 21l-4.35-4.35M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0z" />
  </svg>
);

/** 检索表单（检索优先版）：主输入 = 题名关键词；其余字段收进筛选弹层。
 *  字段名与后端 `search_parameters()` 的白名单一一对应，未变。 */
export function SearchBar({ value, onChange, onSubmit, busy }) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const popRef = useRef(null);

  // 点外部收起弹层
  useEffect(() => {
    if (!filtersOpen) return undefined;
    const onDown = (event) => {
      if (popRef.current && !popRef.current.contains(event.target)) setFiltersOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [filtersOpen]);

  const activeCount = FILTER_FIELDS.filter(([key]) => (value[key] || '').trim()).length;
  const setField = (key, v) => onChange({ ...value, [key]: v });

  return (
    <form
      className="lib-searchbar"
      data-testid="search-form"
      onSubmit={(event) => {
        event.preventDefault();
        setFiltersOpen(false);
        onSubmit();
      }}
    >
      <div className="lib-search-row" ref={popRef}>
        <div className="lib-search-wrap">
          <span className="lib-search-ico">{SEARCH_ICON}</span>
          <input
            name="q"
            value={value.q ?? ''}
            onChange={(event) => setField('q', event.target.value)}
            className="lib-search-input"
            placeholder="输入题名、方法、作者……"
            aria-label="检索关键词"
            maxLength={200}
          />
        </div>
        <button
          type="button"
          className="lib-btn"
          data-testid="filter-toggle"
          aria-expanded={filtersOpen ? 'true' : 'false'}
          onClick={() => setFiltersOpen((prev) => !prev)}
        >
          筛选
          {activeCount ? <span className="lib-btn-n">{activeCount}</span> : null}
          {CHEVRON}
        </button>
        <button type="submit" className="lib-go" data-testid="search-submit" disabled={busy}>
          {busy ? '检索中…' : '检索'}
        </button>
        {filtersOpen ? (
          <div className="lib-filter-pop" data-testid="filter-popover">
            <h4>更多筛选</h4>
            <div className="lib-filter-grid">
              {FILTER_FIELDS.map(([key, label, placeholder]) => (
                <label key={key}>
                  <span>{label}</span>
                  <input
                    name={key}
                    value={value[key] ?? ''}
                    onChange={(event) => setField(key, event.target.value)}
                    placeholder={placeholder}
                    maxLength={200}
                  />
                </label>
              ))}
            </div>
            <div className="lib-filter-foot">
              <span className="lbl">每页</span>
              <select
                name="limit"
                value={value.limit ?? '10'}
                onChange={(event) => setField('limit', event.target.value)}
              >
                {['10', '15', '25'].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              <button
                type="button"
                className="lib-filter-clear"
                data-testid="filter-clear"
                onClick={() => {
                  onChange({ ...value, method: '', task: '', dataset: '', author: '', venue: '', year: '', limit: '10' });
                }}
              >
                清除全部筛选
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </form>
  );
}

/** 结果摘要行：真实来源标识 + 中文别名展开（有展开才显示）。
 *  让用户看得见**实际**发生了什么：这是固定词表展开，不是自动翻译。 */
export function AppliedEcho({ meta, count }) {
  if (!meta) return null;
  const expanded = Object.entries(meta.expandedTerms || {});
  return (
    <div className="lib-summary-row" data-testid="search-summary">
      {typeof count === 'number' ? <span className="n">{count} 篇</span> : null}
      {meta.source ? <span>source={meta.source}</span> : null}
      {meta.aliasVersion ? <span>别名表={meta.aliasVersion}</span> : null}
      {expanded.length > 0 ? (
        <span data-testid="expanded-terms">
          别名展开：
          {expanded.map(([key, terms]) => (
            <code key={key}>{key} → {terms.join(' | ')}</code>
          ))}
        </span>
      ) : null}
    </div>
  );
}

/** 检索结果列表。每条都带一个可核对的证据引用（点击可打开证据抽屉）。
 *  行容器用 div[role=button]：行内还有真 button 的证据 chip，button 嵌套 button 是非法结构。 */
export function PaperList({ papers, selectedId, onSelect, onInspect }) {
  return (
    <ul className="lib-list-shell" data-testid="paper-list" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {papers.map((paper) => {
        const active = paper.publicationId === selectedId;
        return (
          <li key={paper.publicationId}>
            <div
              role="button"
              tabIndex={0}
              onClick={() => onSelect(paper.publicationId)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(paper.publicationId);
                }
              }}
              data-testid="paper-item"
              data-publication-id={paper.publicationId}
              aria-current={active ? 'true' : undefined}
              className={`lib-row ${active ? 'is-active' : ''}`}
            >
              <div className="lib-row-main">
                <span className="lib-row-title">{paper.title}</span>
                <span className="lib-row-meta">
                  <span>{paper.year}</span>
                  <span className="mono">{paper.publicationId}</span>
                </span>
              </div>
              <div className="lib-row-side">
                <span className="lib-badge">{paper.modelApplied ? '已建模型' : '仅书目'}</span>
                <EvidenceChip
                  reference={paper.evidence}
                  compact
                  context={{ title: paper.title, publicationId: paper.publicationId }}
                  onInspect={onInspect}
                />
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export { EvidenceGate };
