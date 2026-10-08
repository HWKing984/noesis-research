import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createResearchApi, describeApiError } from './lib/api.js';
import { createAgentApi, describeAgentError } from './lib/agentApi.js';
import AgentChat from './components/AgentChat.jsx';
import EvidenceRail from './components/EvidenceRail.jsx';
import Sidebar from './components/Sidebar.jsx';
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
  q: '', method: '', task: '', dataset: '', author: '', venue: '', year: '', limit: '10',
};

const TABS = [
  { key: 'detail', label: '论文详情' },
  { key: 'graph', label: '局部图谱' },
];

const IDLE_RUN = {
  status: 'idle', events: [], answer: '', citation: null, runId: null, error: null, question: '',
};

/** 只把非空字段送给后端；空字段一律不发，保证回显与实参一致。 */
function toSearchParams(form) {
  const params = { limit: form.limit || '10', offset: 0 };
  for (const key of ['q', 'method', 'task', 'dataset', 'author', 'venue', 'year']) {
    const value = (form[key] || '').trim();
    if (value) params[key] = value;
  }
  return params;
}

/** 论文库与图谱 —— 二级视图。抽屉状态在 App 层（引用上标共用同一个抽屉）。 */
function LibraryView({ api, initialPublicationId, onConsumeInitial, inspection, onInspect }) {
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

  // 异步请求生命周期：AbortController 真取消 + 序号双保险，旧响应不得覆盖新选择
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

  useEffect(() => { loadHealth(); }, [loadHealth]);

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
        if (sequence !== paperSeqRef.current) return;
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
        const payload = await api.graphNeighbors(publicationId, mode, 15, { signal: controller.signal });
        if (sequence !== graphSeqRef.current) return;
        setSlice(payload);
        setGraphError(null);
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
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <GraphHeader health={health} error={healthError} />
      <div style={{ display: 'flex', minHeight: 0, flex: 1 }}>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border-subtle)' }}>
          <SearchBar value={form} onChange={setForm} onSubmit={runSearch} busy={searching} />
          <AppliedEcho meta={result?.meta} />
          <ErrorBanner error={searchError} onRetry={runSearch} />
          <BoundaryNotice />
          <div className="stage">
            {searching ? <Loading label="正在检索图谱…" /> : null}
            {!searching && !result && !searchError ? (
              <EmptyState>输入条件后点「检索」。检索结果里的每一条都带来源引用，可以直接核对。</EmptyState>
            ) : null}
            {!searching && result && papers.length === 0 ? (
              <EmptyState>图谱里没有匹配的记录（这是真实的空结果，不是服务不可用）。</EmptyState>
            ) : null}
            {!searching && papers.length > 0 ? (
              <PaperList
                papers={papers}
                selectedId={selectedId}
                onSelect={selectPaper}
                onInspect={onInspect}
              />
            ) : null}
          </div>
        </div>

        <aside style={{ width: 480, flex: '0 0 auto', display: 'flex', flexDirection: 'column', background: 'var(--bg-secondary)', minWidth: 0 }}>
          <nav style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-primary)', padding: '8px 16px 0' }}>
            {TABS.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                data-testid="tab"
                data-tab={item.key}
                data-active={tab === item.key ? 'true' : 'false'}
                style={{
                  padding: '6px 12px', fontSize: 12.5,
                  borderBottom: `2px solid ${tab === item.key ? 'var(--text-primary)' : 'transparent'}`,
                  fontWeight: tab === item.key ? 600 : 400,
                  color: tab === item.key ? 'var(--text-primary)' : 'var(--text-tertiary)',
                }}
              >
                {item.label}
              </button>
            ))}
            {selectedId ? (
              <span className="mono" style={{ marginLeft: 'auto', paddingBottom: 6, fontSize: 10, color: 'var(--text-muted)' }}>
                {selectedId}
              </span>
            ) : null}
          </nav>
          <ErrorBanner error={graphError} onRetry={() => loadGraph(selectedId, graphMode)} />
          <div className="stage">
            {!selectedId ? <EmptyState>左侧选择一篇论文后，这里显示详情或局部图谱。</EmptyState> : null}
            {selectedId && tab === 'detail' ? (
              detailBusy ? <Loading label="正在读取论文详情…" /> : (
                <DetailPanel detail={detail} onInspect={onInspect} onOpenPaper={selectPaper} />
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
    </div>
  );
}

export default function App({ api: injectedApi, agentApi: injectedAgentApi }) {
  const api = useMemo(() => injectedApi || createResearchApi(), [injectedApi]);
  const agentApi = useMemo(() => injectedAgentApi || createAgentApi(), [injectedAgentApi]);

  const [view, setView] = useState('agent');
  const [railOpen, setRailOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem('nr-theme') || 'light');
  const [agentHealth, setAgentHealth] = useState(null);
  const [runs, setRuns] = useState([]);
  const [run, setRun] = useState(IDLE_RUN);
  const [inspection, setInspection] = useState(null);
  const [pendingPaper, setPendingPaper] = useState(null);
  const sourceRef = useRef(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('nr-theme', theme);
  }, [theme]);

  useEffect(() => {
    document.body.classList.toggle('is-rail', railOpen && view === 'agent');
  }, [railOpen, view]);

  const closeStream = () => {
    try { sourceRef.current?.close(); } catch { /* ignore */ }
    sourceRef.current = null;
  };

  const refreshRuns = useCallback(async () => {
    try {
      const payload = await agentApi.listRuns(20);
      setRuns(payload.data || []);
    } catch { /* 侧栏历史拿不到就不显示，不阻塞主流程 */ }
  }, [agentApi]);

  /** 打开一次运行的 SSE 流（新提问与历史重放都走这里；已结束的运行会整段重放）。 */
  const followRun = useCallback(
    (runId, question) => {
      closeStream();
      setRun({ ...IDLE_RUN, status: 'running', runId, question });
      const source = new EventSource(agentApi.eventsUrl(runId));
      sourceRef.current = source;
      const append = (m) => setRun((prev) => ({ ...prev, events: [...prev.events, JSON.parse(m.data)] }));
      source.addEventListener('tool_call', append);
      source.addEventListener('tool_result', append);
      source.addEventListener('tool_error', append);
      source.addEventListener('failed', (m) => {
        const payload = JSON.parse(m.data);
        setRun((prev) => ({
          ...prev,
          events: [...prev.events, payload],
          status: 'failed',
          error: { title: '运行失败', detail: payload.message || '未知原因' },
        }));
      });
      // 逐字流式：token 增量直接追加到回答上（NOESIS 的打字机效果）
      source.addEventListener('answer_delta', (m) => {
        const payload = JSON.parse(m.data);
        setRun((prev) => ({ ...prev, answer: prev.answer + (payload.delta || '') }));
      });
      source.addEventListener('answer', (m) => {
        const payload = JSON.parse(m.data);
        // answer 事件是权威全文（含引用核查），覆盖增量拼接的结果
        setRun((prev) => ({ ...prev, answer: payload.text || '', citation: payload.citation || null }));
      });
      source.addEventListener('done', () => {
        setRun((prev) => ({ ...prev, status: prev.status === 'failed' ? 'failed' : 'ok' }));
        closeStream();
        refreshRuns();
      });
      source.onerror = () => {
        setRun((prev) => {
          if (prev.status !== 'running') return prev;
          return {
            ...prev,
            status: 'failed',
            error: {
              title: '事件流中断',
              detail: '没能读到 Agent 的完整事件流。这次结果不算数，请重试。',
              kind: 'offline',
            },
          };
        });
        closeStream();
      };
    },
    [agentApi, refreshRuns],
  );

  const ask = useCallback(
    async (question) => {
      closeStream();
      setRun({ ...IDLE_RUN, status: 'running', question });
      setInspection(null);
      let started;
      try {
        started = await agentApi.startRun(question);
      } catch (cause) {
        setRun((prev) => ({ ...prev, status: 'failed', error: describeAgentError(cause) }));
        return;
      }
      followRun(started.runId, question);
    },
    [agentApi, followRun],
  );

  const openRun = useCallback(
    (runId) => {
      setView('agent');
      const known = runs.find((r) => r.runId === runId);
      followRun(runId, known?.question || '（历史运行）');
    },
    [runs, followRun],
  );

  const newRun = useCallback(() => {
    closeStream();
    setRun(IDLE_RUN);
    setView('agent');
  }, []);

  useEffect(() => {
    let cancelled = false;
    agentApi
      .health()
      .then((payload) => { if (!cancelled) setAgentHealth(payload); })
      .catch((cause) => {
        if (!cancelled) setAgentHealth({ agentReady: false, healthError: describeAgentError(cause) });
      });
    refreshRuns();
    return () => { cancelled = true; };
  }, [agentApi, refreshRuns]);

  useEffect(() => closeStream, []);

  // 证据链论文卡：来自运行事件里的 paperItems（与给模型的视图同源），同一篇只出现一次
  const papers = useMemo(() => {
    const seen = new Map();
    for (const event of run.events) {
      const items = event?.summary?.paperItems;
      if (!Array.isArray(items)) continue;
      for (const item of items) {
        if (item?.publicationId && !seen.has(item.publicationId)) seen.set(item.publicationId, item);
      }
    }
    return [...seen.values()];
  }, [run.events]);

  const paperTitleById = useMemo(() => {
    const map = new Map();
    for (const paper of papers) map.set(paper.publicationId, paper.title);
    return map;
  }, [papers]);

  /** 点引用上标 / 引用 id：打开证据抽屉（能从证据链里拿到题名就带题名）。 */
  const onCited = useCallback(
    (id) => {
      const paper = paperTitleById.get(id);
      setInspection({
        reference: {
          sourceType: 'kg_bibliography',
          sourceId: id,
          publicationId: id,
          graphId: null,
          evidenceLevel: run.citation?.evidenceLevels?.[0] || 'title',
          assertionStatus: 'none',
          verificationStatus: 'unverified',
        },
        context: { title: paper || id, publicationId: id },
      });
    },
    [paperTitleById, run.citation],
  );

  const openPaper = useCallback((publicationId) => {
    setPendingPaper(publicationId);
    setView('library');
  }, []);
  const consumeInitial = useCallback(() => setPendingPaper(null), []);

  return (
    <div className="app">
      <Sidebar
        view={view}
        onView={setView}
        runs={runs}
        activeRunId={run.runId}
        onOpenRun={openRun}
        onNewRun={newRun}
        agentHealth={agentHealth}
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((prev) => !prev)}
      />

      <main className="main">
        {view === 'agent' ? (
          <div style={{ display: 'flex', flex: 1, minHeight: 0, minWidth: 0 }}>
            <AgentChat
              run={run}
              onAsk={ask}
              onCited={onCited}
              agentHealth={agentHealth}
              view={view}
              onView={setView}
              railOpen={railOpen}
              onToggleRail={() => setRailOpen((prev) => !prev)}
              railCount={papers.length}
            />
            <EvidenceRail papers={papers} onInspect={setInspection} busy={run.status === 'running'} />
          </div>
        ) : (
          <LibraryView
            api={api}
            initialPublicationId={pendingPaper}
            onConsumeInitial={consumeInitial}
            inspection={inspection}
            onInspect={setInspection}
          />
        )}
      </main>

      <EvidenceDrawer
        inspection={inspection}
        onClose={() => setInspection(null)}
        onOpenPaper={openPaper}
      />
    </div>
  );
}
