/**
 * 证据展示规则 —— 全部是纯函数，可用 `node --test` 直接跑。
 *
 * ## 移植说明（评审要求「优先原组件移植」）
 *
 * 三段式证据闸门（`covered` / `missing` / `not_required`）这个**形态**移植自 NOESIS：
 * `frontend/src/components/agentEvidence.helpers.js::evidenceState`。
 * 它的数据形状（`write_id` / `observations` / `inputs`）是 NOESIS 学习域的，
 * 与本项目的 `EvidenceRef`（`sourceType` / `sourceId` / `evidenceLevel` /
 * `verificationStatus`）不同，因此**按本项目契约重写**，只保留形态与用语，
 * 目的就是让两边 UI 说同一套话。
 *
 * ## 三条不许含糊的显示规则
 *
 * 1. 候选关系必须显示成「候选」，不得改写成肯定语气；
 * 2. 证据深度是独立维度 —— `title` 只能证明论文存在，不能证明论文做了某事；
 * 3. 核验状态是四级阶梯，`unverified` 不能说成"已核"。
 */

//: 证据深度 → 中文标签（与后端 `EVIDENCE_LEVELS` 一一对应）
export const EVIDENCE_LEVEL_LABELS = {
  title: '仅题名',
  abstract: '摘要级',
  fulltext: '全文级',
};

//: 核验阶梯 → 中文标签（与后端 `VERIFICATION_STAGES` 一一对应）
export const VERIFICATION_LABELS = {
  unverified: '未核验',
  id_valid: 'id 可解析',
  evidence_supports: '引文支持',
  semantic_verified: '语义已核',
};

//: 候选断言状态 → 中文标签
export const ASSERTION_STATUS_LABELS = {
  candidate: '候选',
  verified: '已核',
  none: '',
};

//: 来源类型 → 中文标签
export const SOURCE_TYPE_LABELS = {
  kg_bibliography: '书目记录',
  kg_assertion: '候选断言',
  paper_passage: '论文正文',
  external_record: '外部数据源',
};

export const EVIDENCE_STATES = {
  COVERED: 'covered',
  MISSING: 'missing',
  NOT_REQUIRED: 'not_required',
};

//: 一个「短到不构成断言」的句子下限，与 CLI（run.py）保持同一规则。
export const MIN_CLAIM_CHARS = 8;

/** 有非空 sourceId 的证据引用才算可引用。 */
export function isCitableEvidence(ref) {
  return Boolean(ref && typeof ref.sourceId === 'string' && ref.sourceId.trim() !== '');
}

/** 过滤出可引用的证据引用。 */
export function citableEvidence(refs) {
  return (Array.isArray(refs) ? refs : []).filter(isCitableEvidence);
}

/**
 * 三段式证据闸门。
 *
 * @param {Array} refs 该处用到的证据引用
 * @param {{required?: boolean}} options 该处是否**需要**证据（例如事实性回答需要，纯提示不需要）
 * @returns {'covered'|'missing'|'not_required'}
 */
export function evidenceState(refs, options = {}) {
  if (citableEvidence(refs).length > 0) return EVIDENCE_STATES.COVERED;
  return options.required ? EVIDENCE_STATES.MISSING : EVIDENCE_STATES.NOT_REQUIRED;
}

/** 按句切分，忽略过短的片段（标题、列表残片不构成断言）。 */
export function claimSentences(answer) {
  return String(answer || '')
    .split(/[。！？!?\n]+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length >= MIN_CLAIM_CHARS);
}

/**
 * 引用可溯率。
 *
 * **与 `services/research-agent/run.py::citation_report` 同一条规则**：
 * 统计的是"回答里实际出现了哪些 id"，不是"工具结果里有多少 id"。
 * 后者证明不了任何东西 —— 证据可用 ≠ 回答可溯。
 */
export function citationReport(answer, availableIds) {
  const text = String(answer || '');
  const ids = (Array.isArray(availableIds) ? availableIds : []).filter(
    (id) => typeof id === 'string' && id.trim() !== '',
  );
  const citedIds = ids.filter((id) => text.includes(id));
  const sentences = claimSentences(text);
  const attributed = sentences.filter((sentence) => ids.some((id) => sentence.includes(id)));
  return {
    available: ids.length,
    cited: citedIds.length,
    citedIds,
    consideredSentences: sentences.length,
    attributedSentences: attributed.length,
    citationRate: sentences.length === 0 ? 0 : attributed.length / sentences.length,
    passes: citedIds.length > 0,
  };
}

/** 把一条 EvidenceRef 压成 UI 上要显示的信息，附带它的限制说明。 */
export function describeEvidence(ref) {
  if (!isCitableEvidence(ref)) {
    return { citable: false, sourceId: '', label: '无来源', levelLabel: '', verificationLabel: '', caveat: '该处没有可引用的来源。' };
  }
  const level = String(ref.evidenceLevel || '');
  const verification = String(ref.verificationStatus || 'unverified');
  const caveat =
    level === 'title'
      ? '题名级证据只能证明这篇论文存在、题名里出现了相关词，不能证明论文真的做了这句话声称的事。'
      : level === 'abstract'
        ? '摘要级证据来自摘要原文；全文结论仍需阅读原文。'
        : '全文级证据附有段落定位，可直接核对。';
  return {
    citable: true,
    sourceId: String(ref.sourceId),
    label: SOURCE_TYPE_LABELS[ref.sourceType] || String(ref.sourceType || '来源'),
    levelLabel: EVIDENCE_LEVEL_LABELS[level] || level || '未知深度',
    verificationLabel: VERIFICATION_LABELS[verification] || verification || '未核验',
    assertionLabel: ASSERTION_STATUS_LABELS[String(ref.assertionStatus || 'none')] || '',
    caveat,
    publicationId: ref.publicationId || null,
    graphId: ref.graphId || null,
  };
}

/** 候选断言是否仍应显示为「候选」。图谱里没有别的状态。 */
export function assertionIsCandidate(assertion) {
  return String(assertion?.status || '') === 'candidate';
}

/** 一组断言里有多少条是候选 —— 用于在标题上直接标出"候选 N 条"。 */
export function countCandidates(assertions) {
  return (Array.isArray(assertions) ? assertions : []).filter(assertionIsCandidate).length;
}
