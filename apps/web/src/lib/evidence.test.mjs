/**
 * 证据规则的单元测试（node 内置 test runner，无需额外依赖）。
 *
 *     node --test apps/web/src/lib/
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  EVIDENCE_STATES,
  assertionIsCandidate,
  citationReport,
  citableEvidence,
  claimSentences,
  countCandidates,
  describeEvidence,
  evidenceState,
  isCitableEvidence,
} from './evidence.js';

const bibRef = {
  sourceType: 'kg_bibliography',
  sourceId: 'conf/IEEEwisa/LinGHW25',
  publicationId: 'conf/IEEEwisa/LinGHW25',
  graphId: 'ai-literature-ed16399925fac2a599ed',
  evidenceLevel: 'title',
  assertionStatus: 'none',
  verificationStatus: 'unverified',
};

const assertionRef = {
  sourceType: 'kg_assertion',
  sourceId: 'ai-literature:Assertion:27d1a77d',
  publicationId: 'conf/IEEEwisa/LinGHW25',
  graphId: 'ai-literature-ed16399925fac2a599ed',
  evidenceLevel: 'title',
  assertionStatus: 'candidate',
  verificationStatus: 'unverified',
};

test('只有带非空 sourceId 的引用才算可引用', () => {
  assert.equal(isCitableEvidence(bibRef), true);
  assert.equal(isCitableEvidence({ sourceId: '   ' }), false);
  assert.equal(isCitableEvidence({ sourceId: null }), false);
  assert.equal(isCitableEvidence(null), false);
  assert.equal(citableEvidence([bibRef, { sourceId: '' }, null]).length, 1);
});

test('三段式闸门：有证据=covered，需要却没证据=missing，不需要=not_required', () => {
  assert.equal(evidenceState([bibRef]), EVIDENCE_STATES.COVERED);
  assert.equal(evidenceState([], { required: true }), EVIDENCE_STATES.MISSING);
  assert.equal(evidenceState([], { required: false }), EVIDENCE_STATES.NOT_REQUIRED);
  assert.equal(evidenceState([]), EVIDENCE_STATES.NOT_REQUIRED);
  // 无效引用不能把状态"凑成" covered
  assert.equal(evidenceState([{ sourceId: '  ' }], { required: true }), EVIDENCE_STATES.MISSING);
});

test('按句切分会丢掉过短片段', () => {
  assert.deepEqual(claimSentences('结论先行：图谱里有两篇相关论文。\n###\nA'), [
    '结论先行：图谱里有两篇相关论文',
  ]);
  assert.deepEqual(claimSentences(''), []);
  assert.deepEqual(claimSentences('短。'), []);
});

test('引用可溯率统计的是回答里出现的 id，不是工具结果里的 id', () => {
  const available = ['conf/aaai/A25', 'conf/cvpr/B25'];
  const report = citationReport(
    '结论先行：图谱中有两篇相关论文。\n依据一：conf/aaai/A25 的题名出现关键词。\n依据二：conf/cvpr/B25 同样如此。\n局限：题名级证据不能证明具体结论。',
    available,
  );
  assert.equal(report.available, 2);
  assert.equal(report.cited, 2);
  assert.equal(report.consideredSentences, 4);
  assert.equal(report.attributedSentences, 2);
  assert.equal(report.citationRate, 0.5);
  assert.equal(report.passes, true);
});

test('一个 id 都没引用的流畅回答必须判失败', () => {
  const report = citationReport(
    '图谱里有不少关于 transformer 的论文，其中若干篇来自 CVPR 2025，涵盖了生成与检测任务。',
    ['conf/aaai/A25'],
  );
  assert.equal(report.cited, 0);
  assert.deepEqual(report.citedIds, []);
  assert.equal(report.citationRate, 0);
  assert.equal(report.passes, false);
});

test('空回答不会崩，也不给"通过"', () => {
  const report = citationReport('', ['conf/aaai/A25']);
  assert.equal(report.consideredSentences, 0);
  assert.equal(report.citationRate, 0);
  assert.equal(report.passes, false);
});

test('证据描述把三个维度分开说，并对题名级给出限制说明', () => {
  const described = describeEvidence(bibRef);
  assert.equal(described.citable, true);
  assert.equal(described.sourceId, 'conf/IEEEwisa/LinGHW25');
  assert.equal(described.label, '书目记录');
  assert.equal(described.levelLabel, '仅题名');
  assert.equal(described.verificationLabel, '未核验');
  assert.match(described.caveat, /不能证明/);
});

test('候选断言在 UI 上恒为「候选」', () => {
  const described = describeEvidence(assertionRef);
  assert.equal(described.label, '候选断言');
  assert.equal(described.assertionLabel, '候选');
  assert.equal(assertionIsCandidate({ status: 'candidate' }), true);
  assert.equal(assertionIsCandidate({ status: 'verified' }), false);
  assert.equal(countCandidates([{ status: 'candidate' }, { status: 'verified' }, {}]), 1);
});

test('缺失来源的描述不伪装成有来源', () => {
  const described = describeEvidence({ sourceId: '' });
  assert.equal(described.citable, false);
  assert.equal(described.sourceId, '');
  assert.match(described.caveat, /没有可引用的来源/);
});
