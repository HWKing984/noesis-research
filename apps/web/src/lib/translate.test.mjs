/**
 * 点击翻译的纯逻辑单测（node 内置 runner）。
 *
 *     node --test apps/web/src/lib/translate.test.mjs
 *
 * 重点守一条：**原文冒充译文在任何一层都不可能被画出来** —— 后端拦一次，
 * parseTranslateResponse 再拦一次。
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  describeExplainError,
  describeTranslateError,
  glossLabel,
  normalizeTrText,
  parseExplainResponse,
  parseTranslateResponse,
} from './translate.js';

const OK = {
  zh: '用于图像识别的深度残差学习',
  kind: 'title',
  targetLang: 'zh-Hans',
  cached: false,
  keptTerms: ['ResNet'],
  model: 'qwen3:8b',
};

test('parseTranslateResponse：合法响应原样通过', () => {
  const parsed = parseTranslateResponse({ ...OK }, { originalText: 'Deep Residual Learning' });
  assert.equal(parsed.zh, OK.zh);
  assert.deepEqual(parsed.keptTerms, ['ResNet']);
  assert.equal(parsed.cached, false);
  assert.equal(parsed.model, 'qwen3:8b');
});

test('parseTranslateResponse：无中文的“译文”必须被拒', () => {
  assert.throws(() => parseTranslateResponse({ ...OK, zh: 'Deep Residual Learning' }), /不含中文/);
  assert.throws(() => parseTranslateResponse({ ...OK, zh: '12345 - 6789' }), /不含中文/);
});

test('parseTranslateResponse：与原文相同（空白归一后）必须被拒', () => {
  assert.throws(
    () => parseTranslateResponse({ ...OK, zh: '这是 一个 中文输入' }, { originalText: '这是 一个   中文输入' }),
    /与原文相同/,
  );
});

test('parseTranslateResponse：空译文 / 非对象都算失败', () => {
  assert.throws(() => parseTranslateResponse(null), /不是对象/);
  assert.throws(() => parseTranslateResponse({ zh: '  ' }), /缺少译文/);
});

test('parseTranslateResponse：keptTerms 里的非字符串被过滤，不炸', () => {
  const parsed = parseTranslateResponse({ ...OK, keptTerms: ['ResNet', 42, null, 'ImageNet'] });
  assert.deepEqual(parsed.keptTerms, ['ResNet', 'ImageNet']);
});

test('normalizeTrText 与后端口径一致（含换行折叠）', () => {
  assert.equal(normalizeTrText('  a\n\n  b  '), 'a b');
  assert.equal(normalizeTrText(undefined), '');
});

test('describeTranslateError：三种失败各自可辨，不互相冒充', () => {
  const cases = {
    llm_not_configured: /未配置/,
    translate_unavailable: /不可用/,
    translate_bad_response: /不可信/,
  };
  for (const [code, pattern] of Object.entries(cases)) {
    assert.match(describeTranslateError({ code }).title, pattern, code);
    assert.match(describeTranslateError({ code }).detail, /503|502/, code);
  }
  assert.match(describeTranslateError({ code: 'whatever', message: 'x' }).title, /翻译失败/);
});

test('glossLabel：有保护词显示它们，没有就返回空串（不显示空节）', () => {
  assert.equal(glossLabel(['ResNet', 'ImageNet']), '保留原文：ResNet、ImageNet');
  assert.equal(glossLabel([]), '');
  assert.equal(glossLabel(undefined), '');
});

// ---- 解释（POST /api/explain）------------------------------------------------

const OK_EXPLAIN = {
  text: 'self-attention',
  kind: 'term',
  style: 'normal',
  category: '概念',
  brief: '让序列中每个位置直接关注所有其他位置的机制。',
  detail: '每个位置按注意力权重加权聚合全体位置的表示。\n它摆脱了循环结构，可完全并行。',
  whyItMatters: '它是 Transformer 的核心构件。',
  example: '例如“it”可同时对照句中多个名词确定指代。',
  cached: false,
  model: 'm',
};

test('parseExplainResponse：合法响应原样通过', () => {
  const parsed = parseExplainResponse({ ...OK_EXPLAIN });
  assert.equal(parsed.category, '概念');
  assert.equal(parsed.whyItMatters, OK_EXPLAIN.whyItMatters);
  assert.equal(parsed.model, 'm');
  assert.equal(parsed.cached, false);
});

test('parseExplainResponse：缺任一必需字段都算失败', () => {
  for (const key of ['brief', 'detail', 'whyItMatters', 'example']) {
    const broken = { ...OK_EXPLAIN };
    delete broken[key];
    assert.throws(() => parseExplainResponse(broken), /缺少必要字段/, key);
  }
});

test('parseExplainResponse：人类可读面无中文必须被拒', () => {
  assert.throws(() => parseExplainResponse({ ...OK_EXPLAIN, brief: 'A mechanism of attention.' }), /不含中文/);
  assert.throws(() => parseExplainResponse({ ...OK_EXPLAIN, detail: 'positional encoding only' }), /不含中文/);
});

test('parseExplainResponse：空 category 兜底为「其他」，不炸', () => {
  const parsed = parseExplainResponse({ ...OK_EXPLAIN, category: '' });
  assert.equal(parsed.category, '其他');
});

test('describeExplainError：三种失败各自可辨，不互相冒充', () => {
  const cases = {
    llm_not_configured: /未配置/,
    translate_unavailable: /不可用/,
    explain_bad_response: /不可信/,
  };
  for (const [code, pattern] of Object.entries(cases)) {
    assert.match(describeExplainError({ code }).title, pattern, code);
    assert.match(describeExplainError({ code }).detail, /503|502/, code);
  }
  assert.match(describeExplainError({ code: 'whatever', message: 'x' }).title, /解释失败/);
});
