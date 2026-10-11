/**
 * 回答的确定性渲染：把模型输出的 markdown-lite 文本 + 引用 id，转成 React 节点。
 *
 * 规则全部显式、可用单测锁住 —— 不引入 markdown 依赖，也不用 dangerouslySetInnerHTML：
 *   1. 空行分段；`#`/`##`/`###` 开头的行是标题（降两级，避免破坏文档层级）；
 *   2. `- ` / `* ` 开头的连续行是**无序**列表；`1. ` / `1) ` 开头的连续行是**有序**列表；
 *   3. `| a | b |` 连续行 + `| --- | --- |` 分隔行构成**表格** —— 2026-10-10 新增：
 *      agent 被要求用表格做方法/任务对比，而旧渲染器不认表格，模型写的表格会被当
 *      纯文本原样吐出来（竖线横杠直接显示在正文里，这是"格式看不懂"的直接来源）。
 *   4. `[文本](https://…)` 是**链接** —— 只放行 http/https，其余协议一律按纯文本渲染
 *      （只做协议白名单，不做域名白名单：目的是挡协议注入，不是做内容审查）；
 *   5. `**x**` 加粗；
 *   6. 回答里出现的 sourceId 原文替换成可点的引用上标（pill，带编号）；
 *      pill 的 `title` 优先显示**可读标签**（如「论文题名（2025）」），没有标签时才退回裸 id
 *      —— 用户不该为了看懂引用去读 DBLP 键。
 * 其余字符一律按纯文本渲染（React 自动转义），不存在注入面。
 *
 * 为什么是 `.js` 而不是 `.jsx`：本模块**刻意不含 JSX 字面量**（全用 `React.createElement`），
 * 这样 `node --test src/lib/answerRender.test.mjs` 能直接跑它 —— 而 Node 不认 `.jsx`
 * （`ERR_UNKNOWN_FILE_EXTENSION`）。改名前这个"由单测守住"的渲染器其实一条断言都跑不起来。
 */
import React from 'react';

/** 从回答文本里提取被引用的 id（与 citation_report 同一匹配语义：字面包含）。 */
export function findCitedIds(answer, availableIds) {
  const text = String(answer || '');
  return (Array.isArray(availableIds) ? availableIds : []).filter(
    (id) => typeof id === 'string' && id.trim() !== '' && text.includes(id),
  );
}

const RE_HEADING = /^(#{1,4})\s+(.*)$/;
const RE_UL_ITEM = /^\s*[-*]\s+(.*)$/;
const RE_OL_ITEM = /^\s*\d+[.)]\s+(.*)$/;
const RE_TABLE_ROW = /^\s*\|.*\|\s*$/;
const RE_TABLE_DIVIDER = /^\s*\|[\s:|-]+\|\s*$/;

/** 只放行 http/https。 */
function safeUrl(raw) {
  const text = String(raw || '').trim();
  return /^https?:\/\/[^\s]+$/i.test(text) ? text : null;
}

/** 取引用 id 的可读标签：`题名（年份） · id`，没有标签时退回 id 本身。 */
function labelFor(id, labelById) {
  let label = null;
  if (labelById instanceof Map) label = labelById.get(id);
  else if (labelById && typeof labelById === 'object') label = labelById[id];
  const text = typeof label === 'string' ? label.trim() : '';
  return text && text !== id ? `${text} · ${id}` : id;
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
function textWithPills(text, idToNumber, onCited, keyPrefix, labelById) {
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
      React.createElement(
        'button',
        {
          key: `${keyPrefix}-pill-${index}`,
          type: 'button',
          className: 'pill',
          'data-testid': 'citation-pill',
          'data-cited-id': match.id,
          title: labelFor(match.id, labelById),
          onClick: () => onCited && onCited(match.id),
        },
        match.number,
      ),
    );
    cursor = match.at + match.id.length;
    index += 1;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  if (nodes.length === 0) nodes.push(text);
  return nodes;
}

/** 一段文本：先切出 `[文本](url)` 链接，非链接部分再做 id → 上标替换。 */
function withLinks(text, idToNumber, onCited, keyPrefix, labelById) {
  const nodes = [];
  const re = new RegExp(/\[([^\]]+)\]\(([^)\s]+)\)/.source, 'g');
  let cursor = 0;
  let index = 0;
  let match = re.exec(text);
  while (match !== null) {
    if (match.index > cursor) {
      nodes.push(...textWithPills(text.slice(cursor, match.index), idToNumber, onCited, `${keyPrefix}-t${index}`, labelById));
    }
    const url = safeUrl(match[2]);
    if (url) {
      nodes.push(
        React.createElement(
          'a',
          {
            key: `${keyPrefix}-a${index}`,
            className: 'ans-link',
            href: url,
            target: '_blank',
            rel: 'noreferrer noopener',
            'data-testid': 'answer-link',
          },
          match[1],
        ),
      );
    } else {
      // 不支持的协议：整段当纯文本渲染，不生成任何链接节点
      nodes.push(...textWithPills(match[0], idToNumber, onCited, `${keyPrefix}-x${index}`, labelById));
    }
    cursor = re.lastIndex;
    index += 1;
    match = re.exec(text);
  }
  if (cursor < text.length) {
    nodes.push(...textWithPills(text.slice(cursor), idToNumber, onCited, `${keyPrefix}-z`, labelById));
  }
  if (nodes.length === 0) nodes.push(...textWithPills(text, idToNumber, onCited, `${keyPrefix}-all`, labelById));
  return nodes;
}

