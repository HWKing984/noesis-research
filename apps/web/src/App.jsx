import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createResearchApi, describeApiError } from './lib/api.js';
import { createAgentApi, describeAgentError } from './lib/agentApi.js';
import AgentChat from './components/AgentChat.jsx';
import EvidenceRail from './components/EvidenceRail.jsx';
import Sidebar from './components/Sidebar.jsx';
import PaperDrawer from './components/PaperDrawer.jsx';
import { SearchBar, AppliedEcho, PaperList } from './components/SearchPanel.jsx';
import {
  EmptyState,
  ErrorBanner,
  EvidenceDrawer,
  GraphHeader,
  Loading,
} from './components/StatusPieces.jsx';

const EMPTY_FORM = {
  q: '', method: '', task: '', dataset: '', author: '', venue: '', year: '', limit: '10',
};

/** 空态建议卡：点卡片 = 预填关键词并检索。 */
const SUGGESTIONS = [
  { label: '扩散模型 → image generation', hint: '候选断言 · 方法→任务', q: 'diffusion' },
  { label: '题名含 transformer 的论文', hint: '题名检索', q: 'transformer' },
  { label: 'ImageNet 上的分类方法', hint: '数据集候选 · 评测关系', q: 'ImageNet' },
  { label: 'NeurIPS 2020 · 生成模型', hint: '会议 + 年份组合', q: 'generative' },
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

/** 论文库与图谱 —— 检索优先布局：hero 空态 / 吸顶检索 + 结果流 / 论文抽屉。
 *  抽屉状态在 App 层（引用上标共用同一个证据抽屉，证据抽屉叠在论文抽屉之上）。 */
function LibraryView({ api, initialPublicationId, onConsumeInitial, inspection, onInspect, themeProp }) {
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

  /** override：建议卡预填表单后立即可检索，不等 state 回流（避免 stale closure）。 */
  const runSearch = useCallback(
    async (override) => {
      const source = override || form;
      setSearching(true);
      setSearchError(null);
      try {
        const payload = await api.searchPapers(toSearchParams(source));
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
    },
    [api, form],
  );

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

  const closeDrawer = useCallback(() => {
    paperAbortRef.current?.abort();
    setSelectedId(null);
    setDetail(null);
    setSlice(null);
    setDetailError(null);
  }, []);

  const papers = result?.data || [];
  const hasQuery = Boolean(result || searchError || searching);
  const scope = health?.scope || {};

  return (
    <div className="libview">
      <GraphHeader health={health} error={healthError} />

      {hasQuery ? (
        <div className="lib-scroll">
          <div className="lib-result">
            <div className="lib-fixedbar">
              <SearchBar value={form} onChange={setForm} onSubmit={() => runSearch()} busy={searching} />
            </div>
            <AppliedEcho meta={result?.meta} count={searching ? null : papers.length} />
            <ErrorBanner error={searchError} onRetry={() => runSearch()} />
            {detailError && selectedId ? (
              <ErrorBanner error={detailError} onRetry={() => selectPaper(selectedId)} />
            ) : null}
            {searching ? <Loading label="正在检索图谱…" /> : null}
            {!searching && result && papers.length === 0 ? (
              <EmptyState>图谱里没有匹配的记录（这是真实的空结果，不是服务不可用）。</EmptyState>
            ) : null}
            {!searching && papers.length > 0 ? (
              <div style={{ marginTop: 12 }}>
                <PaperList
                  papers={papers}
                  selectedId={selectedId}
                  onSelect={selectPaper}
                  onInspect={onInspect}
                />
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="lib-hero">
          <div className="lib-hero-inner">
            <h1 className="lib-hero-title">检索文献，核对证据</h1>
            <p className="lib-hero-sub">
              <b>{(scope.bibliographyTitles ?? 0).toLocaleString('en-US')}</b> 篇书目 ·{' '}
              <b>{(scope.modelTitles ?? 0).toLocaleString('en-US')}</b> 篇已建模型 ·{' '}
              <b>{(scope.candidateAssertions ?? 0).toLocaleString('en-US')}</b> 条候选断言。
              <br />
              每一条结果都带来源引用，可以直接核对。
            </p>
            <div style={{ width: '100%' }}>
              <SearchBar value={form} onChange={setForm} onSubmit={() => runSearch()} busy={searching} />
            </div>
            <div className="lib-cards">
              {SUGGESTIONS.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  className="lib-card"
                  data-testid="library-suggest"
                  data-q={item.q}
                  onClick={() => {
                    const next = { ...EMPTY_FORM, q: item.q };
                    setForm(next);
                    runSearch(next);
                  }}
                >
                  <span className="l">{item.label}</span>
                  <span className="h">{item.hint}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <PaperDrawer
        open={Boolean(selectedId)}
        onClose={closeDrawer}
        tab={tab}
        onTab={setTab}
        selectedId={selectedId}
        detail={detail}
        detailBusy={detailBusy}
        slice={slice}
        graphBusy={graphBusy}
        graphMode={graphMode}
        onModeChange={setGraphMode}
        onRefresh={() => loadGraph(selectedId, graphMode)}
        onInspect={onInspect}
        onOpenPaper={selectPaper}
        appearance={themeProp}
      />
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
      source.addEventListener('tool_step', append);
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
            themeProp={theme}
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
