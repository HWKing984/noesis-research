/**
 * Agent 客户端纯函数单测（node 内置 runner）。
 *
 *     node --test apps/web/src/lib/agentApi.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { AgentError, describeAgentError, describeStep } from './agentApi.js';

test('tool_call 步骤把实参摊平成一行', () => {
  const step = describeStep({ type: 'tool_call', tool: 'search_papers', args: { query: 'transformer', limit: 5 } });
  assert.equal(step.icon, 'call');
  assert.match(step.label, /search_papers/);
  assert.equal(step.detail, 'query=transformer limit=5');
});

test('tool_call 没参数也不显示 undefined', () => {
  assert.equal(describeStep({ type: 'tool_call', tool: 'report_graph_scope', args: {} }).detail, '（无参数）');
});

test('tool_result 步骤只报规模，且带上可用证据条数', () => {
  const step = describeStep({
    type: 'tool_result',
    tool: 'search_papers',
    summary: { papers: 10, applied: { q: 'transformer' } },
    evidenceIds: ['a', 'b', 'c'],
  });
  assert.equal(step.icon, 'result');
  assert.match(step.detail, /10 篇论文/);
  assert.match(step.detail, /可用证据 3 条/);
  assert.deepEqual(step.evidenceIds, ['a', 'b', 'c']);
});

test('tool_result 对图谱类结果报节点与关系数', () => {
  const step = describeStep({ type: 'tool_result', tool: 'explore_graph', summary: { nodes: 14, edges: 17, mode: 'paper' }, evidenceIds: [] });
  assert.match(step.detail, /14 个节点/);
  assert.match(step.detail, /17 条关系/);
  assert.match(step.detail, /视图 paper/);
});

test('tool_error 与 failed 都归到 error 图标，不会被当成正常步骤', () => {
  assert.equal(describeStep({ type: 'tool_error', tool: 'search_papers', message: 'KGUnavailable' }).icon, 'error');
  assert.equal(describeStep({ type: 'failed', message: 'boom' }).icon, 'error');
  assert.match(describeStep({ type: 'failed', message: 'boom' }).detail, /boom/);
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
