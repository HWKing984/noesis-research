import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PdfHighlighter, PdfLoader, MonitoredHighlightContainer, TextHighlight } from 'react-pdf-highlighter-extended';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

import { describeApiError } from '../lib/api.js';
import './Reader.css';

/**
 * 原文阅读视图（第二阶段 P1 骨架，拍板方向 C「精读台账」）。
 *
 * 数据侧状态机：`/api/documents/{id}/status` 返回 packages/contracts/document.py
 * 定义的五态（available / publisher_link_only / no_oa_found / fetch_failed /
 * restricted）或 `none`（尚未调查）。UI 逐字呈现 —— 绝不把「未收录」伪装成
 * 「失败」，也绝不给非 available 的论文渲染阅读器。
 *
 * P1 范围：划词「解释 / 批注」落为会话内证据卡（可跳页）；PaperQA2 全文问答、
 * 阅读记录持久化、图谱联动是 P2/P4。
 */

const STATUS_COPY = {
  publisher_link_only: {
    icon: '↗',
    tone: 'var(--text-secondary)',
    title: '未获取到全文 PDF',
    desc: 'OpenAlex 与 Semantic Scholar 均未提供开放获取 PDF，仅找到出版社落地页。系统不会伪装已有全文 —— 可以先访问出版社页面确认，或上传自己有权使用的 PDF。',
    retryable: false,
  },
  no_oa_found: {
    icon: '∅',
    tone: 'var(--text-tertiary)',
    title: '未收录全文（no_oa_found）',
    desc: '已按优先级查询 arXiv / OpenAlex best_oa_location / Semantic Scholar openAccessPdf，均无开放获取版本。这是真实不存在，不是获取失败 —— 两类状态在系统里永远分开呈现。',
    retryable: false,
  },
  fetch_failed: {
    icon: '↻',
    tone: 'var(--warning)',
    title: '获取失败（fetch_failed）',
    desc: 'OA 全文存在，但下载失败。失败与不存在是两回事：这条状态可重试。',
    retryable: true,
  },
  restricted: {
    icon: '🔒',
    tone: 'var(--accent)',
    title: '受限获取（restricted）',
    desc: '该论文在出版社版权限制内，机构订阅之外无法合法自动获取。可以挂接机构代理后重试，或直接上传你有权使用的 PDF。',
    retryable: false,
  },
  none: {
    icon: '…',
    tone: 'var(--text-tertiary)',
    title: '尚未调查全文可得性',
    desc: '系统还没有对这个论文做过 OA 检索。可以上传你手上的 PDF，或等待全文发现流程（P2：OpenAlex 发现服务）完成第一次调查。',
    retryable: false,
  },
};

function makeId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `hl-${Math.random().toString(16).slice(2)}`;
}

/** PDF 高亮底层：PdfLoader → PdfHighlighter → MonitoredHighlightContainer+TextHighlight。 */
function PdfPane({ fileUrl, highlights, onSelectionDone, utilsRef }) {
  return (
    <div className="rd-pdf" data-testid="reader-pdf">
      <PdfLoader
        document={fileUrl}
        workerSrc={workerUrl}
        beforeLoad={() => <div className="rd-pdf-loading">正在加载 PDF…</div>}
        errorMessage={(error) => (
          <div className="rd-pdf-loading">PDF 加载失败：{String(error?.message || error)}</div>
        )}
      >
        {(pdfDocument) => (
          <PdfHighlighter
            pdfDocument={pdfDocument}
            highlights={highlights}
            pdfScaleValue="page-width"
            enableAreaSelection={(event) => event.altKey}
            onSelection={(selection) => onSelectionDone(selection)}
            utilsRef={(utils) => {
              utilsRef.current = utils;
            }}
          >
            {({ highlight, viewportToScaled }) => {
              if (highlight.type === 'area') return null;
              return (
                <MonitoredHighlightContainer
                  key={highlight.id}
                  highlightTip={
                    highlight.content?.text
                      ? { position: highlight.position, content: <span className="rd-tip-text">{highlight.content.text.slice(0, 160)}</span> }
                      : undefined
                  }
                >
                  <TextHighlight
                    highlight={highlight}
                    isScrolledTo={false}
                  />
                </MonitoredHighlightContainer>
              );
            }}
          </PdfHighlighter>
        )}
      </PdfLoader>
    </div>
  );
}

