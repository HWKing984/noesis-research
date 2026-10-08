/**
 * 回答的确定性渲染：把模型输出的 markdown-lite 文本 + 引用 id，转成 React 节点。
 *
 * 规则全部显式、可用单测锁住 —— 不引入 markdown 依赖，也不用 dangerouslySetInnerHTML：
 *   1. 空行分段；`#`/`##`/`###` 开头的行是标题（降两级，避免破坏文档层级）；
 *   2. `- ` / `* ` 开头的连续行是列表；
 *   3. `**x**` 加粗；
 *   4. 回答里出现的 sourceId 原文替换成可点的引用上标（pill，带编号）。
 * 其余字符一律按纯文本渲染（React 自动转义），不存在注入面。
 */
import React from 'react';

/** 从回答文本里提取被引用的 id（与 citation_report 同一匹配语义：字面包含）。 */
export function findCitedIds(answer, availableIds) {
  const text = String(answer || '');
  return (Array.isArray(availableIds) ? availableIds : []).filter(
    (id) => typeof id === 'string' && id.trim() !== '' && text.includes(id),
  );
}

/** 在纯文本里找出所有 id 出现位置（按位置排序，供切片）。 */
function idMatches(text, idToNumber) {
  const matches = [];
  for (const [id, number] of idToNumber) {
    let from = 0;
    for (;;) {
      const at = text.indexOf(id, from);
      if (at < 0) break;
      matches.push({ at, id, number });
      from = at + id.length;
    }
  }
  matches.sort((a, b) => a.at - b.at);
  return matches;
}

/** 纯文本 → 文本节点与引用上标交替的节点数组。 */
function textWithPills(text, idToNumber, onCited, keyPrefix) {
  const nodes = [];
  const matches = idMatches(text, idToNumber);
  let cursor = 0;
  let index = 0;
  for (const match of matches) {
    if (match.at < cursor) continue; // 同 id 重复登记的重叠区间
    if (match.at > cursor) {
      nodes.push(text.slice(cursor, match.at));
    }
    nodes.push(
      <button
        key={`${keyPrefix}-pill-${index}`}
        type="button"
        className="pill"
        data-testid="citation-pill"
        data-cited-id={match.id}
        title={match.id}
        onClick={() => onCited && onCited(match.id)}
      >
        {match.number}
      </button>,
    );
    cursor = match.at + match.id.length;
    index += 1;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  if (nodes.length === 0) nodes.push(text);
  return nodes;
}

/** 一行文本：先按 `**x**` 切加粗段，段内再做 id → 上标替换。 */
function renderInline(line, idToNumber, onCited, keyPrefix) {
  const parts = String(line).split(/\*\*([^*]+)\*\*/g);
  const nodes = [];
  parts.forEach((part, index) => {
    if (part === '') return;
    if (index % 2 === 1) {
      nodes.push(
        React.createElement(
          'b',
          { key: `${keyPrefix}-b${index}` },
          textWithPills(part, idToNumber, onCited, `${keyPrefix}-b${index}`),
        ),
      );
    } else {
      nodes.push(...textWithPills(part, idToNumber, onCited, `${keyPrefix}-s${index}`));
    }
  });
  return nodes;
}

/**
 * 渲染一段回答。
 * @param {string} answer 模型输出的 markdown-lite 文本
 * @param {string[]} citedIds 回答里实际出现的引用 id（按 citation_report 的 citedIds 顺序编号）
 * @param {(id: string) => void} [onCited] 点引用上标时的回调（打开证据抽屉）
 */
export function renderAnswer(answer, citedIds, onCited) {
  const idToNumber = new Map();
  (citedIds || []).forEach((id, index) => idToNumber.set(id, index + 1));

  const blocks = [];
  const listBuffer = [];
  let paragraph = [];
  let key = 0;

  const flushList = () => {
    if (listBuffer.length === 0) return;
    const items = listBuffer.map((item, index) =>
      React.createElement(
        'li',
        { key: `li${index}` },
        renderInline(item, idToNumber, onCited, `l${key}-${index}`),
      ),
    );
    blocks.push(React.createElement('ul', { key: `ul${key++}` }, items));
    listBuffer.length = 0;
  };
  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push(
      React.createElement(
        'p',
        { key: `p${key++}` },
        renderInline(paragraph.join(' '), idToNumber, onCited, `p${key}`),
      ),
    );
    paragraph = [];
  };

  for (const raw of String(answer || '').split('\n')) {
    const line = raw.trimEnd();
    if (line.trim() === '') {
      flushList();
      flushParagraph();
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      flushList();
      flushParagraph();
      const level = Math.min(heading[1].length + 2, 5);
      blocks.push(
        React.createElement(
          `h${level}`,
          { key: `h${key++}` },
          renderInline(heading[2], idToNumber, onCited, `h${key}`),
        ),
      );
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      flushParagraph();
      listBuffer.push(line.replace(/^\s*[-*]\s+/, ''));
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushList();
  flushParagraph();
  return blocks;
}
