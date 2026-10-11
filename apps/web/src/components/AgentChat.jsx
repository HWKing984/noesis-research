import React, { useMemo, useState } from 'react';

import { citationReport } from '../lib/evidence.js';
import { renderAnswer } from '../lib/answerRender.js';
import ThinkingChain from './ThinkingChain.jsx';
import SpiralMark, { SPIRAL_PATH } from './SpiralMark.jsx';

const PROMPTS = [
  { label: '有哪些关于 transformer 的论文？', hint: '按关键词检索' },
  { label: '扩散模型在图像生成上的工作有哪些？', hint: '按方法检索' },
  { label: '图神经网络用在异常检测的有哪些？', hint: '方法 → 任务' },
  { label: '2025 年 CVPR 的扩散 transformer', hint: '按年份与会议' },
];

const USER_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
    <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5" />
  </svg>
);

/**
 * 科研助手 —— 页面结构与视觉逐项照搬 NOESIS ChatArea。
 * 支持连续追问：turns 是本会话的全部轮次，每轮 = 用户气泡 + 助手气泡
 * （过程卡 + 流式正文 + 引用核查）；追问时后端会带上此前所有轮次作为上下文。
 * 主 testid（citation-verdict / agent-answer / agent-question）只标最后一轮，
 * 供验收脚本稳定定位。
 */
