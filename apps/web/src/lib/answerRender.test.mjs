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
import { findCitedIds, renderAnswer } from './answerRender.js';

const ids = ['conf/aaai/A25', 'conf/cvpr/B25'];

function textOf(node) {
  if (node == null || node === false) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (node.props && node.props.children !== undefined) return textOf(node.props.children);
  return '';
}

/** 收集所有元素节点的 type（用来断言"没有生成某个元素"）。 */
function typesOf(node, out = []) {
  if (Array.isArray(node)) {
    node.forEach((item) => typesOf(item, out));
    return out;
  }
  if (node && node.props) {
    out.push(node.type);
    typesOf(node.props.children, out);
  }
  return out;
}

/** 按出现顺序收集引用上标的编号（pill 的 children 是数字）。 */
function pillNumbers(node, out = []) {
  if (Array.isArray(node)) {
    node.forEach((item) => pillNumbers(item, out));
    return out;
  }
  if (node && node.props) {
    if (node.props['data-testid'] === 'citation-pill') out.push(node.props.children);
    pillNumbers(node.props.children, out);
  }
  return out;
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
  const blocks = renderAnswer(answer, ids, () => {});
  // B25 在文本里先出现，但它在 ids 里排第二 → 编号应是 2
  assert.deepEqual(pillNumbers(blocks), [2, 1], '编号顺序应跟随 citedIds 而不是文本顺序');
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

test('渲染输出不含元素级 HTML 注入（脚本只作为纯文本出现）', () => {
  const blocks = renderAnswer('<script>alert(1)</script>\n\n- <img src=x>', [], () => {});
  const types = typesOf(blocks);
  assert.ok(!types.includes('script'), `不该生成 script 元素：${types.join(',')}`);
  assert.ok(!types.includes('img'), `不该生成 img 元素：${types.join(',')}`);
  assert.match(JSON.stringify(blocks), /alert\(1\)/, '脚本内容只应作为纯文本出现');
});

// ---------------------------------------------------------------------------
// 2026-10-10 新增：表格 / 有序列表 / 链接 / 可读引用标签
// 起因：agent 被要求用表格做对比，但渲染器只认 # / - / **，模型写的表格被当纯文本
// 原样吐出（竖线横杠直接显示），用户读到的就是"机器格式"。
// ---------------------------------------------------------------------------

test('表格：| a | b | + 分隔行 → thead/tbody 真表格，不再退化成段落', () => {
  const answer = [
    '| 方法 | 任务 | 来源 |',
    '| --- | --- | --- |',
    '| Latent Diffusion | 图像生成 | conf/cvpr/B25 |',
  ].join('\n');
  const blocks = renderAnswer(answer, ids, () => {});
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].props.className, 'ans-table-wrap');
  const table = blocks[0].props.children;
  assert.equal(table.type, 'table');
  assert.equal(table.props['data-testid'], 'answer-table');
  const [head, body] = table.props.children;
  assert.equal(head.type, 'thead');
  assert.equal(body.type, 'tbody');
  const flat = JSON.stringify(blocks);
  assert.match(flat, /"type":"th"/);
  assert.match(flat, /"type":"td"/);
  assert.doesNotMatch(flat, /"type":"p"/, '表格行不该退化成段落');
});

test('表格：没有分隔行时按无表头表格渲染（不猜表头）', () => {
  const blocks = renderAnswer('| 甲 | 乙 |\n| 丙 | 丁 |', [], () => {});
  const table = blocks[0].props.children;
  const [head, body] = table.props.children;
  assert.equal(head, null, '没有分隔行就不该凭空造出表头');
  assert.equal(body.type, 'tbody');
});

test('表格单元格里的引用 id 同样变成可点上标', () => {
  const answer = ['| 论文 | 年份 |', '| --- | --- |', '| conf/cvpr/B25 | 2022 |'].join('\n');
  const flat = JSON.stringify(renderAnswer(answer, ids, () => {}));
  assert.match(flat, /citation-pill/);
  assert.match(flat, /data-cited-id/);
});

test('列表：1. 有序列表渲染成 ol，与 ul 相邻时不混在一起', () => {
  const kinds = renderAnswer(['1. 第一篇', '2. 第二篇', '', '- 甲', '- 乙'].join('\n'), [], () => {}).map((b) => b.type);
  assert.deepEqual(kinds, ['ol', 'ul']);
});

test('列表：有序列表支持 1) 写法，且 ol 内条目数正确', () => {
  const blocks = renderAnswer('1) 甲\n2) 乙\n3) 丙', [], () => {});
  assert.equal(blocks[0].type, 'ol');
  assert.equal(blocks[0].props.children.length, 3);
});

test('链接：http/https 渲染成新窗口打开的 <a>，带 noreferrer', () => {
  const flat = JSON.stringify(renderAnswer('见 [示例](https://example.org/a) 一文。', [], () => {}));
  assert.match(flat, /"type":"a"/);
  assert.match(flat, /"href":"https:\/\/example.org\/a"/);
  assert.match(flat, /"target":"_blank"/);
  assert.match(flat, /"rel":"noreferrer noopener"/);
});

test('链接：非 http/https 协议一律不生成链接节点（挡协议注入）', () => {
  for (const bad of ['javascript:alert(1)', 'data:text/html,evil', 'file:///etc/passwd']) {
    const flat = JSON.stringify(renderAnswer(`见 [点我](${bad}) 。`, [], () => {}));
    assert.doesNotMatch(flat, /"type":"a"/, `${bad} 不该生成链接节点`);
  }
});

test('引用上标：有 labelById 时 title 显示可读标签 + id，没有时退回裸 id', () => {
  const labels = new Map([['conf/cvpr/B25', 'Latent Diffusion（2022）']]);
  const withLabel = JSON.stringify(renderAnswer('见 conf/cvpr/B25。', ids, () => {}, labels));
  assert.match(withLabel, /Latent Diffusion（2022） · conf\/cvpr\/B25/);

  const without = JSON.stringify(renderAnswer('见 conf/cvpr/B25。', ids, () => {}));
  assert.match(without, /"title":"conf\/cvpr\/B25"/, '没有标签时不许假装有');
});

test('表格/有序列表不会吃掉紧随其后的普通段落', () => {
  const answer = ['| 甲 | 乙 |', '| --- | --- |', '| 1 | 2 |', '', '1. 一条', '', '收尾段落。'].join('\n');
  const kinds = renderAnswer(answer, [], () => {}).map((b) => b.props?.className || b.type);
  assert.deepEqual(kinds, ['ans-table-wrap', 'ol', 'p']);
});
