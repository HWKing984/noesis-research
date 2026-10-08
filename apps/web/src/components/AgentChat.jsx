import React, { useMemo, useState } from 'react';

import { describeStep } from '../lib/agentApi.js';
import { citationReport } from '../lib/evidence.js';
import { renderAnswer } from '../lib/answerRender.jsx';
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
 * 科研助手 —— 页面结构与视觉逐项照搬 NOESIS ChatArea：
 * 头部（左标题 / 居中胶囊页签 / 右状态）、空态（螺旋标 + 衬线标题 + 2×2 建议卡）、
 * 消息气泡（蓝用户泡 / bg-elevated 助手泡 + 螺线头像）、
 * 输入区（内嵌工具行 + 焦点环 + 证据链胶囊）、底部免责一行。
 * 回答按 token 增量流式渲染（answer_delta），生成中带光标。
 */
export default function AgentChat({ run, onAsk, onCited, agentHealth, view, onView, railOpen, onToggleRail, railCount = 0 }) {
  const [draft, setDraft] = useState('');
  const [traceOpen, setTraceOpen] = useState(false);

  const busy = run.status === 'running';
  const steps = useMemo(() => run.events.map(describeStep).filter(Boolean), [run.events]);
  const evidenceIds = useMemo(() => {
    const seen = [];
    for (const event of run.events) {
      for (const id of event?.evidenceIds || []) {
        if (!seen.includes(id)) seen.push(id);
      }
    }
    return seen;
  }, [run.events]);
  const verdict = run.citation || (run.answer ? citationReport(run.answer, evidenceIds) : null);
  const blocks = useMemo(
    () => (run.answer ? renderAnswer(run.answer, verdict?.citedIds || [], onCited) : null),
    [run.answer, verdict, onCited],
  );
  const hasThread = run.events.length > 0 || Boolean(run.answer) || Boolean(run.question);

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
          {run.question || '新研究'}
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
            {run.question ? (
              <div className="message-bubble is-user" data-testid="agent-question">
                <div className="message-avatar is-user">{USER_ICON}</div>
                <div className="message-column is-user">
                  <div className="message-body--user">{run.question}</div>
                </div>
              </div>
            ) : null}

            <div className="message-bubble">
              <div className="message-avatar" aria-hidden="true"><SpiralMark size={30} strokeWidth={2} /></div>
              <div className="message-column">
                <div className={`message-body--assistant ${steps.length ? 'has-trace' : ''}`}>
                  {steps.length > 0 ? (
                    <div className={`trace ${traceOpen ? 'is-open' : ''}`} data-testid="agent-trace">
                      <button
                        type="button"
                        className="trace-sum"
                        data-testid="agent-trace-toggle"
                        onClick={() => setTraceOpen((prev) => !prev)}
                      >
                        <svg viewBox="0 0 24 24" fill="none">
                          <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
                        </svg>
                        已执行 {steps.length} 步 · 可用证据 {evidenceIds.length} 条
                        <span className="n">{traceOpen ? '收起' : '展开'}</span>
                      </button>
                      <div className="trace-body" data-testid="agent-steps">
                        {steps.map((step, index) => (
                          <div
                            key={`${step.label}-${index}`}
                            className={`tstep ${step.icon === 'error' ? 'is-error' : ''}`}
                            data-testid="agent-step"
                            data-step-icon={step.icon}
                          >
                            <span className="t">{step.label}</span>
                            <span>{step.detail}</span>
                          </div>
                        ))}
                        {busy ? (
                          <div className="tstep" data-testid="agent-step-running">
                            <span className="t">…</span>
                            <span>正在检索图谱…</span>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {busy && steps.length === 0 && !run.answer ? (
                    <p style={{ color: 'var(--text-tertiary)', fontSize: 13 }} data-testid="agent-thinking">
                      正在检索图谱…
                    </p>
                  ) : null}

                  {blocks ? (
                    <div className="message-text" data-testid="agent-answer">
                      {blocks}
                      {busy ? <span className="cursor-blink" aria-hidden="true" /> : null}
                    </div>
                  ) : null}

                  {verdict ? (
                    <>
                      <div
                        className={`okcard ${verdict.passes ? '' : 'fail'}`}
                        data-testid="citation-verdict"
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
                          {!verdict.passes ? (
                            <div className="sub" style={{ color: 'var(--danger)' }}>
                              这条回答没有任何来源 id —— 按本项目验收口径，它是一次失败的回答，不是"差不多能用"。
                            </div>
                          ) : null}
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

                  {run.error ? (
                    <div className="banner" data-testid="agent-error" role="alert" style={{ marginLeft: 0, marginRight: 0 }}>
                      <div className="t">{run.error.title}</div>
                      <div className="d">{run.error.detail}</div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="chat-composer-stack">
        <div className="chat-input-container" data-testid="composer">
          <textarea
            className="chat-input"
            value={draft}
            placeholder="问点什么吧…（Shift+Enter 换行）"
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
                  title="在右侧展开证据链，查看本次检索命中的全部论文"
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
          {run.runId ? <span className="mono" style={{ marginRight: 8 }}>run {run.runId.slice(0, 8)}</span> : null}
          NOESIS Research 生成内容不构成专业意见；引用均为题名级证据，请核对原文。
        </div>
      </div>
    </div>
  );
}
