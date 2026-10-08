/**
 * Agent 客户端纯函数单测（node 内置 runner）。
 *
 *     node --test apps/web/src/lib/agentApi.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { AgentError, describeAgentError, describeStep } from './agentApi.js';

test('tool_step 步骤用中文动作名 + 参数 + 结果规模合成一行', () => {
  const step = describeStep({
    type: 'tool_step',
    tool: 'search_papers',
    label: '检索论文',
    args: { query: 'transformer', limit: 5 },
    summary: { papers: 10, applied: { q: 'transformer' } },
    evidenceIds: ['a', 'b', 'c'],
  });
  assert.equal(step.icon, 'tool');
  assert.equal(step.label, '检索论文', '用户看到的是中文动作名，不是函数名');
  assert.match(step.detail, /query=transformer/);
  assert.match(step.detail, /命中 10 篇/);
  assert.match(step.detail, /可用证据 3 条/);
  assert.deepEqual(step.evidenceIds, ['a', 'b', 'c']);
});

test('tool_step 没参数也不显示 undefined', () => {
  const step = describeStep({ type: 'tool_step', tool: 'report_graph_scope', label: '查询图谱规模', args: {}, summary: { status: 'ready' } });
  assert.match(step.detail, /已返回/);
  assert.doesNotMatch(step.detail, /undefined/);
});

test('tool_step 对图谱规模结果报真实计数', () => {
  const step = describeStep({
    type: 'tool_step',
    tool: 'report_graph_scope',
    label: '查询图谱规模',
    args: {},
    summary: { status: 'ready', scope: { bibliographyTitles: 20000, candidateAssertions: 21497 } },
    evidenceIds: [],
  });
  assert.match(step.detail, /书目 20000/);
  assert.match(step.detail, /候选断言 21497/);
});

test('tool_step 对论文详情结果带出题名', () => {
  const step = describeStep({
    type: 'tool_step',
    tool: 'get_paper',
    label: '查看论文详情',
    args: { publication_id: 'conf/x/1' },
    summary: { publicationId: 'conf/x/1', title: 'ShrimpFormer-X' },
    evidenceIds: [],
  });
  assert.match(step.detail, /《ShrimpFormer-X》/);
});

test('tool_error 与 failed 都归到 error 图标，不会被当成正常步骤', () => {
  assert.equal(describeStep({ type: 'tool_error', tool: 'search_papers', message: 'KGUnavailable' }).icon, 'error');
  assert.equal(describeStep({ type: 'failed', message: 'boom' }).icon, 'error');
  assert.match(describeStep({ type: 'failed', message: 'boom' }).detail, /boom/);
});

test('run_retry 事件渲染成可见的重试步骤', () => {
  const step = describeStep({ type: 'run_retry', attempt: 2, reason: '上一轮模型调用没有取得工具结果，自动重试一次' });
  assert.equal(step.icon, 'retry');
  assert.match(step.label, /第 2 轮/);
  assert.match(step.detail, /没有取得工具结果/);
});

test('无关事件不产生步骤行', () => {
  assert.equal(describeStep({ type: 'heartbeat' }), null);
  assert.equal(describeStep(null), null);
});

test('未配置模型时给出可操作的提示，而不是含糊报错', () => {
  const described = describeAgentError(new AgentError(503, 'llm_not_configured', 'Agent 未配置模型：LLM_API_KEY'));
  assert.equal(described.kind, 'unconfigured');
  assert.match(described.title, /没配置模型|未配置/);
  assert.match(described.detail, /LLM_API_KEY/);
});

test('图谱不可用与「没有结果」在文案上是两件事', () => {
  assert.equal(describeAgentError(new AgentError(503, 'kg_unavailable', 'x')).kind, 'unavailable');
  assert.equal(describeAgentError(new AgentError(404, 'not_found', 'x')).kind, 'unknown');
});

test('非 AgentError 的异常也能翻成人话', () => {
  const described = describeAgentError(new Error('boom'));
  assert.equal(described.kind, 'unknown');
  assert.match(described.detail, /boom/);
});
