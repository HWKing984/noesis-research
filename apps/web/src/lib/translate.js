/**
 * 点击翻译的纯逻辑。后端：`POST /api/translate`（apps/api/noesis_research_api/translate.py）。
 *
 * 与全仓同一条铁律在这里的形态：**失败不许变成原文**。后端已经保证不会把
 * 原文当译文返回（无中文 / 复读输入一律 502），这一层再做一次独立校验 ——
 * 就算上游契约哪天松了，前端也绝不会把英文标题冒充成中文译名画出来。
 *
 * 译文不是证据：它不产生 EvidenceRef、不进引用核查；这些由 TranslatePop 的
 * UI 文案声明，这里只管数据形状。
 */

/** 后端与前端共用的"是不是中文"判定（U+4E00–U+9FFF）。 */
const ZH_CHAR = /[\u4e00-\u9fff]/;

/** 与后端 `translate()` 相同的空白折叠，保证缓存/比对口径一致。 */
export function normalizeTrText(text) {
  return String(text ?? '').replace(/\s+/g, ' ').trim();
}

/**
 * 校验并规整翻译响应。结构不符 / 无中文 / 与原文相同 → 抛错（调用方显示失败态）。
 * @returns {{ zh: string, kind: string, cached: boolean, keptTerms: string[], model: string|null, targetLang: string }}
 */
export function parseTranslateResponse(payload, { originalText = '' } = {}) {
  if (!payload || typeof payload !== 'object') {
    throw new Error('翻译响应不是对象');
  }
  const zh = String(payload.zh ?? '').trim();
  if (!zh) throw new Error('翻译响应缺少译文');
  if (!ZH_CHAR.test(zh)) throw new Error('翻译响应不含中文（疑似原文复读）');
  const original = normalizeTrText(originalText);
  if (original && zh === original) throw new Error('译文与原文相同（疑似复读）');

  const keptTerms = Array.isArray(payload.keptTerms)
    ? payload.keptTerms.filter((term) => typeof term === 'string' && term.trim() !== '')
    : [];
  return {
    zh,
    kind: String(payload.kind || 'text'),
    targetLang: String(payload.targetLang || 'zh-Hans'),
    cached: Boolean(payload.cached),
    keptTerms,
    model: payload.model ? String(payload.model) : null,
  };
}

/**
 * 翻译失败的文案 —— 三种失败必须可区分，且都不掩盖失败。
 * @param {{ code?: string, message?: string }} error ApiError 形状
 */
export function describeTranslateError(error) {
  switch (error?.code) {
    case 'llm_not_configured':
      return { title: '翻译服务未配置', detail: '服务端缺少 LLM_API_KEY / LLM_MODEL（503）。' };
    case 'translate_unavailable':
      return { title: '翻译服务不可用', detail: '上游模型未响应（503）。原文不会被当成译文显示。' };
    case 'translate_bad_response':
      return { title: '翻译结果不可信', detail: '上游没有返回可用的中文译文（502）。' };
    case 'network_error':
      return { title: '连不上研究 API', detail: String(error?.message || '') };
    default:
      return { title: '翻译失败', detail: `${error?.code || ''}${error?.code ? '：' : ''}${error?.message || ''}` };
  }
}

/** "术语处理"小节的展示条目：保护词保留原文，其余照常。 */
export function glossLabel(keptTerms) {
  const list = Array.isArray(keptTerms) ? keptTerms : [];
  return list.length > 0 ? `保留原文：${list.join('、')}` : '';
}

/**
 * 校验并规整解释响应（POST /api/explain）。结构不符 / 无中文 → 抛错。
 * 解释与译文同一条边界：**AI 解释不是证据**——不产生 EvidenceRef、不进引用核查。
 * @returns {{ text: string, kind: string, style: string, category: string, brief: string,
 *   detail: string, whyItMatters: string, example: string, cached: boolean, model: string|null }}
 */
export function parseExplainResponse(payload) {
  if (!payload || typeof payload !== 'object') {
    throw new Error('解释响应不是对象');
  }
  const str = (key) => String(payload[key] ?? '').trim();
  const brief = str('brief');
  const detail = str('detail');
  const whyItMatters = str('whyItMatters');
  const example = str('example');
  if (!brief || !detail || !whyItMatters || !example) {
    throw new Error('解释响应缺少必要字段');
  }
  if (!ZH_CHAR.test(brief) || !ZH_CHAR.test(detail)) {
    throw new Error('解释不含中文（疑似复读或跑偏）');
  }
  return {
    text: str('text'),
    kind: String(payload.kind || 'term'),
    style: String(payload.style || 'normal'),
    category: str('category') || '其他',
    brief,
    detail,
    whyItMatters,
    example,
    cached: Boolean(payload.cached),
    model: payload.model ? String(payload.model) : null,
  };
}

/**
 * 解释失败的文案 —— 与翻译同样的三种失败可区分、不掩盖失败。
 * @param {{ code?: string, message?: string }} error ApiError 形状
 */
export function describeExplainError(error) {
  switch (error?.code) {
    case 'llm_not_configured':
      return { title: '解释服务未配置', detail: '服务端缺少 LLM_API_KEY / LLM_MODEL（503）。' };
    case 'translate_unavailable':
      return { title: '解释服务不可用', detail: '上游模型未响应（503）。不会编一段解释来冒充。' };
    case 'explain_bad_response':
      return { title: '解释结果不可信', detail: '上游没有按约定结构返回可用的解释（502）。' };
    case 'network_error':
      return { title: '连不上研究 API', detail: String(error?.message || '') };
    default:
      return { title: '解释失败', detail: `${error?.code || ''}${error?.code ? '：' : ''}${error?.message || ''}` };
  }
}