function StateCard({ documentRef, onUpload, onRetry, busy }) {
  const copy = STATUS_COPY[documentRef.status] || STATUS_COPY.none;
  return (
    <div className="rd-state" data-testid="reader-state" data-status={documentRef.status}>
      <div className="rd-state-card">
        <div className="rd-state-icon" style={{ color: copy.tone }}>{copy.icon}</div>
        <div className="rd-state-title">{copy.title}</div>
        <div className="rd-state-desc">{copy.desc}</div>
        {documentRef.detail ? <div className="rd-state-detail">{documentRef.detail}</div> : null}
        <div className="rd-state-btns">
          {copy.retryable && documentRef.sourceUrl ? (
            <button type="button" className="btn btn--ink" data-testid="reader-retry" disabled={busy} onClick={() => onRetry(documentRef.sourceUrl)}>
              {busy ? '重试中…' : '重试获取'}
            </button>
          ) : null}
          <label className="btn btn--ink" style={{ cursor: 'pointer' }}>
            上传 PDF
            <input
              type="file"
              accept="application/pdf"
              style={{ display: 'none' }}
              data-testid="reader-upload"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onUpload(file);
                event.target.value = '';
              }}
            />
          </label>
          {documentRef.sourceUrl && documentRef.status === 'publisher_link_only' ? (
            <a className="btn" href={documentRef.sourceUrl} target="_blank" rel="noreferrer">
              访问出版社页面 ↗
            </a>
          ) : null}
        </div>
        <div className="rd-state-src">
          全文来源优先级：arXiv / OpenReview → OpenAlex best_oa_location → Semantic Scholar openAccessPdf → 用户上传
          <br />
          来源、SHA-256 与获取时间全部落库，引用可追溯。
        </div>
      </div>
    </div>
  );
}

