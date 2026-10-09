import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createResearchApi, describeApiError } from './lib/api.js';
import { createAgentApi, describeAgentError } from './lib/agentApi.js';
import AgentChat from './components/AgentChat.jsx';
import EvidenceRail from './components/EvidenceRail.jsx';
import ReaderView from './components/ReaderView.jsx';
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

const IDLE_TURN = {
  runId: null, question: '', events: [], answer: '', citation: null, status: 'idle', error: null,
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
function LibraryView({ api, initialPublicationId, onConsumeInitial, inspection, onInspect, onOpenReader }) {
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

  // 全文可得性（paper-reader 状态机）：详情栏打开时查询，驱动「阅读全文」按钮。
  const [docRef, setDocRef] = useState(null);
  useEffect(() => {
    let cancelled = false;
    setDocRef(null);
    if (!selectedId) return undefined;
    api
      .documentStatus(selectedId)
      .then((ref) => {
        if (!cancelled) setDocRef(ref);
      })
      .catch(() => {
        if (!cancelled) setDocRef(null);
      });
    return () => {
      cancelled = true;
    };
  }, [api, selectedId]);

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

        <aside data-testid="detail-aside" style={{ width: 480, flex: '0 0 auto', display: 'flex', flexDirection: 'column', background: 'var(--bg-secondary)', minWidth: 0 }}>
          <nav style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-primary)', padding: '8px 16px 0', alignItems: 'center' }}>
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
            {selectedId ? (
              docRef?.status === 'available' ? (
                <button
                  type="button"
                  className="btn btn--ink"
                  data-testid="read-full-btn"
                  style={{ marginLeft: 8, marginBottom: 4, flex: '0 0 auto' }}
                  onClick={() => onOpenReader?.(selectedId)}
                >
                  阅读全文 →
                </button>
              ) : docRef ? (
                <span
                  data-testid="read-full-state"
                  title={docRef.detail || docRef.status}
                  style={{
                    marginLeft: 8, marginBottom: 4, flex: '0 0 auto',
                    fontSize: 11, padding: '2.5px 9px', borderRadius: 999,
                    border: '1px solid var(--border-default)', background: 'var(--pill-bg)',
                    color: 'var(--text-tertiary)', whiteSpace: 'nowrap',
                  }}
                >
                  {docRef.status === 'none' ? '全文未调查' : docRef.status === 'no_oa_found' ? '未收录全文' : docRef.status === 'fetch_failed' ? '获取失败' : docRef.status === 'restricted' ? '版权受限' : '仅出版社页'}
                </span>
              ) : null
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
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [turns, setTurns] = useState([]);
  const [inspection, setInspection] = useState(null);
  const [pendingPaper, setPendingPaper] = useState(null);
  const [readerPaper, setReaderPaper] = useState(null);
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

  const refreshSessions = useCallback(async () => {
    try {
      const payload = await agentApi.listSessions(20);
      setSessions(payload.data || []);
    } catch { /* 侧栏历史拿不到就不显示，不阻塞主流程 */ }
  }, [agentApi]);

  const updateTurn = useCallback((index, patch) => {
    setTurns((prev) => prev.map((turn, i) => (i === index ? { ...turn, ...patch } : turn)));
  }, []);

  /** 跟一次运行的 SSE 流，事件落到第 turnIndex 轮上。 */
  const followRun = useCallback(
    (runId, turnIndex) => {
      closeStream();
      const append = (m) => {
        const event = JSON.parse(m.data);
        setTurns((prev) => prev.map((turn, i) => (i === turnIndex ? { ...turn, events: [...turn.events, event] } : turn)));
      };
      sourceRef.current = new EventSource(agentApi.eventsUrl(runId));
      const source = sourceRef.current;
      source.addEventListener('tool_step', append);
      source.addEventListener('tool_call', append);
      source.addEventListener('tool_result', append);
      source.addEventListener('tool_error', append);
      source.addEventListener('run_retry', append);
      source.addEventListener('failed', (m) => {
        const payload = JSON.parse(m.data);
        updateTurn(turnIndex, {
          status: 'failed',
          error: { title: '运行失败', detail: payload.message || '未知原因' },
        });
      });
      source.addEventListener('answer', (m) => {
        const payload = JSON.parse(m.data);
        updateTurn(turnIndex, { answer: payload.text || '', citation: payload.citation || null });
      });
      source.addEventListener('answer_delta', (m) => {
        const payload = JSON.parse(m.data);
        setTurns((prev) => prev.map((turn, i) => (i === turnIndex ? { ...turn, answer: turn.answer + (payload.delta || '') } : turn)));
      });
      source.addEventListener('done', () => {
        updateTurn(turnIndex, { status: 'ok' });
        closeStream();
        refreshSessions();
      });
      source.onerror = () => {
        updateTurn(turnIndex, {
          status: 'failed',
          error: {
            title: '事件流中断',
            detail: '没能读到 Agent 的完整事件流。这次结果不算数，请重试。',
            kind: 'offline',
          },
        });
        closeStream();
      };
    },
    [agentApi, refreshSessions, updateTurn],
  );

  const ask = useCallback(
    async (question) => {
      closeStream();
      const turnIndex = turns.length;
      setTurns((prev) => [...prev, { ...IDLE_TURN, status: 'running', question }]);
      setInspection(null);
      let started;
      try {
        started = await agentApi.startRun(question, sessionId || undefined);
      } catch (cause) {
        updateTurn(turnIndex, { status: 'failed', error: describeAgentError(cause) });
        return;
      }
      if (started.sessionId && started.sessionId !== sessionId) setSessionId(started.sessionId);
      followRun(started.runId, turnIndex);
    },
    [agentApi, sessionId, turns.length, followRun, updateTurn],
  );

  const openSession = useCallback(
    async (id) => {
      setView('agent');
      try {
        const session = await agentApi.getSession(id);
        setSessionId(session.sessionId);
        setTurns(
          (session.turns || []).map((turn) => ({
            ...IDLE_TURN,
            runId: turn.runId,
            question: turn.question,
            answer: turn.answer,
            status: 'ok',
          })),
        );
        setInspection(null);
      } catch { /* 会话详情拿不到就不切换，保持当前视图 */ }
    },
    [agentApi],
  );

  const newResearch = useCallback(() => {
    closeStream();
    setSessionId(null);
    setTurns([]);
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
    refreshSessions();
    return () => { cancelled = true; };
  }, [agentApi, refreshSessions]);

  useEffect(() => closeStream, []);

  // 证据链论文卡：本会话所有轮次的 paperItems（同一篇只出现一次）
  const papers = useMemo(() => {
    const seen = new Map();
    for (const turn of turns) {
      for (const event of turn.events) {
        const items = event?.summary?.paperItems;
        if (!Array.isArray(items)) continue;
        for (const item of items) {
          if (item?.publicationId && !seen.has(item.publicationId)) seen.set(item.publicationId, item);
        }
      }
    }
    return [...seen.values()];
  }, [turns]);

  const paperTitleById = useMemo(() => {
    const map = new Map();
    for (const paper of papers) map.set(paper.publicationId, paper.title);
    return map;
  }, [papers]);

  const onCited = useCallback(
    (id) => {
      const paper = paperTitleById.get(id);
      setInspection({
        reference: {
          sourceType: 'kg_bibliography',
          sourceId: id,
          publicationId: id,
          graphId: null,
          evidenceLevel: 'title',
          assertionStatus: 'none',
          verificationStatus: 'unverified',
        },
        context: { title: paper || id, publicationId: id },
      });
    },
    [paperTitleById],
  );

  const openPaper = useCallback((publicationId) => {
    setPendingPaper(publicationId);
    setView('library');
  }, []);
  const consumeInitial = useCallback(() => setPendingPaper(null), []);

  const openReader = useCallback((publicationId) => {
    setReaderPaper(publicationId);
    setView('reader');
  }, []);

  return (
    <div className="app">
      <Sidebar
        view={view}
        onView={setView}
        sessions={sessions}
        activeSessionId={sessionId}
        onOpenSession={openSession}
        onNewResearch={newResearch}
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
              turns={turns}
              onAsk={ask}
              onCited={onCited}
              agentHealth={agentHealth}
              view={view}
              onView={setView}
              railOpen={railOpen}
              onToggleRail={() => setRailOpen((prev) => !prev)}
              railCount={papers.length}
            />
            <EvidenceRail papers={papers} onInspect={setInspection} busy={turns.some((t) => t.status === 'running')} />
          </div>
        ) : view === 'reader' ? (
          readerPaper ? (
            <ReaderView
              api={api}
              publicationId={readerPaper}
              title={paperTitleById.get(readerPaper)}
            />
          ) : (
            <div className="reader" data-testid="reader-empty">
              <div className="rd-state">
                <div className="rd-state-card">
                  <div className="rd-state-title">从一篇论文进入阅读</div>
                  <div className="rd-state-desc">
                    阅读器一次只读一篇：在「科研助手」的回答里点引用上标，或在「论文库与图谱」打开详情后点
                    「阅读全文」，即可进入本视图。
                  </div>
                </div>
              </div>
            </div>
          )
        ) : (
          <LibraryView
            api={api}
            initialPublicationId={pendingPaper}
            onConsumeInitial={consumeInitial}
            inspection={inspection}
            onInspect={setInspection}
            onOpenReader={openReader}
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
