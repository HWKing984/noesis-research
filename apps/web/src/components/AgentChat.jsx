import React, { useMemo, useState } from 'react';

import { describeStep } from '../lib/agentApi.js';
import { citationReport } from '../lib/evidence.js';
import { renderAnswer } from '../lib/answerRender.jsx';

const EXAMPLES = [
  '有哪些关于 transformer 的论文？',
  '扩散模型在图像生成上的工作有哪些？',
  '图神经网络用在异常检测的有哪些？',
  '2025 年 CVPR 的扩散 transformer',
];

/**
 * 科研助手（主界面）：一句话提问 → agent 自己去查 → 过程与证据流回来。
 * 刻意简单：一个输入框、一串步骤、一段回答、一个引用核查结论。
 * 运行状态由 App 持有（右栏证据链要读同一份事件流），本组件只负责呈现与发起。
 */
export default function AgentChat({ run, onAsk, onCited, agentHealth }) {
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
    <div className="stage" data-testid="agent-chat">
      {!hasThread ? (
        <div className="col" style={{ flexDirection: 'column' }}>
          <div className="hero" data-testid="agent-intro">
            <h1>今天研究什么？</h1>
            <p className="sub">
              我会在这 {agentHealth?.scope?.bibliographyTitles ?? '2 万'} 篇文献的候选关系图谱上检索，
              边查边把过程和证据摆给你。
            </p>
            <div className="ex" data-testid="example-questions">
              {EXAMPLES.map((example) => (
                <button key={example} type="button" data-testid="example-question" onClick={() => submit(example)}>
                  {example}
                </button>
              ))}
            </div>
            <div className="caps">
              <div className="cap">
                <div className="t"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>自主检索</div>
                <div className="d">自己决定查什么、查几次，过程全部可见</div>
              </div>
              <div className="cap">
                <div className="t"><svg viewBox="0 0 24 24"><path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="9" /></svg>句句有来源</div>
                <div className="d">每个事实断句都挂记录 id，可点开核对</div>
              </div>
              <div className="cap">
                <div className="t"><svg viewBox="0 0 24 24"><path d="M12 9v4M12 17h.01" /><circle cx="12" cy="12" r="9" /></svg>边界诚实</div>
                <div className="d">候选关系不说成结论；没有引用数据就拒答</div>
              </div>
            </div>
            {agentHealth && !agentHealth.agentReady ? (
              <p
                style={{
                  marginTop: 18, borderRadius: 'var(--radius-lg)', border: '1px solid rgba(220,38,38,.35)',
                  background: 'rgba(220,38,38,.06)', padding: '9px 14px', fontSize: 12.5, color: 'var(--danger)',
                  textAlign: 'left',
                }}
                data-testid="agent-not-ready"
              >
                Agent 未就绪：{(agentHealth.missingSettings || []).join(', ') || agentHealth.healthError?.detail || '服务不可用'}
              </p>
            ) : null}
          </div>
          {/* 提问前也要有输入区：hero 只负责引导，打字入口必须在（原型如此，落码时曾漏掉） */}
          <div className="composer">
            <div className="cbox">
              <textarea
                rows={1}
                value={draft}
                placeholder="问一个科研问题，例如：扩散模型在图像生成上的工作有哪些？"
                data-testid="agent-input"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    submit();
                  }
                }}
              />
              <button
                type="button"
                className="send"
                data-testid="agent-submit"
                disabled={busy || draft.trim() === ''}
                onClick={() => submit()}
                aria-label="发送"
              >
                <svg viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            </div>
            <div className="chint" data-testid="agent-hint">
              候选关系图谱 · 题名级证据 · 无引用数据（不回答被引次数/引用链） · 证据链可从右上角打开
            </div>
          </div>
        </div>
      ) : (
        <div className="col" style={{ flexDirection: 'column' }}>
          <div className="thread" data-testid="agent-thread">
            {run.question ? <div className="msg-user" data-testid="agent-question">{run.question}</div> : null}
            <div className="msg-ai">
              {steps.length > 0 ? (
                <div className={`trace ${traceOpen ? 'is-open' : ''}`} data-testid="agent-trace">
                  <button
                    type="button"
                    className="trace-sum"
                    data-testid="agent-trace-toggle"
                    onClick={() => setTraceOpen((prev) => !prev)}
                  >
                    <svg viewBox="0 0 24 24">
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

              {busy && steps.length === 0 ? (
                <p style={{ color: 'var(--text-tertiary)', fontSize: 13 }} data-testid="agent-thinking">
                  正在检索图谱…
                </p>
              ) : null}

              {blocks ? <div data-testid="agent-answer">{blocks}</div> : null}

              {verdict ? (
                <>
                  <div
                    className={`okcard ${verdict.passes ? '' : 'fail'}`}
                    style={{ marginTop: 14 }}
                    data-testid="citation-verdict"
                    data-passes={verdict.passes ? 'true' : 'false'}
                  >
                    <svg
                      className="ic"
                      viewBox="0 0 24 24"
                      style={{
                        stroke: verdict.passes ? 'var(--success)' : 'var(--danger)',
                        fill: 'none',
                        strokeWidth: 1.8,
                      }}
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
                    <div className="warn" style={{ marginTop: 9 }} data-testid="title-only-warning">
                      以上证据全部是<b>题名级</b>：只能证明这些论文存在、题名里出现了相关词，
                      <b>不能证明</b>它们真的做了回答里描述的事。
                    </div>
                  ) : null}
                </>
              ) : null}

              {run.error ? (
                <div
                  className="banner"
                  data-testid="agent-error"
                  role="alert"
                  style={{ marginLeft: 0, marginRight: 0 }}
                >
                  <div className="t">{run.error.title}</div>
                  <div className="d">{run.error.detail}</div>
                </div>
              ) : null}
            </div>
          </div>

          <div className="composer">
            <div className="cbox">
              <textarea
                rows={1}
                value={draft}
                placeholder="继续追问，例如：这几篇里哪些是候选断言？"
                data-testid="agent-input"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    submit();
                  }
                }}
              />
              <button
                type="button"
                className="send"
                data-testid="agent-submit"
                disabled={busy || draft.trim() === ''}
                onClick={() => submit()}
                aria-label="发送"
              >
                <svg viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            </div>
            <div className="chint" data-testid="agent-hint">
              {run.runId ? <span className="mono" style={{ marginRight: 8 }}>run {run.runId.slice(0, 8)}</span> : null}
              候选关系图谱 · 题名级证据 · 无引用数据（不回答被引次数/引用链） · 证据链可从右上角打开
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
