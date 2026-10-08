/**
 * 研究 API 客户端。
 *
 * 与后端同一条铁律：**失败不许变成空结果**。503（图谱不可用）与真实的空结果
 * （`data: []`）必须在上层是可区分的两种状态 —— 所以这里一律抛 {@link ApiError}，
 * 绝不返回空数组冒充"没搜到"。
 *
 * 后端：apps/api（`GET /api/papers/search`、`/api/papers/{id}`、`/api/graph/neighbors`、`/api/health`）。
 */

export const CONFIGURED_API_BASE =
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE) || '';

/**
 * 解析 API 基址。
 *
 * 默认走**同源**：dev / preview 由 Vite 把 `/api` 代理到后端（见 vite.config.js），
 * 浏览器看到的是同源请求，因此不需要给后端开 CORS。部署时用 `VITE_API_BASE`
 * 指向真实后端地址即可。
 */
export function resolveApiBase(configured = CONFIGURED_API_BASE) {
  const raw = String(configured || '').trim();
  if (raw) return raw.replace(/\/+$/, '');
  if (typeof window !== 'undefined' && window.location && window.location.origin) {
    return window.location.origin;
  }
  return 'http://127.0.0.1:8100';
}

export const DEFAULT_API_BASE = resolveApiBase();

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** 把 publicationId（含斜杠的 DBLP 键）拼成请求路径，逐段转义但保留分隔斜杠。 */
export function publicationPath(publicationId) {
  const id = String(publicationId || '').trim();
  if (!id) throw new ApiError(400, 'invalid_request', '缺少 publicationId');
  const escaped = id.split('/').map(encodeURIComponent).join('/');
  return `/api/papers/${escaped}`;
}

async function request(base, path, params, options = {}) {
  const url = new URL(path, base);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== '' && value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  }

  let response;
  try {
    response = await fetch(url, {
      headers: { Accept: 'application/json' },
      ...options,
    });
  } catch (cause) {
    throw new ApiError(0, 'network_error', `无法连接研究 API（${base}）：${cause.message}`);
  }

  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const code = payload?.error?.code || `http_${response.status}`;
    const message = payload?.error?.message || `HTTP ${response.status}`;
    throw new ApiError(response.status, code, message);
  }
  if (!payload || typeof payload !== 'object') {
    throw new ApiError(502, 'bad_response', 'API 返回了非 JSON 响应');
  }
  return payload;
}

export function createResearchApi(base = DEFAULT_API_BASE) {
  return {
    base,
    health: (options) => request(base, '/api/health', undefined, options),
    searchPapers: (params = {}, options) => request(base, '/api/papers/search', params, options),
    getPaper: (publicationId, options) =>
      request(base, publicationPath(publicationId), undefined, options),
    graphNeighbors: (publicationId, mode = 'paper', limit = 15, options = {}) =>
      request(base, '/api/graph/neighbors', { id: publicationId, mode, limit }, options),
  };
}

/**
 * 把 ApiError 翻译成用户看得懂、且**不掩盖失败**的文案。
 * `kg_unavailable` 与"没有命中"是完全不同的两件事，文案上必须分开。
 */
export function describeApiError(error) {
  if (!(error instanceof ApiError)) {
    if (error && (error.name === 'AbortError' || error.code === 20)) {
      return { title: '已取消', detail: '这次请求已被更新的操作取代。', kind: 'cancelled' };
    }
    return { title: '未知错误', detail: String(error?.message || error), kind: 'unknown' };
  }
  switch (error.code) {
    case 'kg_unavailable':
      return { title: '知识图谱不可用', detail: '图谱服务或 Neo4j 未就绪（503）。系统没有回退到离线数据。', kind: 'unavailable' };
    case 'kg_graph_version_mismatch':
      return { title: '图谱版本不一致', detail: '服务返回的图谱版本与锁定版本不符，为避免引用错版本，本次请求被拒绝。', kind: 'unavailable' };
    case 'kg_bad_response':
      return { title: '图谱响应结构异常', detail: '上游返回了不符合契约的数据（502）。这不会被当成"没有搜到"。', kind: 'unavailable' };
    case 'invalid_request':
      return { title: '请求参数不合法', detail: error.message, kind: 'invalid' };
    case 'not_found':
      return { title: '没有这条记录', detail: error.message, kind: 'not_found' };
    case 'network_error':
      return { title: '连不上研究 API', detail: error.message, kind: 'offline' };
    default:
      return { title: '请求失败', detail: `${error.code}：${error.message}`, kind: 'unknown' };
  }
}
