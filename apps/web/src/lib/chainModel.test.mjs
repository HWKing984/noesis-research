/**
 * 思考链模型单测（node 内置 runner；纯函数，无 JSX）。
 *
 *     node --test apps/web/src/lib/chainModel.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { argsText, evidenceChips, toChainModel } from './chainModel.js';

const TOOL_STEP = {
  type: 'tool_step',
  tool: 'search_papers',
  label: '检索论文',
  args: { query: 'diffusion model image generation', limit: 25 },
  summary: { papers: 18, applied: { q: 'diffusion model image generation' } },
  evidenceIds: ['a', 'b', 'c', 'd', 'e', 'f'],
  evidenceRefs: [
    { sourceId: 'a', evidenceLevel: 'abstract' },
    { sourceId: 'b', evidenceLevel: 'title' },
    { sourceId: 'c', evidenceLevel: 'title' },
    { sourceId: 'd', evidenceLevel: 'title' },
    { sourceId: 'e', evidenceLevel: 'title' },
    { sourceId: 'f', evidenceLevel: 'title' },
  ],
};

test('argsText 与 describeStep 同规则：空参数不出现 undefined', () => {
  assert.equal(argsText({ query: 'x', limit: 5 }), 'query=x · limit=5');
  assert.equal(argsText({}), '');
  assert.equal(argsText({ q: '' }), '');
});

test('证据 chips：摘要级/题名级可辨，超出上限折进 more，层级计数齐全', () => {
  const ev = evidenceChips(TOOL_STEP);
  assert.equal(ev.chips.length, 4);
  assert.equal(ev.chips[0].level, 'abstract');
  assert.equal(ev.chips[1].level, 'title');
  assert.equal(ev.more, 2);
  assert.deepEqual(ev.levels, { title: 5, abstract: 1 });
});

test('没有完整引用时退回裸 id（不假装有层级）', () => {
  const ev = evidenceChips({ evidenceIds: ['x', 'y'] });
  assert.deepEqual(ev.chips, [{ id: 'x', level: null }, { id: 'y', level: null }]);
  assert.equal(ev.levels, null);
  assert.equal(ev.more, 0);
});

test('tool_step → 工具条目：中文动作名 + 参数行 + 结果规模', () => {
  const { items } = toChainModel([TOOL_STEP]);
  assert.equal(items.length, 1);
  const item = items[0];
  assert.equal(item.kind, 'tool');
  assert.equal(item.icon, 'tool');
  assert.equal(item.label, '检索论文');
  assert.equal(item.args, 'query=diffusion model image generation · limit=25');
  assert.match(item.outcome, /命中 18 篇/);
  assert.equal(item.chips.length, 4);
});

test('推演文本成为第一条 reasoning 条目', () => {
  const { items } = toChainModel([TOOL_STEP], '先拆解问题：方法 → 任务检索。');
  assert.equal(items[0].kind, 'reasoning');
  assert.equal(items[0].icon, 'think');
  assert.equal(items[0].label, '研究推演');
  assert.match(items[0].text, /先拆解问题/);
  assert.equal(items.length, 2);
});

test('推演为空（或纯空白）时不产生 reasoning 条目 —— 界面不造假', () => {
  const { items } = toChainModel([TOOL_STEP], '   ');
  assert.equal(items.some((item) => item.kind === 'reasoning'), false);
});

test('run_retry / tool_error / failed → 运行级条目，图标区分', () => {
  const { items } = toChainModel([
    { type: 'run_retry', attempt: 2, reason: '上一轮模型调用没有取得工具结果' },
    { type: 'tool_error', tool: 'search_papers', message: 'KGUnavailable' },
    { type: 'failed', message: 'boom' },
  ]);
  assert.deepEqual(items.map((item) => item.icon), ['retry', 'error', 'error']);
  assert.match(items[0].label, /第 2 轮/);
  assert.match(items[1].label, /search_papers 失败/);
  assert.match(items[2].text, /boom/);
});

test('条目顺序 = 推演/运行级在前、工具集中在后；done/answer 不产生条目', () => {
  const { items } = toChainModel([
    { type: 'run_started', runId: 'r1' },
    { type: 'run_retry', attempt: 2, reason: 'x' },
    TOOL_STEP,
    { type: 'answer_delta', delta: '结论' },
    { type: 'answer', text: '结论', citation: {} },
    { type: 'done', status: 'ok' },
  ]);
  assert.deepEqual(items.map((item) => item.kind), ['retry', 'tool']);
  assert.equal(items.length, 2);
});

test('evidenceCount 跨事件去重计数（同一 id 多次出现只算一次）', () => {
  const scopeEvent = {
    type: 'tool_step', tool: 'report_graph_scope', label: '查询图谱规模',
    args: {}, summary: { status: 'ready', scope: { bibliographyTitles: 20000, candidateAssertions: 21497 } },
    evidenceIds: ['a'],
  };
  const { items, evidenceCount } = toChainModel([scopeEvent, TOOL_STEP, TOOL_STEP]);
  assert.equal(evidenceCount, 6);
  assert.equal(items.filter((item) => item.kind === 'tool').length, 3);
});

test('事件流为空 / 含垃圾元素时不抛错', () => {
  assert.deepEqual(toChainModel([], '').items, []);
  assert.deepEqual(toChainModel([null, 'x', 42], '').items, []);
});
