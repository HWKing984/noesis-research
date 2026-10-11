import React, { useEffect, useMemo, useRef, useState } from 'react';

import { toChainModel } from '../lib/chainModel.js';

/**
 * 思考链 —— 与 NOESIS `ChatArea.jsx::ThinkingChain` 同构的移植版。
 *
 * 结构 / 类名 / 交互逐字对齐（.thinking-area / .thinking-status-pill /
 * .thinking-timeline-* / 工具簇限长 260px + 上下模糊 seam / 完成后绿点胶囊），
 * 供后续融合迁移时组件上收或事件改道两条路都不返工。差异只有三处，都是刻意的：
 * 1. thinking-orbs 动效球暂用 CSS 点阵近似（本仓库未携带该依赖；融合进 NOESIS
 *    时换成 `import { ThinkingOrb } from 'thinking-orbs'` 一行即可）；
 * 2. 展开态由宿主控制（研究侧纪律：会话最后一轮完成后保持展开 ——见 AgentChat）；
 * 3. 模型推演文本 = turn.reasoning（reasoning_delta + 工具边界重分类），
 *    流式时逐字增长，天然是"打字机"，无需再造动画。
 */

/* 与原型一致的点阵球：thinking-orbs「solving」20px 预设的 CSS 近似 */
const ORB_DOTS = [
  [0, 0], [6.6, 0], [-6.6, 0], [0, 6.6], [0, -6.6],
  [4.7, 4.7], [-4.7, 4.7], [4.7, -4.7], [-4.7, -4.7],
  [3.2, 6.6], [-3.2, -6.6], [6.6, 3.2], [-6.6, -3.2],
];

function ThinkingOrbMark() {
  return (
    <span className="thinking-orb" aria-hidden="true">
      {ORB_DOTS.map((dot, index) => (
        <i
          key={index}
          style={{
            left: `${(10 + dot[0] - 1.3).toFixed(1)}px`,
            top: `${(10 + dot[1] - 1.3).toFixed(1)}px`,
            animationDelay: `${(-(index * 0.13)).toFixed(2)}s`,
          }}
        />
      ))}
    </span>
  );
}

/* 固定 20px 状态槽：思考中装球、完成装绿点，切换时行高与基线不跳 */
function ThinkingMark({ active }) {
  return (
    <span className="thinking-mark">
      {active ? <ThinkingOrbMark /> : <span className="thinking-status-dot thinking-status-dot--done" />}
    </span>
  );
}

function Chevron({ open }) {
  return (
    <svg
      className={`thinking-chain-chevron ${open ? 'thinking-chain-chevron--open' : ''}`}
      width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="chk" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

/* 滚动窗口的模糊 seam：哪一侧真的能滚才显示哪一条（与 NOESIS 同一套判据） */
function useSeams(ref, content) {
  const [seams, setSeams] = useState({ top: false, bottom: false });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const canScroll = el.scrollHeight - el.clientHeight > 4;
    setSeams({
      top: canScroll && el.scrollTop > 4,
      bottom: canScroll && el.scrollTop + el.clientHeight < el.scrollHeight - 4,
    });
  }, [ref, content]);
  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    const canScroll = el.scrollHeight - el.clientHeight > 4;
    setSeams({
      top: canScroll && el.scrollTop > 4,
      bottom: canScroll && el.scrollTop + el.clientHeight < el.scrollHeight - 4,
    });
  };
  return { seams, onScroll };
}

/* 流式时跟随到底；用户上翻超过阈值即暂停（不与用户"拔河"） */
function useAutoFollow(ref, content, active) {
  const followRef = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (active && followRef.current) el.scrollTop = el.scrollHeight;
  }, [ref, content, active]);
  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distance > 48) followRef.current = false;
    else if (distance <= 12) followRef.current = true;
  };
  return onScroll;
}

/* 模型推演正文：无框流动文本 + 上下模糊 seam（值与 NOESIS 同） */
function ModelThinkingContent({ text, active }) {
  const ref = useRef(null);
  const { seams, onScroll } = useSeams(ref, text);
  const follow = useAutoFollow(ref, text, active);
  return (
    <div className="thinking-model-window">
      <div
        ref={ref}
        className="thinking-item-text thinking-item-text--model"
        onScroll={(event) => { follow(event); onScroll(event); }}
      >
        {String(text || '').split('\n\n').map((para, index) => (
          <p key={index}>{para}</p>
        ))}
      </div>
      <span className={`thinking-model-seam thinking-model-seam--top${seams.top ? ' thinking-model-seam--show' : ''}`} aria-hidden="true" />
      <span className={`thinking-model-seam thinking-model-seam--bottom${seams.bottom ? ' thinking-model-seam--show' : ''}`} aria-hidden="true" />
    </div>
  );
}

