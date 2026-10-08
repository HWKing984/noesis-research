import React, { useCallback, useEffect, useRef, useState } from 'react';

import { createAgentApi, describeAgentError, describeStep } from '../lib/agentApi.js';
import { citationReport } from '../lib/evidence.js';

const EXAMPLES = [
  '有哪些关于 transformer 的论文？',
  '扩散模型在图像生成上的工作有哪些？',
  '图神经网络用在异常检测的有哪些？',
];

/**
 * 科研助手 —— 本产品的主界面。
 *
 * 一句话输入 → agent 自己去查 → 过程与证据流回来。刻意做得简单：
 * 一个输入框、一串步骤、一段回答、一个引用核查结论。没有多余的栏。
 */
export default function AgentChat({ api: injectedApi, onOpenPaper }) {
  const api = React.useMemo(() => injectedApi || createAgentApi(), [injectedApi]);

  const [question, setQuestion] = useState('');
  const [runId, setRunId] = useState(null);
  const [events, setEvents] = useState([]);
  const [answer, setAnswer] = useState('');
  const [citation, setCitation] = useState(null);
  const [status, setStatus] = useState('idle'); // idle | running | ok | failed
  const [error, setError] = useState(null);
  const [agentHealth, setAgentHealth] = useState(null);
  const sourceRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((payload) => {
        if (!cancelled) setAgentHealth(payload);
      })
      .catch((cause) => {
        if (!cancelled) setAgentHealth({ agentReady: false, healthError: describeAgentError(cause) });
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(
    () => () => {
      try {
        sourceRef.current?.close();
      } catch {
        /* ignore */
      }
    },
    [],
  );

  const ask = useCallback(
    async (text) => {
      const prompt = (text ?? question).trim();
      if (!prompt || status === 'running') return;

      try {
        sourceRef.current?.close();
      } catch {
        /* ignore */
      }

      setQuestion(prompt);
      setEvents([]);
      setAnswer('');
      setCitation(null);
      setError(null);
      setRunId(null);
      setStatus('running');

      let started;
      try {
        started = await api.startRun(prompt);
      } catch (cause) {
        setError(describeAgentError(cause));
        setStatus('failed');
        return;
      }
      setRunId(started.runId);

      const source = new EventSource(api.eventsUrl(started.runId));
      sourceRef.current = source;

      source.addEventListener('run_started', () => {});
      source.addEventListener('tool_call', (message) => {
        setEvents((prev) => [...prev, JSON.parse(message.data)]);
      });
      source.addEventListener('tool_result', (message) => {
        setEvents((prev) => [...prev, JSON.parse(message.data)]);
      });
      source.addEventListener('tool_error', (message) => {
        setEvents((prev) => [...prev, JSON.parse(message.data)]);
      });
      source.addEventListener('answer', (message) => {
        const payload = JSON.parse(message.data);
        setAnswer(payload.text || '');
        setCitation(payload.citation || null);
      });
      source.addEventListener('failed', (message) => {
        setEvents((prev) => [...prev, JSON.parse(message.data)]);
        setStatus('failed');
      });
      source.addEventListener('done', () => {
        setStatus((prev) => (prev === 'failed' ? 'failed' : 'ok'));
        source.close();
        sourceRef.current = null;
      });
      source.onerror = () => {
        // 流断了要区分"正常收尾"与"真的连不上"
        setStatus((prev) => {
          if (prev === 'running') {
            setError({
              title: '事件流中断',
              detail: '没能读到 Agent 的完整事件流。这次结果不算数，请重试。',
              kind: 'offline',
            });
            return 'failed';
          }
          return prev;
        });
        source.close();
        sourceRef.current = null;
      };
    },
    [api, question, status],
  );

  // 兜底：即使服务端没给 citation 事件，也用同一条纯函数规则在本地算一遍
  const evidenceIds = events.flatMap((event) => event.evidenceIds || []);
  const localCitation = answer ? citationReport(answer, [...new Set(evidenceIds)]) : null;
  const verdict = citation || localCitation;

  const steps = events.map(describeStep).filter(Boolean);

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col" data-testid="agent-chat">
      <div className="min-h-0 flex-1 overflow-auto px-6 py-6">
        {status === 'idle' && steps.length === 0 ? (
          <div className="pt-10 text-center" data-testid="agent-intro">
            <h2 className="text-[18px] font-semibold">问一句，它自己去查</h2>
            <p className="mx-auto mt-2 max-w-md text-[13px] text-[var(--ink-muted)]">
              Agent 会在 2 万篇 DBLP 文献的候选关系图谱上检索，边查边把调用的工具与拿到的证据
              显示出来。回答里的每句话都要挂来源 id，挂不上就判失败。
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => ask(example)}
                  data-testid="example-question"
                  className="rounded-full border border-[var(--line)] bg-[var(--panel)] px-3 py-1.5 text-[12px] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                >
                  {example}
                </button>
              ))}
            </div>
            {agentHealth && !agentHealth.agentReady ? (
              <p className="mt-5 rounded-lg border border-[#f0c9c5] bg-[var(--danger-soft)] px-3 py-2 text-[12px] text-[var(--danger)]">
                Agent 未就绪：{agentHealth.healthError?.detail || `缺少 ${(agentHealth.missingSettings || []).join(', ')}`}
              </p>
            ) : null}
          </div>
        ) : null}

        {steps.length > 0 ? (
          <ol className="space-y-1.5" data-testid="agent-steps">
            {steps.map((step, index) => (
              <li
                key={`${step.label}-${index}`}
                data-testid="agent-step"
                data-step-icon={step.icon}
                className={`flex items-start gap-2 rounded border px-3 py-1.5 text-[12px] ${
                  step.icon === 'error'
                    ? 'border-[#f0c9c5] bg-[var(--danger-soft)] text-[var(--danger)]'
                    : 'border-[var(--line)] bg-[var(--panel)]'
                }`}
              >
                <span className="mono mt-[1px] w-4 shrink-0 text-[10px] text-[var(--ink-muted)]">
                  {index + 1}
                </span>
                <span className="font-medium">{step.label}</span>
                <span className="text-[var(--ink-muted)]">{step.detail}</span>
                {step.evidenceIds?.length ? (
                  <span className="mono ml-auto shrink-0 text-[10px] text-[var(--ink-muted)]">
                    {step.evidenceIds.length} 条证据
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        ) : null}

        {status === 'running' && steps.length === 0 ? (
          <p className="mt-4 text-[13px] text-[var(--ink-muted)]" data-testid="agent-thinking">
            正在检索图谱…
          </p>
        ) : null}

        {answer ? (
          <section className="mt-5" data-testid="agent-answer-block">
            <h3 className="mb-1.5 text-[13px] font-medium">回答</h3>
            <div
              className="whitespace-pre-wrap rounded-lg border border-[var(--line)] bg-[var(--panel)] px-4 py-3 text-[13px] leading-relaxed"
              data-testid="agent-answer"
            >
              {answer}
            </div>

            {verdict ? (
              <div
                className={`mt-3 rounded-lg border px-3 py-2 text-[12px] ${
                  verdict.passes
                    ? 'border-[#bfe0c5] bg-[#f2fbf4] text-[#1a7f37]'
                    : 'border-[#f0c9c5] bg-[var(--danger-soft)] text-[var(--danger)]'
                }`}
                data-testid="citation-verdict"
                data-passes={verdict.passes ? 'true' : 'false'}
              >
                <b>{verdict.passes ? '引用核查通过' : '引用核查不通过'}</b>
                <span className="ml-2">
                  回答里实际引用 {verdict.cited} / 可用 {verdict.available} 条；
                  按句可溯率 {verdict.attributedSentences}/{verdict.consideredSentences} ={' '}
                  {Math.round(verdict.citationRate * 100)}%
                </span>
                {!verdict.passes ? (
                  <div className="mt-1">
                    这条回答没有任何来源 id —— 按本项目验收口径，它是一次<strong>失败</strong>的回答，
                    不是"差不多能用"。
                  </div>
                ) : null}
                {verdict.titleOnly ? (
                  <div
                    className="mt-2 rounded border border-[var(--candidate-soft)] bg-[var(--candidate-soft)] px-2 py-1 text-[var(--candidate)]"
                    data-testid="title-only-warning"
                  >
                    以上证据全部是<strong>题名级</strong>：只能证明这些论文存在、题名里出现了相关词，
                    <b>不能证明</b>它们真的做了回答里描述的事。
                  </div>
                ) : null}
                {verdict.citedIds?.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {verdict.citedIds.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => onOpenPaper?.(id)}
                        data-testid="cited-id"
                        className="mono rounded border border-current px-1.5 py-0.5 text-[11px] hover:underline"
                      >
                        {id}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {error ? (
          <div
            className="mt-4 rounded-lg border border-[#f0c9c5] bg-[var(--danger-soft)] px-3 py-2 text-[12px] text-[var(--danger)]"
            data-testid="agent-error"
            role="alert"
          >
            <b>{error.title}</b>
            <div className="mt-0.5">{error.detail}</div>
          </div>
        ) : null}
      </div>

      <form
        className="border-t border-[var(--line)] bg-[var(--panel)] px-6 py-3"
        data-testid="agent-form"
        onSubmit={(event) => {
          event.preventDefault();
          ask();
        }}
      >
        <div className="flex items-end gap-2">
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                ask();
              }
            }}
            rows={2}
            placeholder="问一个科研问题，例如：扩散模型在图像生成上的工作有哪些？"
            data-testid="agent-input"
            className="min-h-[52px] flex-1 resize-none rounded-lg border border-[var(--line)] px-3 py-2 text-[13px] outline-none focus:border-[var(--accent)]"
          />
          <button
            type="submit"
            disabled={status === 'running' || question.trim() === ''}
            data-testid="agent-submit"
            className="h-[52px] shrink-0 rounded-lg bg-[var(--accent)] px-5 text-[13px] font-medium text-white disabled:opacity-40"
          >
            {status === 'running' ? '检索中…' : '问'}
          </button>
        </div>
        <p className="mt-1.5 text-[11px] text-[var(--ink-muted)]">
          {runId ? <span className="mono mr-2">run {runId.slice(0, 8)}</span> : null}
          图谱为候选断言图；题名级证据只能证明论文存在，不能证明其结论。本图谱无引用数据，
          不回答「是否必引 / 被引次数 / 引用链」。
        </p>
      </form>
    </div>
  );
}
