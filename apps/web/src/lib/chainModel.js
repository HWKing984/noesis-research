/**
 * 研究事件流 → NOESIS 思考链模型（纯函数，可单测）。
 *
 * 目标形态与 NOESIS `frontend/src/components/ChatArea.jsx::ThinkingChain` 同构：
 * 运行级条目（推演 / 重试 / 错误）+ 工具调用条目，渲染组件 `ThinkingChain.jsx`
 * 直接消费本模块的输出。人话文案的唯一来源仍是 `agentApi.js`
 * （describeStep / toolOutcomeBits）—— 本模块只做归类与结构化，不另造文案。
 *
 * 推演文本的两个来源（在 App.jsx 汇合成 turn.reasoning）：
 * 1. 后端 `reasoning_delta`（模型自带思考通道 reasoning_content）；
 * 2. 工具边界重分类：工具步骤到达时，此前流出的"回答"其实是研究计划/过渡说明。
 */

import { describeStep, toolOutcomeBits } from './agentApi.js';

/** 参数 → 「query=… · limit=…」一行文本（与 describeStep 同规则）。 */
export function argsText(args) {
  return Object.entries(args || {})
    .filter(([, value]) => value !== '' && value !== null && value !== undefined)
    .map(([key, value]) => `${key}=${value}`)
    .join(' · ');
}

/** 事件 → 证据 chips（摘要级 / 题名级可辨）+ 层级计数；超出 cap 的折进 more。
 *  没有完整引用（evidenceRefs）时退回裸 id —— 宁可朴素，不假装有层级。 */
export function evidenceChips(event, cap = 4) {
  const refs = Array.isArray(event?.evidenceRefs) ? event.evidenceRefs : [];
  if (refs.length) {
    const levels = { title: 0, abstract: 0 };
    for (const ref of refs) {
      levels[ref?.evidenceLevel === 'abstract' ? 'abstract' : 'title'] += 1;
    }
    return {
      chips: refs.slice(0, cap).map((ref) => ({
        id: String(ref.sourceId || ''),
        level: ref.evidenceLevel === 'abstract' ? 'abstract' : 'title',
      })),
      more: Math.max(0, refs.length - cap),
      levels,
    };
  }
  const ids = Array.isArray(event?.evidenceIds) ? event.evidenceIds : [];
  return {
    chips: ids.slice(0, cap).map((id) => ({ id: String(id || ''), level: null })),
    more: Math.max(0, ids.length - cap),
    levels: null,
  };
}

/**
 * 事件流 + 推演文本 → 思考链条目。
 * 条目顺序 = NOESIS 口径：推演与运行级条目在前，工具调用集中进簇。
 * `done` 不产生条目 ——「思考完成」由状态胶囊承担（与 NOESIS 一致）。
 */
export function toChainModel(events, reasoning = '') {
  const list = Array.isArray(events) ? events : [];
  const steps = [];
  const tools = [];
  const seenIds = new Set();
  let evidenceCount = 0;

  if (String(reasoning || '').trim()) {
    steps.push({ kind: 'reasoning', icon: 'think', label: '研究推演', text: String(reasoning) });
  }

  for (const event of list) {
    if (!event || typeof event !== 'object') continue;
    if (event.type === 'tool_step') {
      const summary = event.summary || {};
      const chips = evidenceChips(event);
      tools.push({
        kind: 'tool',
        icon: 'tool',
        status: 'done',
        label: event.label || event.tool,
        args: argsText(event.args),
        outcome: toolOutcomeBits(summary).join(' · ') || '已返回',
        summary,
        ...chips,
      });
      for (const id of event.evidenceIds || []) {
        if (!seenIds.has(id)) {
          seenIds.add(id);
          evidenceCount += 1;
        }
      }
      continue;
    }
    if (event.type === 'tool_error' || event.type === 'failed') {
      const step = describeStep(event);
      steps.push({ kind: 'error', icon: 'error', label: step.label, text: step.detail });
      continue;
    }
    if (event.type === 'run_retry') {
      const step = describeStep(event);
      steps.push({ kind: 'retry', icon: 'retry', label: step.label, text: step.detail });
      continue;
    }
    // run_started / answer_delta / answer / done / reasoning_delta：不产生条目
  }

  return { items: [...steps, ...tools], evidenceCount };
}
