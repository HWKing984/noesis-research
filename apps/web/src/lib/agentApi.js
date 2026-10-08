/**
 * Agent 服务客户端（`services/research-agent` 的 HTTP + SSE 面）。
 *
 * 走同源代理：Vite 把 `/agent` 转发到 agent 服务（见 vite.config.js），所以同样不需要 CORS。
 *
 * 流程：`POST /agent/runs` 拿 runId → `EventSource` 打开 `/agent/runs/{id}/events` 看它干活。
 * 用 SSE 而不是"等一个最终结果"，是因为 agent 的价值一半在过程：调了哪个工具、
 * 命中多少条真实记录、回答到底引用了没有。
 */

export const DEFAULT_AGENT_BASE = '/agent';

export class AgentError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = 'AgentError';
    this.status = status;
    this.code = code;
  }
}

async function request(base, path, options = {}) {
  let response;
  try {
    response = await fetch(`${base}${path}`, {
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      ...options,
    });
  } catch (cause) {
    throw new AgentError(0, 'network_error', `连不上 Agent 服务：${cause.message}`);
  }
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new AgentError(
      response.status,
      payload?.error?.code || `http_${response.status}`,
      payload?.error?.message || `HTTP ${response.status}`,
    );
  }
  return payload;
}

export function createAgentApi(base = DEFAULT_AGENT_BASE) {
  return {
    base,
    health: () => request(base, '/health'),
    startRun: (question) =>
      request(base, '/runs', { method: 'POST', body: JSON.stringify({ question }) }),
    getRun: (runId) => request(base, `/runs/${encodeURIComponent(runId)}`),
    eventsUrl: (runId) => `${base}/runs/${encodeURIComponent(runId)}/events`,
  };
}

/** 把 AgentError 翻成不掩盖失败的文案。 */
export function describeAgentError(error) {
  if (!(error instanceof AgentError)) {
    return { title: '未知错误', detail: String(error?.message || error), kind: 'unknown' };
  }
  switch (error.code) {
    case 'llm_not_configured':
      return {
        title: 'Agent 还没配置模型',
        detail: `${error.message}（设置 LLM_API_KEY 与 LLM_MODEL 后重启 agent 服务）`,
        kind: 'unconfigured',
      };
    case 'kg_unavailable':
      return { title: '知识图谱不可用', detail: '图谱未就绪（503）。系统没有回退到离线数据。', kind: 'unavailable' };
    case 'kg_graph_version_mismatch':
      return { title: '图谱版本不一致', detail: '为避免引用错版本，本次请求被拒绝。', kind: 'unavailable' };
    case 'network_error':
      return { title: '连不上 Agent 服务', detail: error.message, kind: 'offline' };
    default:
      return { title: '请求失败', detail: `${error.code}：${error.message}`, kind: 'unknown' };
  }
}

/** 把事件流里的一条事件压成界面上一行可读的步骤。 */
export function describeStep(event) {
  switch (event?.type) {
    case 'tool_call': {
      const args = Object.entries(event.args || {})
        .map(([key, value]) => `${key}=${value}`)
        .join(' ');
      return { icon: 'call', label: `调用 ${event.tool}`, detail: args || '（无参数）' };
    }
    case 'tool_result': {
      const summary = event.summary || {};
      const bits = [];
      if (summary.papers != null) bits.push(`${summary.papers} 篇论文`);
      if (summary.assertions != null) bits.push(`${summary.assertions} 条候选断言`);
      if (summary.nodes != null) bits.push(`${summary.nodes} 个节点`);
      if (summary.edges != null) bits.push(`${summary.edges} 条关系`);
      if (summary.mode) bits.push(`视图 ${summary.mode}`);
      const count = (event.evidenceIds || []).length;
      return {
        icon: 'result',
        label: `${event.tool} 返回`,
        detail: `${bits.length ? bits.join(' · ') : '已返回'}｜可用证据 ${count} 条`,
        evidenceIds: event.evidenceIds || [],
      };
    }
    case 'tool_error':
      return { icon: 'error', label: `${event.tool} 失败`, detail: event.message };
    case 'failed':
      return { icon: 'error', label: '运行失败', detail: event.message };
    case 'done':
      return { icon: 'done', label: '结束', detail: event.status };
    default:
      return null;
  }
}
