import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { createResearchApi, describeApiError } from './lib/api.js';
import { SearchBar, AppliedEcho, PaperList } from './components/SearchPanel.jsx';
import { DetailPanel, GraphPanel } from './components/InspectorPanel.jsx';
import {
  BoundaryNotice,
  EmptyState,
  ErrorBanner,
  GraphHeader,
  Loading,
} from './components/StatusPieces.jsx';

const EMPTY_FORM = {
  q: '',
  method: '',
  task: '',
  dataset: '',
  author: '',
  venue: '',
  year: '',
  limit: '10',
};

const TABS = [
  { key: 'detail', label: '论文详情' },
  { key: 'graph', label: '局部图谱' },
];

/** 只把非空字段送给后端；空字段一律不发，保证回显与实参一致。 */
function toSearchParams(form) {
  const params = { limit: form.limit || '10', offset: 0 };
  for (const key of ['q', 'method', 'task', 'dataset', 'author', 'venue', 'year']) {
    const value = (form[key] || '').trim();
    if (value) params[key] = value;
  }
  return params;
}

export default function App({ api: injectedApi }) {
  const api = useMemo(() => injectedApi || createResearchApi(), [injectedApi]);

  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);

  const [form, setForm] = useState(EMPTY_FORM);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [result, setResult] = useState(null);

  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [detailBusy, setDetailBusy] = useState(false);

  const [graphMode, setGraphMode] = useState('paper');
  const [slice, setSlice] = useState(null);
  const [graphBusy, setGraphBusy] = useState(false);
  const [tab, setTab] = useState('detail');

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setHealthError(null);
    } catch (error) {
      setHealth(null);
      setHealthError(describeApiError(error));
    }
  }, [api]);

  useEffect(() => {
    loadHealth();
  }, [loadHealth]);

  const runSearch = useCallback(async () => {
    setSearching(true);
    setSearchError(null);
    try {
      const payload = await api.searchPapers(toSearchParams(form));
      setResult(payload);
      setSelectedId(null);
      setDetail(null);
      setSlice(null);
    } catch (error) {
      // 失败时清掉结果，绝不保留上一次的列表冒充本次结果
      setResult(null);
      setSearchError(describeApiError(error));
    } finally {
      setSearching(false);
    }
  }, [api, form]);

  const selectPaper = useCallback(
    async (publicationId) => {
      setSelectedId(publicationId);
      setDetail(null);
      setSlice(null);
      setDetailError(null);
      setDetailBusy(true);
      setTab('detail');
      try {
        setDetail(await api.getPaper(publicationId));
      } catch (error) {
        setDetailError(describeApiError(error));
      } finally {
        setDetailBusy(false);
      }
    },
    [api],
  );

  const loadGraph = useCallback(
    async (publicationId, mode) => {
      if (!publicationId) return;
      setGraphBusy(true);
      try {
        setSlice(await api.graphNeighbors(publicationId, mode, 15));
      } catch (error) {
        setSlice(null);
        setDetailError(describeApiError(error));
      } finally {
        setGraphBusy(false);
      }
    },
    [api],
  );

  useEffect(() => {
    if (tab === 'graph' && selectedId) loadGraph(selectedId, graphMode);
  }, [tab, selectedId, graphMode, loadGraph]);

  const papers = result?.data || [];

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-[var(--line)] bg-[var(--panel)] px-5 py-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[15px] font-semibold">NOESIS Research</h1>
          <span className="text-[12px] text-[var(--ink-muted)]">
            基于科学文献知识图谱的研究工作区
          </span>
          <span className="mono ml-auto text-[11px] text-[var(--ink-muted)]">{api.base}</span>
        </div>
      </header>

      <GraphHeader health={health} error={healthError} />

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col border-r border-[var(--line)]">
          <SearchBar value={form} onChange={setForm} onSubmit={runSearch} busy={searching} />
          <AppliedEcho meta={result?.meta} />
          <ErrorBanner error={searchError} onRetry={runSearch} />
          <BoundaryNotice />

          <div className="min-h-0 flex-1 overflow-auto">
            {searching ? <Loading label="正在检索图谱…" /> : null}
            {!searching && !result && !searchError ? (
              <EmptyState>
                输入条件后点「检索」。检索结果里的每一条都带来源引用，可以直接核对。
              </EmptyState>
            ) : null}
            {!searching && result && papers.length === 0 ? (
              <EmptyState data-testid="empty-result">
                图谱里没有匹配的记录（这是**真实的空结果**，不是服务不可用）。
              </EmptyState>
            ) : null}
            {!searching && papers.length > 0 ? (
              <PaperList papers={papers} selectedId={selectedId} onSelect={selectPaper} />
            ) : null}
          </div>
        </div>

        <aside className="flex w-[560px] min-w-0 flex-col bg-[var(--bg)]">
          <nav className="flex gap-1 border-b border-[var(--line)] bg-[var(--panel)] px-5 pt-2">
            {TABS.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                data-testid="tab"
                data-tab={item.key}
                data-active={tab === item.key ? 'true' : 'false'}
                className={`-mb-px border-b-2 px-3 py-1.5 text-[12px] ${
                  tab === item.key
                    ? 'border-[var(--accent)] font-medium text-[var(--accent)]'
                    : 'border-transparent text-[var(--ink-muted)]'
                }`}
              >
                {item.label}
              </button>
            ))}
            {selectedId ? (
              <span className="mono ml-auto pb-1.5 text-[10px] text-[var(--ink-muted)]">
                {selectedId}
              </span>
            ) : null}
          </nav>

          <ErrorBanner error={detailError} />

          <div className="min-h-0 flex-1 overflow-auto">
            {!selectedId ? (
              <EmptyState>左侧选择一篇论文后，这里显示详情或局部图谱。</EmptyState>
            ) : null}
            {selectedId && tab === 'detail' ? (
              detailBusy ? <Loading label="正在读取论文详情…" /> : <DetailPanel detail={detail} />
            ) : null}
            {selectedId && tab === 'graph' ? (
              <GraphPanel
                slice={slice}
                busy={graphBusy}
                mode={graphMode}
                onModeChange={setGraphMode}
                onRefresh={() => loadGraph(selectedId, graphMode)}
              />
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}