function EvidenceCard({ item, onJump }) {
  const kindLabel = item.kind === 'qa' ? '提问' : item.kind === 'explain' ? '划词解释' : '批注';
  return (
    <div className="rd-ev-card" data-testid="ev-card" data-kind={item.kind}>
      <span className="rd-ev-kind">{kindLabel} · {item.time}</span>
      {item.quote ? <div className="rd-ev-quote">“{item.quote}”</div> : null}
      {item.text ? <div className="rd-ev-text">{item.text}</div> : null}
      <div className="rd-ev-acts">
        {item.highlightId ? (
          <button type="button" className="rd-ev-mini" onClick={() => onJump(item.highlightId)}>
            跳到原文 p.{item.page}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default function ReaderView({ api, publicationId, title }) {
  const [docState, setDocState] = useState({ loading: true, ref: null, error: null });
  const [highlights, setHighlights] = useState([]);
  const [evidence, setEvidence] = useState([]);
  const [ghost, setGhost] = useState(null);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState('');
  const utilsRef = useRef(null);
  const fileUrl = useMemo(() => api.documentFileUrl(publicationId), [api, publicationId]);

  const loadStatus = useCallback(async () => {
    setDocState({ loading: true, ref: null, error: null });
    setHighlights([]);
    setEvidence([]);
    try {
      const ref = await api.documentStatus(publicationId);
      setDocState({ loading: false, ref, error: null });
    } catch (cause) {
      setDocState({ loading: false, ref: null, error: describeApiError(cause) });
    }
  }, [api, publicationId]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const onSelectionDone = useCallback((selection) => {
    try {
      setGhost(selection.makeGhostHighlight());
    } catch {
      setGhost(null);
    }
  }, []);

  const commitGhost = useCallback((kind) => {
    if (!ghost) return;
    const id = makeId();
    const page = ghost.position?.boundingRect?.pageNumber || 1;
    const quote = String(ghost.content?.text || '').trim();
    setHighlights((prev) => [...prev, { id, type: ghost.type, content: ghost.content, position: ghost.position }]);
    setEvidence((prev) => [
      {
        id,
        kind,
        quote,
        page,
        highlightId: id,
        time: new Date().toTimeString().slice(0, 5),
        text:
          kind === 'explain'
            ? '已存为会话内证据。真实实现（P2）：PaperQA2 在全文索引上检索证据后作答，每条结论附页码定位。'
            : '',
      },
      ...prev,
    ]);
    setGhost(null);
  }, [ghost]);

  const onJump = useCallback((highlightId) => {
    const utils = utilsRef.current;
    const target = highlights.find((h) => h.id === highlightId);
    if (utils && target) utils.scrollToHighlight(target);
  }, [highlights]);

  const onUpload = useCallback(async (file) => {
    setBusy(true);
    try {
      const ref = await api.uploadDocument(publicationId, file);
      setDocState({ loading: false, ref, error: null });
    } catch (cause) {
      const described = describeApiError(cause);
      setDocState((prev) => ({ ...prev, error: described }));
    } finally {
      setBusy(false);
    }
  }, [api, publicationId]);

  const onRetry = useCallback(async (sourceUrl) => {
    setBusy(true);
    try {
      const ref = await api.fetchDocument(publicationId, sourceUrl);
      setDocState({ loading: false, ref, error: null });
    } catch (cause) {
      setDocState((prev) => ({ ...prev, error: describeApiError(cause) }));
    } finally {
      setBusy(false);
    }
  }, [api, publicationId]);

  const onAsk = useCallback(() => {
    const text = question.trim();
    if (!text) return;
    setQuestion('');
    setEvidence((prev) => [
      {
        id: makeId(),
        kind: 'qa',
        quote: text,
        page: null,
        time: new Date().toTimeString().slice(0, 5),
        text: '（P2）全文问答由 PaperQA2 检索证据后作答，并给出可跳页的引用；当前为会话内占位。',
      },
      ...prev,
    ]);
  }, [question]);

  const docRef = docState.ref;
  const readable = docRef?.status === 'available';

  return (
    <div className="reader" data-testid="reader-view" data-status={docRef?.status || (docState.loading ? 'loading' : 'error')}>
      <aside className="rd-side">
        <div className="rd-side-label">本篇导航</div>
        <div className="rd-side-note">
          章节/页缩略（P2）。选中正文后，解释与批注会作为带页码的锚点出现在下方，可回跳高亮。
        </div>
        <div className="rd-side-label">批注与引用锚</div>
        <div className="rd-side-list" data-testid="reader-anchors">
          {evidence.filter((item) => item.highlightId).length === 0 ? (
            <div className="rd-side-empty">还没有锚点 —— 在正文里选中一段试试。</div>
          ) : (
            evidence
              .filter((item) => item.highlightId)
              .map((item) => (
                <button key={item.id} type="button" className="rd-anchor" onClick={() => onJump(item.highlightId)}>
                  <span className="rd-anchor-quote">“{item.quote.slice(0, 60)}{item.quote.length > 60 ? '…' : ''}”</span>
                  <span className="rd-anchor-page">p.{item.page} · {item.kind === 'explain' ? '解释' : '批注'}</span>
                </button>
              ))
          )}
        </div>
      </aside>

      <section className="rd-main">
        <div className="rd-toolbar">
          <span className="rd-title" data-testid="reader-title">{title || publicationId}</span>
          {readable ? (
            <span className="rd-badge rd-badge--ok" data-testid="reader-state-badge">全文可读 · 已缓存</span>
          ) : docRef ? (
            <span className="rd-badge" data-testid="reader-state-badge">{docRef.status}</span>
          ) : null}
        </div>
        {docState.loading ? (
          <div className="rd-pdf-loading">正在查询全文可得性…</div>
        ) : docState.error ? (
          <div className="rd-state">
            <div className="rd-state-card">
              <div className="rd-state-title">{docState.error.title}</div>
              <div className="rd-state-desc">{docState.error.detail}</div>
              <div className="rd-state-btns">
                <button type="button" className="btn" onClick={loadStatus}>重试</button>
              </div>
            </div>
          </div>
        ) : readable ? (
          <PdfPane
            fileUrl={fileUrl}
            highlights={highlights}
            onSelectionDone={onSelectionDone}
            utilsRef={utilsRef}
          />
        ) : (
          <StateCard documentRef={docRef} busy={busy} onUpload={onUpload} onRetry={onRetry} />
        )}
      </section>

      <aside className="rd-ev">
        <div className="rd-ev-head">
          <span className="rd-ev-title">证据流</span>
          <span className="rd-ev-count">{evidence.length} 条 · 会话内（P2 持久化）</span>
        </div>
        <div className="rd-ev-scroll" data-testid="reader-evidence">
          {evidence.length === 0 ? (
            <div className="rd-ev-empty">
              选中正文一段 → <b>解释 / 批注</b>；或直接提问。每条都带页码，可回跳原文。
            </div>
          ) : (
            evidence.map((item) => <EvidenceCard key={item.id} item={item} onJump={onJump} />)
          )}
        </div>
        {ghost ? (
          <div className="rd-tip" data-testid="reader-tip">
            <span className="rd-tip-quote">“{String(ghost.content?.text || '').slice(0, 48)}…”</span>
            <div className="rd-tip-btns">
              <button type="button" className="btn btn--ink" onClick={() => commitGhost('explain')}>解释</button>
              <button type="button" className="btn" onClick={() => commitGhost('note')}>批注</button>
              <button type="button" className="btn" onClick={() => setGhost(null)}>取消</button>
            </div>
          </div>
        ) : (
          <div className="rd-composer">
            <input
              placeholder="问这篇论文…（P2 接 PaperQA2）"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') onAsk();
              }}
            />
            <button type="button" className="rd-send" aria-label="发送" onClick={onAsk}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M22 2 15 22l-4-9-9-4Z" /></svg>
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}