export default function AgentChat({ turns, onAsk, onCited, agentHealth, view, onView, railOpen, onToggleRail, railCount = 0 }) {
  const [draft, setDraft] = useState('');
  // 研究笔记**默认展开**（最后一轮），历史轮默认收起；用户点过的轮次记在 flipped 里取反。
  // 起因：过程默认收起时用户只看得到"答案 + 核查卡"，观感是"它没有思考"。
  const [flippedTraces, setFlippedTraces] = useState(() => new Set());

  const busy = turns.some((t) => t.status === 'running');
  const hasThread = turns.length > 0;
  const lastIndex = turns.length - 1;

  const toggleTrace = (key) => {
    setFlippedTraces((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const submit = (text) => {
    const prompt = (text ?? draft).trim();
    if (!prompt || busy) return;
    setDraft('');
    onAsk(prompt);
  };

  return (
    <div className="chat-area" data-testid="agent-chat">
      <div className="chat-header">
        <span className="chat-header-title" data-testid="agent-header-title">
          {hasThread ? (turns[0].question || '新研究') : '新研究'}
        </span>
        <div className="chat-header-badge">
          <div className="mode-tabs" data-testid="mode-tabs">
            <button
              type="button"
              data-testid="view-tab"
              data-view="agent"
              data-active={view === 'agent' ? 'true' : 'false'}
              className={view === 'agent' ? 'is-on' : ''}
              onClick={() => onView('agent')}
            >
              对话
            </button>
            <button
              type="button"
              data-testid="view-tab"
              data-view="library"
              data-active={view === 'library' ? 'true' : 'false'}
              className={view === 'library' ? 'is-on' : ''}
              onClick={() => onView('library')}
            >
              论文库
            </button>
            <button
              type="button"
              data-testid="view-tab"
              data-view="reader"
              data-active={view === 'reader' ? 'true' : 'false'}
              className={view === 'reader' ? 'is-on' : ''}
              onClick={() => onView('reader')}
            >
              原文阅读
            </button>
          </div>
        </div>
        <div className="chat-header-status">
          <span className="chip" data-testid="graph-chip">
            <span className={`dot ${agentHealth?.status === 'ready' ? '' : 'is-down'}`} />
            {agentHealth?.status || '…'} · {String(agentHealth?.graphId || '').slice(0, 12) || '—'}
          </span>
        </div>
      </div>

      <div className="chat-content-frame">
        {!hasThread ? (
          <div className="welcome-screen" data-testid="agent-intro">
            <div className="welcome-inner">
              <div className="welcome-glyph"><SpiralMark size={48} /></div>
              <h1 className="welcome-title">你好，我是研究助手</h1>
              <p className="welcome-subtitle">
                基于科学文献知识图谱的科研 Agent。
                <br />
                替你检索文献、盘点候选关系，每句话都挂可核对的来源。
              </p>
              <div className="welcome-prompts" data-testid="example-questions">
                {PROMPTS.map((prompt) => (
                  <button
                    key={prompt.label}
                    type="button"
                    className="prompt-card"
                    data-testid="prompt-card"
                    onClick={() => submit(prompt.label)}
                  >
                    <span className="prompt-card-wm" aria-hidden="true">
                      <svg viewBox="0 0 32 32" fill="none" className="prompt-card-wm-base">
                        <path d={SPIRAL_PATH} stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                      </svg>
                    </span>
                    <span className="prompt-card-label">{prompt.label}</span>
                    <span className="prompt-card-hint">{prompt.hint}</span>
                  </button>
                ))}
              </div>
              {agentHealth && !agentHealth.agentReady ? (
                <p
                  style={{
                    width: '100%', borderRadius: 'var(--radius-lg)', border: '1px solid rgba(220,38,38,.35)',
                    background: 'rgba(220,38,38,.06)', padding: '9px 14px', fontSize: 12.5, color: 'var(--danger)',
                    textAlign: 'left',
                  }}
                  data-testid="agent-not-ready"
                >
                  Agent 未就绪：{(agentHealth.missingSettings || []).join(', ') || agentHealth.healthError?.detail || '服务不可用'}
                </p>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="chat-messages" data-testid="agent-thread">
            {turns.map((turn, index) => (
              <TurnView
                key={turn.runId || `turn-${index}`}
                turn={turn}
                index={index}
                isLast={index === lastIndex}
                traceOpen={(index === lastIndex) !== flippedTraces.has(index)}
                onToggleTrace={() => toggleTrace(index)}
                onCited={onCited}
              />
            ))}
          </div>
        )}
      </div>

      <div className="chat-composer-stack">
        <div className="chat-input-container" data-testid="composer">
          <textarea
            className="chat-input"
            value={draft}
            placeholder={hasThread ? '继续追问，我会带着前面的上下文去查…（Shift+Enter 换行）' : '问点什么吧…（Shift+Enter 换行）'}
            data-testid="agent-input"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
          />
          <div className="composer-toolbar">
            <div className="composer-left">
              <div className="composer-pills">
                <button
                  type="button"
                  className={`composer-pill ${railOpen ? 'is-on' : ''}`}
                  data-testid="rail-toggle"
                  data-rail={railOpen ? 'open' : 'closed'}
                  onClick={onToggleRail}
                  title="在右侧展开证据链，查看本会话命中的全部论文"
                >
                  <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></svg>
                  证据链
                  <span data-testid="rail-count">{railCount}</span>
                </button>
              </div>
            </div>
            <div className="chat-input-actions">
              <button
                type="button"
                className={`chat-send-btn ${busy || draft.trim() === '' ? 'is-disabled' : ''}`}
                data-testid="agent-submit"
                disabled={busy || draft.trim() === ''}
                onClick={() => submit()}
                aria-label="发送"
              >
                <svg viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            </div>
          </div>
        </div>
        <div className="chat-disclaimer" data-testid="agent-hint">
          连续追问会带上本会话的此前问答作为上下文 · 候选关系图谱 · 题名级证据 · 无引用数据（不回答被引次数/引用链）
        </div>
      </div>
    </div>
  );
}

/** 单轮：用户气泡 + 助手气泡（思考链 + 流式正文 + 引用核查）。 */
function TurnView({ turn, index, isLast, traceOpen, onToggleTrace, onCited }) {
  const busy = turn.status === 'running';
  // 思考链：结构/交互与 NOESIS ThinkingChain 同构（见 ThinkingChain.jsx）。
  // 推演 = turn.reasoning（reasoning_delta + 工具边界重分类，见 App.jsx）。
  const hasChain = busy || turn.events.length > 0 || Boolean(turn.reasoning);
  const evidenceIds = useMemo(() => {
    const seen = [];
    for (const event of turn.events) {
      for (const id of event?.evidenceIds || []) {
        if (!seen.includes(id)) seen.push(id);
      }
    }
    return seen;
  }, [turn.events]);
  const verdict = turn.citation || (turn.answer ? citationReport(turn.answer, evidenceIds) : null);
  // 引用上标的可读标签：把本轮的论文卡（题名 + 年份）汇总成 id → 标签，
  // 用户 hover 上标就看到「题名（年份）」而不是一串 DBLP 键。没有标签的 id 退回裸 id ——
  // 宁可显示得朴素，也不假装有标签。
  const labelById = useMemo(() => {
    const map = new Map();
    for (const event of turn.events) {
      for (const item of event?.summary?.paperItems || []) {
        if (!item?.publicationId || map.has(item.publicationId)) continue;
        const title = item.title || item.publicationId;
        map.set(item.publicationId, item.year ? `${title}（${item.year}）` : title);
      }
    }
    return map;
  }, [turn.events]);
  const blocks = useMemo(
    () => (turn.answer ? renderAnswer(turn.answer, verdict?.citedIds || [], onCited, labelById) : null),
    [turn.answer, verdict, onCited, labelById],
  );
  const tid = (name) => (isLast ? name : `${name}-${index}`);

  return (
    <>
      <div className="message-bubble is-user">
        <div className="message-avatar is-user">{USER_ICON}</div>
        <div className="message-column is-user">
          <div className="message-body--user" data-testid={isLast ? 'agent-question' : tid('question')}>{turn.question}</div>
        </div>
      </div>

      <div className="message-bubble">
        <div className="message-avatar" aria-hidden="true"><SpiralMark size={30} strokeWidth={2} /></div>
        <div className="message-column">
          <div className={`message-body--assistant ${hasChain ? 'has-trace' : ''}`}>
            <ThinkingChain
              events={turn.events}
              reasoning={turn.reasoning || ''}
              running={busy}
              open={traceOpen}
              onToggle={onToggleTrace}
              traceTestId={isLast ? 'agent-trace' : tid('trace')}
            />

            {blocks ? (
              <div className="message-text" data-testid={isLast ? 'agent-answer' : tid('answer')}>
                {blocks}
                {busy ? <span className="cursor-blink" aria-hidden="true" /> : null}
              </div>
            ) : null}

            {verdict ? (
              <>
                <div
                  className={`okcard ${verdict.passes ? '' : 'fail'}`}
                  data-testid={isLast ? 'citation-verdict' : tid('verdict')}
                  data-passes={verdict.passes ? 'true' : 'false'}
                >
                  <svg
                    className="ic"
                    viewBox="0 0 24 24"
                    style={{ stroke: verdict.passes ? 'var(--success)' : 'var(--danger)', fill: 'none', strokeWidth: 1.8 }}
                  >
                    {verdict.passes ? <path d="M20 6 9 17l-5-5" /> : <path d="M18 6 6 18M6 6l12 12" />}
                  </svg>
                  <div>
                    <b>{verdict.passes ? '引用核查通过' : '引用核查不通过'}</b>
                    <div className="sub">
                      回答里实际引用 {verdict.cited} / 可用 {verdict.available} 条 · 按句可溯率{' '}
                      {verdict.attributedSentences}/{verdict.consideredSentences} ={' '}
                      {Math.round(verdict.citationRate * 100)}% · 证据等级：
                      {(verdict.evidenceLevels || []).join('、') || '—'}
                    </div>
                    {verdict.citedIds?.length ? (
                      <div className="ids" data-testid="cited-ids">
                        {verdict.citedIds.map((id) => (
                          <button
                            key={id}
                            type="button"
                            className="pill"
                            data-testid="cited-id"
                            data-cited-id={id}
                            title={id}
                            onClick={() => onCited(id)}
                          >
                            {id}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
                {verdict.titleOnly ? (
                  <div className="warn" data-testid="title-only-warning">
                    以上证据全部是<b>题名级</b>：只能证明这些论文存在、题名里出现了相关词，
                    <b>不能证明</b>它们真的做了回答里描述的事。
                  </div>
                ) : null}
              </>
            ) : null}

            {turn.error ? (
              <div className="banner" data-testid="agent-error" role="alert" style={{ marginLeft: 0, marginRight: 0 }}>
                <div className="t">{turn.error.title}</div>
                <div className="d">{turn.error.detail}</div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}