/* 工具明细卡（近似 NOESIS McpToolActivity embedded；命中论文 ≤4 条 + 证据 chips） */
function ToolCard({ item }) {
  const papers = Array.isArray(item.summary?.paperItems) ? item.summary.paperItems : [];
  const paperCap = papers.slice(0, 4);
  const paperMore = Math.max(0, papers.length - paperCap.length);
  const levels = item.levels;
  return (
    <details className="mcp-tool-activity__item is-result" open>
      <summary>
        <span className="mcp-tool-activity__status"><CheckIcon /></span>
        <span className="tn">{item.label}</span>
        <span className="to">{item.outcome}</span>
        <svg className="caret" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </summary>
      <div className="mcp-tool-activity__details">
        {item.args ? <div className="mcp-tool-activity__query">{item.args}</div> : null}
        {paperCap.length ? (
          <div className="mcp-tool-activity__resources">
            {paperCap.map((paper, index) => (
              <div className="mcp-tool-activity__resource" key={paper.publicationId || index}>
                <span>《{paper.title || paper.publicationId}》</span>
                <small>{[paper.year, paper.verificationStatus === 'id_valid' ? '标识已核实' : ''].filter(Boolean).join(' · ')}</small>
              </div>
            ))}
            {paperMore > 0 ? <span className="mcp-tool-activity__more">另有 {paperMore} 条资料（右栏证据链可查）</span> : null}
          </div>
        ) : null}
        {item.chips?.length ? (
          <div className="mcp-tool-activity__evi">
            {item.chips.map((chip) => (
              <span key={chip.id} className={`chip${chip.level === 'abstract' ? ' is-abs' : ''}`} title={chip.level === 'abstract' ? '摘要级证据' : chip.level === 'title' ? '题名级证据' : '证据 id'}>
                {chip.id}
              </span>
            ))}
            {item.more > 0 ? <span className="chip">+{item.more}</span> : null}
          </div>
        ) : null}
        {levels ? (
          <div className="mcp-tool-activity__meta">
            证据等级：题名级 ×{levels.title} · 摘要级 ×{levels.abstract}
          </div>
        ) : null}
      </div>
    </details>
  );
}

/** 思考链主体。running=流式中；open/onToggle 由宿主控制（研究侧：最后一轮完成后保持展开）。
 *  traceTestId：主 testid 只标最后一轮（AgentChat 的验收口径），历史轮传后缀名。 */
export default function ThinkingChain({ events, reasoning, running, open, onToggle, traceTestId = 'agent-trace' }) {
  const { items, evidenceCount } = useMemo(() => toChainModel(events, reasoning), [events, reasoning]);
  const clusterRef = useRef(null);
  const clusterContent = items.filter((item) => item.kind === 'tool').length;
  const { seams, onScroll } = useSeams(clusterRef, clusterContent);
  const follow = useAutoFollow(clusterRef, clusterContent, running);

  // 与 NOESIS 同判据：非流式且没有任何条目 → 整块不渲染（不留空壳）
  if (!running && items.length === 0) return null;

  const steps = items.filter((item) => item.kind !== 'tool');
  const tools = items.filter((item) => item.kind === 'tool');

  const renderStep = (item, index) => {
    if (item.kind === 'reasoning') {
      return (
        <div
          key={`reasoning-${index}`}
          className={`thinking-timeline-item thinking-timeline-item--${running ? 'active' : 'done'} thinking-timeline-item--model`}
          data-testid="agent-step"
          data-step-icon={item.icon}
        >
          <div className="thinking-timeline-rail" aria-hidden="true">
            <ThinkingMark active={running} />
            <span className="thinking-timeline-line" />
          </div>
          <div className="thinking-timeline-content">
            <span className="thinking-item-label">{item.label}</span>
            <ModelThinkingContent text={item.text} active={running} />
          </div>
        </div>
      );
    }
    return (
      <div
        key={`${item.kind}-${item.label}-${index}`}
        className="thinking-timeline-item thinking-timeline-item--done"
        data-testid="agent-step"
        data-step-icon={item.icon}
      >
        <div className="thinking-timeline-rail" aria-hidden="true">
          <ThinkingMark active={false} />
          <span className="thinking-timeline-line" />
        </div>
        <div className="thinking-timeline-content">
          <span className="thinking-item-label">{item.label}</span>
          <div className="thinking-item-text">{item.text}</div>
        </div>
      </div>
    );
  };

  return (
    <section
      className={`thinking-area ${running ? 'thinking-area--streaming' : ''}`}
      data-testid={traceTestId}
      data-evidence-count={evidenceCount}
    >
      <button
        type="button"
        className="thinking-area-header thinking-status-pill"
        aria-expanded={open ? 'true' : 'false'}
        aria-label={`${running ? '正在思考' : '思考完成'}，${open ? '收起' : '展开'}思考过程`}
        data-testid="agent-trace-toggle"
        onClick={onToggle}
      >
        <ThinkingMark active={running} />
        <span className="thinking-pill-label" aria-live="polite">
          {running ? '深度思考中...' : '思考完成'}
        </span>
        {items.length > 0 ? <span className="thinking-item-count">{items.length} 项</span> : null}
        <Chevron open={open} />
      </button>

      {open ? (
        <div className="thinking-area-body" data-testid="agent-steps">
          <div className="thinking-timeline">
            {steps.map((item, index) => renderStep(item, index))}

            {tools.length > 0 ? (
              <div className="thinking-tool-window">
                <div
                  ref={clusterRef}
                  className="thinking-tool-cluster"
                  onScroll={(event) => { follow(event); onScroll(event); }}
                >
                  {tools.map((item, index) => (
                    <div
                      key={`${item.label}-${index}`}
                      className="thinking-timeline-item thinking-timeline-item--done"
                      data-testid="agent-step"
                      data-step-icon={item.icon}
                    >
                      <div className="thinking-timeline-rail" aria-hidden="true">
                        <ThinkingMark active={false} />
                        <span className="thinking-timeline-line" />
                      </div>
                      <div className="thinking-timeline-content">
                        <section className="mcp-tool-activity mcp-tool-activity--embedded" aria-label="工具调用">
                          <ToolCard item={item} />
                        </section>
                      </div>
                    </div>
                  ))}
                </div>
                <span className={`thinking-tool-seam thinking-tool-seam--top${seams.top ? ' thinking-tool-seam--show' : ''}`} aria-hidden="true" />
                <span className={`thinking-tool-seam thinking-tool-seam--bottom${seams.bottom ? ' thinking-tool-seam--show' : ''}`} aria-hidden="true" />
              </div>
            ) : null}

            {running && items.length === 0 ? (
              <div className="thinking-timeline-empty">正在整理问题并选择下一步...</div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
