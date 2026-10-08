import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { createResearchApi, describeApiError } from './lib/api.js';
import AgentChat from './components/AgentChat.jsx';
import { SearchBar, AppliedEcho, PaperList } from './components/SearchPanel.jsx';
import { DetailPanel, GraphPanel } from './components/InspectorPanel.jsx';
import {
  BoundaryNotice,
  EmptyState,
  ErrorBanner,
  EvidenceDrawer,
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

/** 论文库与图谱 —— 由 agent 页面跳进来的二级视图。 */
function LibraryView({ api, initialPublicationId, onConsumeInitial }) {
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
  const [graphError, setGraphError] = useState(null);
  const [tab, setTab] = useState('detail');

  const [inspection, setInspection] = useState(null);

  // 异步请求的生命周期必须管住：先点 A 再点 B，A 的慢响应不能把 B 的详情盖掉。
  // 用 AbortController 真正取消旧请求 + 序号双重保险（取消失败也不覆盖）。
  const paperAbortRef = React.useRef(null);
  const paperSeqRef = React.useRef(0);
  const graphAbortRef = React.useRef(null);
  const graphSeqRef = React.useRef(0);

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
      const sequence = ++paperSeqRef.current;
      paperAbortRef.current?.abort();
      const controller = new AbortController();
      paperAbortRef.current = controller;

      setSelectedId(publicationId);
      setDetail(null);
      setSlice(null);
      setDetailError(null);
      setDetailBusy(true);
      setTab('detail');
      try {
        const payload = await api.getPaper(publicationId, { signal: controller.signal });
        if (sequence !== paperSeqRef.current) return; // 已被更新的选择取代
        setDetail(payload);
        setDetailError(null);
      } catch (error) {
        if (sequence !== paperSeqRef.current) return;
        const described = describeApiError(error);
        if (described.kind === 'cancelled') return;
        setDetailError(described);
      } finally {
        if (sequence === paperSeqRef.current) setDetailBusy(false);
      }
    },
    [api],
  );

  // 从 agent 页面点某条证据跳进来时，直接打开那一篇
  useEffect(() => {
    if (!initialPublicationId) return;
    selectPaper(initialPublicationId);
    onConsumeInitial?.();
  }, [initialPublicationId, selectPaper, onConsumeInitial]);

  const loadGraph = useCallback(
    async (publicationId, mode) => {
      if (!publicationId) return;
      const sequence = ++graphSeqRef.current;
      graphAbortRef.current?.abort();
      const controller = new AbortController();
      graphAbortRef.current = controller;

      setGraphBusy(true);
      try {
        const payload = await api.graphNeighbors(publicationId, mode, 15, {
          signal: controller.signal,
        });
        if (sequence !== graphSeqRef.current) return;
        setSlice(payload);
        setGraphError(null); // 成功后必须清掉上一次的图谱错误
      } catch (error) {
        if (sequence !== graphSeqRef.current) return;
        const described = describeApiError(error);
        if (described.kind === 'cancelled') return;
        setSlice(null);
        setGraphError(described);
      } finally {
        if (sequence === graphSeqRef.current) setGraphBusy(false);
      }
    },
    [api],
  );

  useEffect(() => {
    if (tab === 'graph' && selectedId) loadGraph(selectedId, graphMode);
  }, [tab, selectedId, graphMode, loadGraph]);

  const papers = result?.data || [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
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
              <EmptyState>
                图谱里没有匹配的记录（这是真实的空结果，不是服务不可用）。
              </EmptyState>
            ) : null}
            {!searching && papers.length > 0 ? (
              <PaperList
                papers={papers}
                selectedId={selectedId}
                onSelect={selectPaper}
                onInspect={setInspection}
              />
            ) : null}
          </div>
        </div>

        <aside className="flex w-[520px] min-w-0 flex-col bg-[var(--bg)]">
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

          <ErrorBanner error={graphError} onRetry={() => loadGraph(selectedId, graphMode)} />

          <div className="min-h-0 flex-1 overflow-auto">
            {!selectedId ? (
              <EmptyState>左侧选择一篇论文后，这里显示详情或局部图谱。</EmptyState>
            ) : null}
            {selectedId && tab === 'detail' ? (
              detailBusy ? <Loading label="正在读取论文详情…" /> : (
                <DetailPanel
                  detail={detail}
                  onInspect={setInspection}
                  onOpenPaper={selectPaper}
                />
              )
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

      <EvidenceDrawer
        inspection={inspection}
        onClose={() => setInspection(null)}
        onOpenPaper={selectPaper}
      />
    </div>
  );
}

export default function App({ api: injectedApi, agentApi }) {
  const api = useMemo(() => injectedApi || createResearchApi(), [injectedApi]);
  const [view, setView] = useState('agent');
  const [pendingPaper, setPendingPaper] = useState(null);

  const openPaper = useCallback((publicationId) => {
    setPendingPaper(publicationId);
    setView('library');
  }, []);

  const consumeInitial = useCallback(() => setPendingPaper(null), []);

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-[var(--line)] bg-[var(--panel)] px-5 py-2.5">
        <div className="mx-auto flex w-full max-w-5xl items-center gap-1">
          <h1 className="mr-3 text-[15px] font-semibold">NOESIS Research</h1>
          {[
            { key: 'agent', label: '科研助手' },
            { key: 'library', label: '论文库与图谱' },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setView(item.key)}
              data-testid="view-tab"
              data-view={item.key}
              data-active={view === item.key ? 'true' : 'false'}
              className={`rounded-md px-3 py-1 text-[13px] ${
                view === item.key
                  ? 'bg-[var(--accent-soft)] font-medium text-[var(--accent)]'
                  : 'text-[var(--ink-muted)] hover:text-[var(--ink)]'
              }`}
            >
              {item.label}
            </button>
          ))}
          <span className="ml-auto text-[11px] text-[var(--ink-muted)]">
            科学文献知识图谱 · 候选关系非事实
          </span>
        </div>
      </header>

      {view === 'agent' ? (
        <AgentChat api={agentApi} onOpenPaper={openPaper} />
      ) : (
        <LibraryView
          api={api}
          initialPublicationId={pendingPaper}
          onConsumeInitial={consumeInitial}
        />
      )}
    </div>
  );
}