/** 一行文本：先按 `**x**` 切加粗段，段内再切链接与 id 上标。 */
function renderInline(line, idToNumber, onCited, keyPrefix, labelById) {
  const parts = String(line).split(/\*\*([^*]+)\*\*/g);
  const nodes = [];
  parts.forEach((part, index) => {
    if (part === '') return;
    if (index % 2 === 1) {
      nodes.push(
        React.createElement(
          'b',
          { key: `${keyPrefix}-b${index}` },
          withLinks(part, idToNumber, onCited, `${keyPrefix}-b${index}`, labelById),
        ),
      );
    } else {
      nodes.push(...withLinks(part, idToNumber, onCited, `${keyPrefix}-s${index}`, labelById));
    }
  });
  return nodes;
}

/** `| a | b |` → ['a', 'b']（表头行、分隔行、数据行同一套解析）。 */
function parseTableRow(line) {
  return String(line)
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

/**
 * 渲染一段回答。
 * @param {string} answer 模型输出的 markdown-lite 文本
 * @param {string[]} citedIds 回答里实际出现的引用 id（按 citation_report 的 citedIds 顺序编号）
 * @param {(id: string) => void} [onCited] 点引用上标时的回调（打开证据抽屉）
 * @param {Map<string,string>|Record<string,string>} [labelById] 引用 id → 可读标签
 *        （如「题名（2025）」）。缺省时 pill 仍以裸 id 作 title —— 不假装有标签。
 */
export function renderAnswer(answer, citedIds, onCited, labelById) {
  const idToNumber = new Map();
  (citedIds || []).forEach((id, index) => idToNumber.set(id, index + 1));

  const blocks = [];
  let listBuffer = null; // { type: 'ul' | 'ol', items: string[] }
  let tableBuffer = [];
  let paragraph = [];
  let key = 0;

  const inline = (text, prefix) => renderInline(text, idToNumber, onCited, prefix, labelById);

  const flushList = () => {
    if (!listBuffer || listBuffer.items.length === 0) {
      listBuffer = null;
      return;
    }
    const tag = listBuffer.type === 'ol' ? 'ol' : 'ul';
    const items = listBuffer.items.map((item, index) =>
      React.createElement('li', { key: `li${index}` }, inline(item, `l${key}-${index}`)),
    );
    blocks.push(React.createElement(tag, { key: `${tag}${key++}` }, items));
    listBuffer = null;
  };

  const flushTable = () => {
    if (tableBuffer.length === 0) return;
    const rows = tableBuffer;
    tableBuffer = [];
    const cells = rows.map(parseTableRow);
    if (cells.length === 0) return;
    let header = null;
    let body = cells;
    if (cells.length >= 2 && RE_TABLE_DIVIDER.test(rows[1]) && rows[1].includes('-')) {
      header = cells[0];
      body = cells.slice(2);
    }
    const tableKey = key++;
    const head = header
      ? React.createElement(
          'thead',
          null,
          React.createElement(
            'tr',
            null,
            header.map((cell, index) =>
              React.createElement('th', { key: `th${index}` }, inline(cell, `th${tableKey}-${index}`)),
            ),
          ),
        )
      : null;
    const tbody = React.createElement(
      'tbody',
      null,
      body.map((row, rowIndex) =>
        React.createElement(
          'tr',
          { key: `tr${rowIndex}` },
          row.map((cell, cellIndex) =>
            React.createElement('td', { key: `td${cellIndex}` }, inline(cell, `td${tableKey}-${rowIndex}-${cellIndex}`)),
          ),
        ),
      ),
    );
    blocks.push(
      React.createElement(
        'div',
        { className: 'ans-table-wrap', key: `tw${tableKey}` },
        React.createElement('table', { className: 'ans-table', 'data-testid': 'answer-table' }, head, tbody),
      ),
    );
  };

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push(
      React.createElement(
        'p',
        { key: `p${key++}` },
        inline(paragraph.join(' '), `p${key}`),
      ),
    );
    paragraph = [];
  };

  const flushAll = () => {
    flushList();
    flushTable();
    flushParagraph();
  };

  for (const raw of String(answer || '').split('\n')) {
    const line = raw.trimEnd();
    if (line.trim() === '') {
      flushAll();
      continue;
    }

    if (RE_TABLE_ROW.test(line)) {
      flushList();
      flushParagraph();
      tableBuffer.push(line);
      continue;
    }

    const heading = RE_HEADING.exec(line);
    if (heading) {
      flushAll();
      const level = Math.min(heading[1].length + 2, 5);
      blocks.push(
        React.createElement(`h${level}`, { key: `h${key++}` }, inline(heading[2], `h${key}`)),
      );
      continue;
    }

    const ul = RE_UL_ITEM.exec(line);
    const ol = ul ? null : RE_OL_ITEM.exec(line);
    if (ul || ol) {
      flushTable();
      flushParagraph();
      const type = ol ? 'ol' : 'ul';
      if (listBuffer && listBuffer.type !== type) flushList();
      if (!listBuffer) listBuffer = { type, items: [] };
      listBuffer.items.push((ul || ol)[1]);
      continue;
    }

    flushList();
    flushTable();
    paragraph.push(line);
  }
  flushAll();
  return blocks;
}
