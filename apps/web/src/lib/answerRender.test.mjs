/**
 * 回答渲染规则的单元测试（node 内置 runner）。
 *
 *     node --test apps/web/src/lib/answerRender.test.mjs
 *
 * node:test 没有 JSX —— 这里用 React.createElement 的返回对象做结构断言。
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { findCitedIds, renderAnswer } from './answerRender.jsx';

const ids = ['conf/aaai/A25', 'conf/cvpr/B25'];

function textOf(node) {
  if (node == null || node === false) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (node.props && node.props.children !== undefined) return textOf(node.props.children);
  return '';
}

test('findCitedIds 只认回答里字面出现的 id', () => {
  const answer = '依据一：conf/aaai/A25 的题名出现关键词；另一篇没提。';
  assert.deepEqual(findCitedIds(answer, [...ids, 'conf/x/C25']), ['conf/aaai/A25']);
  assert.deepEqual(findCitedIds('', ids), []);
});

test('id 被替换成带编号的可点上标，其余文本原样保留', () => {
  const blocks = renderAnswer(`结论先行。\n依据见 conf/aaai/A25 与 conf/cvpr/B25。`, ids, () => {});
  const flat = JSON.stringify(blocks);
  assert.match(flat, /citation-pill/);
  assert.match(flat, /conf\/aaai\/A25/);
  // 上标按钮必须带着 id 与回调触发能力
  const flatProps = JSON.stringify(blocks);
  assert.match(flatProps, /data-cited-id/);
});

test('上标编号按 citedIds 顺序，不按文本出现顺序', () => {
  const answer = '先讲 conf/cvpr/B25，再讲 conf/aaai/A25。';
  const flat = JSON.stringify(renderAnswer(answer, ids, () => {}));
  const first = flat.indexOf('"children":"1"');
  const second = flat.indexOf('"children":"2"');
  assert.ok(first >= 0 && second >= 0, `应有两个编号上标：${flat.slice(0, 400)}`);
  // B25 在文本里先出现，但它的编号是 2 → "2" 应当先于 "1" 出现
  assert.ok(second < first, '编号顺序应跟随 citedIds 而不是文本顺序');
});

test('markdown-lite：空行分段 / # 标题 / - 列表 / **加粗**', () => {
  const blocks = renderAnswer(
    ['## 小标题', '', '第一段，**重点**内容。', '', '- 甲 conf/aaai/A25', '- 乙', '', '结尾。'].join('\n'),
    ids,
    () => {},
  );
  const kinds = blocks.map((b) => b.type);
  assert.deepEqual(kinds, ['h4', 'p', 'ul', 'p']);
  const p1 = JSON.stringify(blocks[1]);
  assert.match(p1, /"type":"b"/, '加粗应渲染成 <b>');
  const ul = JSON.stringify(blocks[2]);
  assert.match(ul, /"type":"li"/);
  assert.equal(blocks.length, 4);
});

test('没有引用时纯文本分段，不产生任何 pill', () => {
  const flat = JSON.stringify(renderAnswer('第一段。\n\n第二段。', [], () => {}));
  assert.doesNotMatch(flat, /citation-pill/);
});

test('空回答渲染为空数组且不抛异常', () => {
  assert.deepEqual(renderAnswer('', ids, () => {}), []);
  assert.deepEqual(renderAnswer(null, ids, () => {}), []);
});

test('id 出现在列表项与加粗段内同样被替换', () => {
  const flat = JSON.stringify(renderAnswer('- 加粗 **conf/aaai/A25** 的条目', ids, () => {}));
  assert.match(flat, /citation-pill/);
});

test('渲染输出不含 HTML 字符串（无注入面）', () => {
  const flat = JSON.stringify(renderAnswer('<script>alert(1)</script>\n\n- <img src=x>', [], () => {}));
  assert.doesNotMatch(flat, /<script>/);
  assert.match(flat, /alert\(1\)/, '脚本内容只应作为纯文本出现');
});
