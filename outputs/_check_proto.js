
'use strict';
/* ================= mock 数据（AI-Literature 图谱，与 /api/health 同构） ================= */
var GRAPH_ID = 'ai-literature-ed16399925fac2a599ed';
var MOCK = {
  health: { status: 'ready', graphId: GRAPH_ID, pinnedGraphId: GRAPH_ID,
    scope: { bibliographyTitles: 20000, modelTitles: 19999, candidateAssertions: 21497 } },
  papers: [
    { id: 'conf/nips/VaswaniSPUJGKP17', title: 'Attention Is All You Need', year: 2017, venue: 'NeurIPS', model: true },
    { id: 'conf/nips/SohlDicksteinWZ20', title: 'Denoising Diffusion Probabilistic Models', year: 2020, venue: 'NeurIPS', model: true },
    { id: 'conf/iclr/DosovitskiyDJ0PZ21', title: 'An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale', year: 2021, venue: 'ICLR', model: true },
    { id: 'conf/naacl/DevlinCLT19', title: 'BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding', year: 2019, venue: 'NAACL', model: true },
    { id: 'conf/nips/BrownMRSKDNSSAA20', title: 'Language Models are Few-Shot Learners', year: 2020, venue: 'NeurIPS', model: false },
    { id: 'conf/cvpr/HeZRS16', title: 'Deep Residual Learning for Image Recognition', year: 2016, venue: 'CVPR', model: true },
    { id: 'conf/cvpr/KarrasLA19', title: 'A Style-Based Generator Architecture for Generative Adversarial Networks', year: 2019, venue: 'CVPR', model: true },
    { id: 'arxiv/KaplanMcB20', title: 'Scaling Laws for Neural Language Models', year: 2020, venue: 'arXiv', model: false }
  ],
  detail: {
    publication: { id: 'conf/nips/SohlDicksteinWZ20', title: 'Denoising Diffusion Probabilistic Models', year: 2020, doi: '10.5555/3495724.3496298' },
    authors: [
      { name: 'Jascha Sohl-Dickstein', status: 'dblp' },
      { name: 'Eric A. Weiss', status: 'pending' },
      { name: 'Niru Maheswaranathan', status: 'pending' },
      { name: 'Surya Ganguli', status: 'dblp' }
    ],
    venues: ['NeurIPS 2020'],
    mentions: [{ t: 'diffusion model', l: 'METHOD' }, { t: 'image generation', l: 'TASK' }, { t: 'ImageNet', l: 'DATASET' }],
    assertions: [
      { pred: 'USED_FOR', head: 'diffusion model', tail: 'image generation', conf: 0.7241, ev: 'Denoising Diffusion Probabilistic Models' },
      { pred: 'EVALUATED_ON', head: 'image generation', tail: 'ImageNet', conf: 0.6812, ev: 'Denoising Diffusion Probabilistic Models' }
    ],
    citation: 'Sohl-Dickstein, J., Weiss, E. A., Maheswaranathan, N., & Ganguli, S. (2020). Denoising diffusion probabilistic models. NeurIPS.',
    notice: '方法—任务 / 方法—数据集关系由模型从题名抽取，状态恒为 candidate，不是已核实事实。'
  },
  graph: {
    rootId: 'p1',
    nodes: [
      { id: 'p1', kind: 'Publication', name: 'Denoising Diffusion Probabilistic Models' },
      { id: 'a1', kind: 'Person', name: 'Jascha Sohl-Dickstein' },
      { id: 'a2', kind: 'Person', name: 'Surya Ganguli' },
      { id: 'v1', kind: 'Venue', name: 'NeurIPS' },
      { id: 'c1', kind: 'Concept', name: 'diffusion model' },
      { id: 't1', kind: 'Task', name: 'image generation' },
      { id: 'd1', kind: 'Dataset', name: 'ImageNet' },
      { id: 'p2', kind: 'Publication', name: 'Improved DDPM' },
      { id: 'p3', kind: 'Publication', name: 'Score-Based Generative Modeling via SDE' }
    ],
    edges: [
      { id: 'e1', source: 'p1', target: 'a1', kind: 'WRITTEN_BY' },
      { id: 'e2', source: 'p1', target: 'a2', kind: 'WRITTEN_BY' },
      { id: 'e3', source: 'p1', target: 'v1', kind: 'PUBLISHED_IN' },
      { id: 'e4', source: 'p1', target: 'c1', kind: 'MENTIONS' },
      { id: 'e5', source: 'c1', target: 't1', kind: 'USED_FOR', cand: true },
      { id: 'e6', source: 'p1', target: 'd1', kind: 'EVALUATED_ON', cand: true },
      { id: 'e7', source: 'p2', target: 'c1', kind: 'MENTIONS' },
      { id: 'e8', source: 'p3', target: 'c1', kind: 'MENTIONS' }
    ],
    paths: [
      { text: 'Denoising Diffusion Probabilistic Models —WRITTEN_BY→ Jascha Sohl-Dickstein' },
      { text: 'Denoising Diffusion Probabilistic Models —PUBLISHED_IN→ NeurIPS' },
      { text: 'diffusion model —USED_FOR→ image generation（候选）' },
      { text: 'Denoising Diffusion Probabilistic Models —EVALUATED_ON→ ImageNet（候选）' }
    ],
    meta: { nodes: 9, edges: 8, pathsReturned: 4, hasMorePaths: false }
  },
  evidence: { label: 'DBLP 书目', level: '题名级', ver: '未核验', caveat: '题名级证据只能证明论文存在、题名里出现了相关词；不能证明方法或任务的真实使用。' },
  suggests: [
    { l: '扩散模型 → image generation', h: '候选断言 · 方法→任务', q: 'diffusion' },
    { l: '题名含 transformer 的论文', h: '题名检索 · 8 篇', q: 'transformer' },
    { l: 'ImageNet 上的分类方法', h: '数据集候选 · 评测关系', q: 'ImageNet' },
    { l: 'NeurIPS 2020 · 生成模型', h: '会议 + 年份组合', q: 'generative' }
  ],
  history: ['有哪些关于 transformer 的论文?', '有哪些关于 transformer 的论文?', '有哪些关于 diffusion 的论文?'],
  boundary: [
    '图谱是<b>候选断言图</b>：方法—任务 / 方法—数据集关系 status 恒为 candidate，不会讲成已核实事实。',
    '证据深度目前只有<b>题名</b>：只能证明论文存在、题名里出现了相关词。',
    '只有书目与题名；摘要仅 75 篇，全文 0 篇，不托管 PDF。',
    '没有引用数据，因此<b>不提供</b>「必引 / 被引次数 / 引用链 / 影响力排序」。',
    '图谱不可用时会明确报错（503），<b>不会</b>回退成「没有搜到」。'
  ]
};
var KIND_ZH = { Publication: '论文', Person: '作者', Venue: '会议', Concept: '概念', Task: '任务', Dataset: '数据集' };

/* ================= 状态 ================= */
var S = {
  dir: 'baseline', theme: 'light',
  searched: false, q: '', filters: null,           // filters: {method,task,dataset,author,venue,year,limit}
  selected: null, tab: 'detail',
  filtersOpen: false, infoOpen: false, graphMode: 'paper', evDrawer: null
};

/* ================= 小工具 ================= */
function $(s) { return document.querySelector(s); }
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function fmt(n) { return Number(n).toLocaleString('en-US'); }
function svgIco(d, extra) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' + (extra || '') + '><path d="' + d + '"/></svg>'; }
var ICO = {
  search: 'M21 21l-4.35-4.35M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0z',
  filter: 'M4 6h16M7 12h10M10 18h4',
  info: 'M12 8h.01M11 12h1v4h1M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18z',
  close: 'M18 6 6 18M6 6l12 12',
  chat: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  book: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z',
  plus: 'M12 5v14M5 12h14',
  sun: 'M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z'
};
var toastTimer = null;
function toast(msg) {
  var t = $('#toast'); t.textContent = msg; t.classList.add('is-on');
  clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.classList.remove('is-on'); }, 1800);
}
function activeFilterCount() {
  if (!S.filters) return 0;
  var n = 0;
  ['method', 'task', 'dataset', 'author', 'venue', 'year'].forEach(function (k) { if ((S.filters[k] || '').trim()) n++; });
  return n;
}

/* ================= 侧栏（照截图） ================= */
function renderSidebar() {
  var spiral = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 12m-2 0a2 2 0 1 0 4 0 4 4 0 1 0-8 0 6 6 0 1 0 12 0 8 8 0 1 0-16 0"/></svg>';
  var themeIco = S.theme === 'dark' ? svgIco(ICO.sun) : svgIco(ICO.moon);
  $('#sidebar').innerHTML =
    '<div class="sb-header"><div class="sb-logo"><span class="sb-logo-mark">' + spiral + '</span><span class="sb-logo-name">NOESIS Research</span></div></div>' +
    '<button class="sb-new" data-act="new-research">' + svgIco(ICO.plus) + '<span>新的研究</span></button>' +
    '<nav class="sb-nav">' +
      '<button class="sb-item" data-act="nav-agent" title="本轮原型聚焦论文库与图谱">' + svgIco(ICO.chat) + '<span>科研助手</span></button>' +
      '<button class="sb-item is-active">' + svgIco(ICO.book) + '<span>论文库与图谱</span></button>' +
    '</nav>' +
    '<div class="sb-sec">本次会话</div>' +
    '<div class="sb-sessions">' +
      MOCK.history.map(function (q, i) {
        return '<button class="sb-hist' + (i === 0 ? ' is-active' : '') + '" data-act="nav-agent" title="' + esc(q) + '">' +
          '<span class="sb-hist-icon">' + svgIco(ICO.chat) + '</span>' +
          '<span style="min-width:0;flex:1"><span class="sb-hist-t">' + esc(q) + '</span></span></button>';
      }).join('') +
    '</div>' +
    '<div class="sb-foot">' +
      '<div class="sb-foot-l"><span class="dot"></span><span>Agent 就绪 · deepseek-v4-flash</span></div>' +
      '<button class="sb-theme" data-act="theme" aria-label="切换深浅色">' + themeIco + '</button>' +
    '</div>';
}

/* ================= 共享片段 ================= */
function evChipHtml(onClickAct) {
  var e = MOCK.evidence;
  return '<button class="ev-chip" data-act="' + (onClickAct || 'evidence-open') + '" title="' + esc(e.caveat) + '">' + e.label + ' · ' + e.level + ' · ' + e.ver + '</button>';
}
function paperRowHtml(p, selected) {
  return '<div class="paper-row' + (selected ? ' is-active' : '') + '" role="button" tabindex="0" data-act="paper-open" data-id="' + esc(p.id) + '" style="font:inherit;color:inherit">' +
    '<div class="pr-main">' +
      '<span class="pr-title">' + esc(p.title) + '</span>' +
      '<span class="pr-meta">' + p.year + ' · ' + esc(p.venue) + ' · <span class="mono" style="font-size:10.5px">' + esc(p.id) + '</span></span>' +
    '</div>' +
    '<div class="pr-side">' +
      '<span class="badge">' + (p.model ? '已建模型' : '仅书目') + '</span>' +
      evChipHtml() +
    '</div>' +
  '</div>';
}
function listHtml(papers, selectedId, compact) {
  return papers.map(function (p) {
    var row = paperRowHtml(p, p.id === selectedId);
    return compact ? row : row;
  }).join('');
}
function summaryHtml(papers) {
  var expanded = (S.q || '').indexOf('扩散') >= 0 || (S.filters && (S.filters.method || '').indexOf('扩散') >= 0);
  var ex = expanded ? ' · 别名展开：<code>method → diffusion model(s)</code>' : '';
  return '<span><b style="color:var(--text-primary);font-weight:600">' + papers.length + ' 篇</b> · source 真实 Neo4j' + ex + '</span>';
}
function detailBodyHtml(compact) {
  var d = MOCK.detail, h = '';
  h += '<h2 class="dt-title">' + esc(d.publication.title) + '</h2>';
  h += '<div class="dt-id">' + esc(d.publication.id) + '</div>';
  h += '<div class="dt-links">' + evChipHtml() +
    '<a data-act="noop" href="javascript:void 0">DOI</a><a data-act="noop" href="javascript:void 0">DBLP</a>' +
    '<span class="badge">' + d.publication.year + '</span></div>';
  h += '<div class="dt-sec"><h3>作者（' + d.authors.length + '）</h3>' + d.authors.map(function (a) {
    return '<div class="dt-auth"><span>' + esc(a.name) + '</span><span class="badge">' + (a.status === 'dblp' ? 'DBLP 主页身份已匹配' : '身份未决') + '</span></div>';
  }).join('') + '</div>';
  h += '<div class="dt-sec"><h3>会议 / 期刊</h3><div class="dt-chips">' + d.venues.map(function (v) {
    return '<span class="chip">' + esc(v) + '</span>';
  }).join('') + '</div></div>';
  h += '<div class="dt-sec"><h3>实体提及（' + d.mentions.length + '）</h3><div class="dt-chips">' + d.mentions.map(function (m) {
    return '<span class="chip">' + esc(m.t) + ' <span style="color:var(--text-muted);font-size:10px">' + m.l + '</span></span>';
  }).join('') + '</div></div>';
  h += '<div class="dt-sec"><h3>候选断言（' + d.assertions.length + '）</h3>' +
    '<p class="hint">' + (compact ? '' : '') + esc(d.notice) + '</p>' + d.assertions.map(function (a) {
      return '<div class="dt-assert"><div class="top"><span class="chip is-cand">候选</span><code class="pred">' + esc(a.pred) + '</code>' +
        '<span>' + esc(a.head) + ' → ' + esc(a.tail) + '</span><span class="score">分数 ' + a.conf.toFixed(4) + '（未校准）</span></div>' +
        '<div class="ev">' + evChipHtml() + '</div></div>';
    }).join('') + '</div>';
  h += '<div class="dt-sec"><h3>引文草稿</h3><p class="hint">这是草稿，引用前须核对原文与书目信息。</p><p class="dt-cite">' + esc(d.citation) + '</p></div>';
  h += '<div class="dt-notice">候选断言不是已核实事实；引用前请阅读原文。</div>';
  return h;
}
/* 环形图谱 SVG */
function graphSvg(g, size) {
  size = size || 480;
  var c = size / 2, R = c - 66;
  var others = g.nodes.filter(function (n) { return n.id !== g.rootId; });
  var pos = {}; pos[g.rootId] = [c, c];
  others.forEach(function (n, i) {
    var ang = (i / Math.max(others.length, 1)) * Math.PI * 2 - Math.PI / 2;
    pos[n.id] = [c + R * Math.cos(ang), c + R * Math.sin(ang)];
  });
  var h = '<svg viewBox="0 0 ' + size + ' ' + size + '" style="width:100%;max-width:' + (size + 60) + 'px;height:auto" role="img" aria-label="局部知识图谱">';
  g.edges.forEach(function (e) {
    var a = pos[e.source], b = pos[e.target]; if (!a || !b) return;
    var dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
    var r1 = e.source === g.rootId ? 27 : 17, r2 = e.target === g.rootId ? 27 : 17;
    var x1 = a[0] + dx * r1 / L, y1 = a[1] + dy * r1 / L, x2 = b[0] - dx * (r2 + 7) / L, y2 = b[1] - dy * (r2 + 7) / L;
    h += '<line x1="' + x1.toFixed(1) + '" y1="' + y1.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) + '" stroke="var(--border-strong)" stroke-width="1.3"/>';
    h += '<text x="' + ((x1 + x2) / 2).toFixed(1) + '" y="' + ((y1 + y2) / 2 - 4).toFixed(1) + '" text-anchor="middle" font-size="9.5" fill="var(--text-tertiary)" font-family="var(--font-mono)">' + esc(e.kind) + (e.cand ? '（候选）' : '') + '</text>';
  });
  g.nodes.forEach(function (n) {
    var p = pos[n.id]; if (!p) return;
    var isRoot = n.id === g.rootId, r = isRoot ? 26 : 16;
    var label = (n.name.length > 15 ? n.name.slice(0, 14) + '…' : n.name);
    h += '<g data-act="g-node" data-node="' + n.id + '" style="cursor:pointer">' +
      '<title>' + KIND_ZH[n.kind] + '：' + esc(n.name) + '</title>' +
      '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="' + r + '" fill="' + (isRoot ? 'var(--text-primary)' : 'var(--bg-elevated)') + '" stroke="var(--border-strong)" stroke-width="' + (isRoot ? 0 : 1.2) + '"/>' +
      '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] + 3.5).toFixed(1) + '" text-anchor="middle" font-size="' + (isRoot ? 10.5 : 9) + '" fill="' + (isRoot ? 'var(--bg-primary)' : 'var(--text-secondary)') + '">' + KIND_ZH[n.kind] + '</text>' +
      '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] + r + 14).toFixed(1) + '" text-anchor="middle" font-size="10" fill="var(--text-secondary)">' + esc(label) + '</text>' +
      '</g>';
  });
  return h + '</svg>';
}

/* ================= 瘦身 header（B/C 共用，A 用更轻版） ================= */
function slimHeaderHtml() {
  var sc = MOCK.health.scope;
  return '<div class="b-top">' +
    '<span class="b-crumb">论文库与图谱</span>' +
    '<span class="a-status"><span class="dot"></span>ready</span>' +
    '<div class="b-count">' +
      '<span><b>' + fmt(sc.bibliographyTitles) + '</b> 书目</span>' +
      '<span><b>' + fmt(sc.modelTitles) + '</b> 已建模型</span>' +
      '<span><b>' + fmt(sc.candidateAssertions) + '</b> 候选断言</span>' +
    '</div>' +
    '<button class="icon-btn" data-act="info-toggle" aria-label="图谱版本与边界">' + svgIco(ICO.info) + '</button>' +
    (S.infoOpen ? infoPopHtml() : '') +
  '</div>';
}
function infoPopHtml() {
  return '<div class="pop" style="right:20px;top:52px">' +
    '<h4>图谱版本与边界</h4>' +
    '<span class="idfull">' + esc(GRAPH_ID) + '</span>' +
    '<div class="kv"><span class="k">版本锁定</span><span>已锁定 · 检索与图谱都读这一个版本</span>' +
    '<span class="k">数据来源</span><span>DBLP 结构化 XML · 冻结 SciBERT NER/RE</span></div>' +
    '<ul>' + MOCK.boundary.join('') + '</ul>' +
  '</div>';
}
function filterPopHtml(cls) {
  var f = S.filters || {};
  var inp = function (k, label, ph) {
    return '<label class="f"><span>' + label + '</span><input data-filter="' + k + '" value="' + esc(f[k] || '') + '" placeholder="' + (ph || '') + '"></label>';
  };
  return '<div class="pop ' + (cls || '') + '">' +
    '<h4>更多筛选</h4>' +
    '<div class="grid2">' +
      inp('method', '方法', '扩散模型') + inp('task', '任务', 'image generation') +
      inp('dataset', '数据集', 'ImageNet') + inp('author', '作者', '') +
      inp('venue', '会议 / 期刊', '') + inp('year', '年份（2015–2025）', '2015–2025') +
    '</div>' +
    '<div style="display:flex;align-items:center;gap:10px;margin-top:10px">' +
      '<span style="font-size:11px;color:var(--text-tertiary)">每页</span>' +
      '<select data-filter="limit" style="height:26px;border:1px solid var(--border-subtle);border-radius:6px;background:var(--bg-primary);color:var(--text-primary);font-size:12px">' +
        [10, 15, 25].map(function (n) { return '<option ' + (Number(f.limit || 10) === n ? 'selected' : '') + '>' + n + '</option>'; }).join('') +
      '</select>' +
      '<button class="clr" data-act="filters-clear" style="margin-left:auto">清除全部筛选</button>' +
    '</div>' +
  '</div>';
}
function filterChipsHtml() {
  var f = S.filters || {}, labels = { method: '方法', task: '任务', dataset: '数据集', author: '作者', venue: '会议 / 期刊', year: '年份' };
  var chips = [];
  Object.keys(labels).forEach(function (k) {
    if ((f[k] || '').trim()) chips.push('<span class="b-fchip">' + labels[k] + ': ' + esc(f[k]) + '<button data-act="filter-remove" data-k="' + k + '" aria-label="移除">×</button></span>');
  });
  return chips.length ? '<div class="b-filters">' + chips.join('') + '</div>' : '';
}

/* ================= 方向：现状复刻 ================= */
function viewBaseline() {
  var sc = MOCK.health.scope;
  var form = [
    ['q', '关键词（题名）', 'transformer / 扩散模型', S.q || 'transformer / 扩散模型'],
    ['method', '方法', '扩散模型', ''],
    ['task', '任务', 'image generation', ''],
    ['dataset', '数据集', 'ImageNet', ''],
    ['author', '作者', '', ''],
    ['venue', '会议 / 期刊', '', ''],
    ['year', '年份（2015–2025）', '2015–2025', ''],
    ['limit', '条数（1–25）', '1–25', '10']
  ];
  var grid = form.map(function (f) {
    return '<label class="bl-f"><span>' + f[1] + '</span><input data-bl="' + f[0] + '" placeholder="' + esc(f[2]) + '" value="' + esc(f[3]) + '"></label>';
  }).join('');
  var papers = MOCK.papers;
  var leftStage;
  if (!S.searched) {
    leftStage = '<div class="bl-stage"><div class="bl-empty">输入条件后点「检索」。检索结果里的每一条都带来源引用，可以直接核对。</div></div>';
  } else {
    leftStage = '<div class="bl-stage"><ul class="bl-list">' + MOCK.papers.map(function (p) {
      return '<li><div class="bl-li' + (p.id === S.selected ? ' is-active' : '') + '" role="button" tabindex="0" data-act="paper-open" data-id="' + esc(p.id) + '" style="font:inherit;color:inherit">' +
        '<span class="t">' + esc(p.title) + '</span><div class="id">' + esc(p.id) + '</div>' +
        '<div class="badges"><span class="badge">' + (p.model ? '已建模型提及' : '仅书目') + '</span>' + evChipHtml() + '</div></div></li>';
    }).join('') + '</ul></div>';
  }
  return '<div class="dirview">' +
    '<div class="bl-top">' +
      '<span class="crumb">论文库与图谱</span>' +
      '<span class="chip"><span class="dot"></span>ready</span>' +
      '<span>graphId <code>' + esc(GRAPH_ID) + '</code></span>' +
      '<span data-testid="pin-state">版本锁定 <code>' + esc(GRAPH_ID.slice(0, 18)) + '…</code></span>' +
      '<span>书目 <b>' + sc.bibliographyTitles + '</b> · 已建模型 <b>' + sc.modelTitles + '</b> · 候选断言 <b>' + sc.candidateAssertions + '</b></span>' +
    '</div>' +
    '<div class="bl-body">' +
      '<div class="bl-left">' +
        '<form class="bl-form" data-testid="search-form">' +
          '<div class="bl-grid">' + grid + '</div>' +
          '<div class="bl-act"><button type="button" class="bl-go" data-act="bl-search">' + (S.searched ? '检索中…'.replace('…', '') : '检索') + '</button>' +
          '<span class="bl-note">中文仅在 22 条固定别名上做精确展开（如「扩散模型」→ diffusion model(s)）；未知中文原样检索。</span></div>' +
        '</form>' +
        (S.searched ?
          '<div class="bl-echo">实参回显：' +
            ['q=transformer / 扩散模型', 'method=扩散模型', 'task=image generation', 'dataset=ImageNet', 'year=2015-2025', 'limit=10'].map(function (x) { return '<code>' + esc(x) + '</code>'; }).join(' ') +
            ' <span>source=neo4j</span> <span>别名表=v4</span><br>别名展开：<code>method → diffusion model(s)</code></div>' : '') +
        '<details class="bl-notice"><summary>本系统能做什么、不能做什么</summary><ul>' + MOCK.boundary.join('') + '</ul></details>' +
        leftStage +
      '</div>' +
      '<aside class="bl-aside">' +
        '<nav class="bl-tabs"><button class="' + (S.tab === 'detail' ? 'is-on' : '') + '">论文详情</button><button class="' + (S.tab === 'graph' ? 'is-on' : '') + '">局部图谱</button></nav>' +
        '<div class="bl-stage">' + (S.selected ?
          (S.tab === 'detail' ?
            '<div class="dw-body" style="padding:16px 18px 90px">' + detailBodyHtml(true) + '</div>' :
            '<div class="dw-body" style="padding:16px 18px 90px"><div class="g-wrap">' + graphSvg(MOCK.graph, 420) +
            '<div class="g-nodeinfo">9 节点 · 8 关系 · 4 条路径（上限 30）· 真实 Neo4j</div></div></div>') :
          '<div class="bl-empty">左侧选择一篇论文后，这里显示详情或局部图谱。</div>') +
        '</div>' +
      '</aside>' +
    '</div>' +
  '</div>';
}

/* ================= 方向 A：检索优先 ================= */
function searchRowHtml(compact) {
  var n = activeFilterCount();
  return '<div class="a-search">' +
    '<span class="a-ico">' + svgIco(ICO.search) + '</span>' +
    '<input class="a-input" id="mainQ" placeholder="输入题名、方法、作者……" value="' + esc(S.q) + '" aria-label="检索关键词">' +
    '<button class="a-btn" data-act="filters-toggle">筛选' + (n ? '<span class="n">' + n + '</span>' : '') + svgIco('m6 9 6 6 6-6') + '</button>' +
    '<button class="a-go" data-act="search-submit">检索</button>' +
    (S.filtersOpen ? filterPopHtml('a-fpop') : '') +
  '</div>';
}
function viewA() {
  var papers = MOCK.papers;
  if (!S.searched) {
    var sc = MOCK.health.scope;
    return '<div class="dirview">' +
      '<div class="a-top"><span class="a-crumb">论文库与图谱</span><span class="a-status"><span class="dot"></span>ready</span>' +
        '<span style="margin-left:auto"></span>' +
        '<button class="icon-btn" data-act="info-toggle" aria-label="图谱版本与边界">' + svgIco(ICO.info) + '</button>' +
        (S.infoOpen ? infoPopHtml() : '') + '</div>' +
      '<div class="a-hero"><div class="a-hero-inner">' +
        '<h1 class="a-title">检索文献，核对证据</h1>' +
        '<p class="a-sub"><b>' + fmt(sc.bibliographyTitles) + '</b> 篇书目 · <b>' + fmt(sc.modelTitles) + '</b> 篇已建模型 · <b>' + fmt(sc.candidateAssertions) + '</b> 条候选断言。<br>每一条结果都带来源引用，可以直接核对。</p>' +
        searchRowHtml() +
        '<div class="a-cards">' + MOCK.suggests.map(function (s) {
          return '<button class="a-card" data-act="suggest" data-q="' + esc(s.q) + '"><span class="l">' + esc(s.l) + '</span><span class="h">' + esc(s.h) + '</span></button>';
        }).join('') + '</div>' +
      '</div></div>' +
    '</div>';
  }
  /* 结果态：搜索框吸顶 + 列表 + 右侧抽屉 */
  return '<div class="dirview">' +
    '<div class="a-result" style="padding-top:0;padding-bottom:110px">' +
      '<div class="a-fixedbar">' + searchRowHtml(true) + '</div>' +
      '<div class="a-res-head" style="margin-top:12px">' + summaryHtml(papers) + '</div>' +
      '<div class="a-list">' + listHtml(papers, S.selected) + '</div>' +
    '</div>' +
  '</div>';
}

/* ================= 方向 B：检索带 + 双栏 ================= */
function viewB() {
  var papers = MOCK.papers;
  var left;
  if (!S.searched) {
    left = '<div class="b-list" style="display:flex;flex-direction:column"><div class="b-sug">' +
      '<div class="t">试试这些检索</div><div class="b-sug-row">' +
      MOCK.suggests.map(function (s) { return '<button class="b-sug-pill" data-act="suggest" data-q="' + esc(s.q) + '">' + esc(s.l) + '</button>'; }).join('') +
      '</div></div></div>';
  } else {
    left = '<div class="b-summary">' + summaryHtml(papers) + '</div><div class="b-list">' + listHtml(papers, S.selected) + '</div>';
  }
  return '<div class="dirview">' +
    slimHeaderHtml() +
    '<div class="b-bar">' +
      '<span class="b-barico">' + svgIco(ICO.search) + '</span>' +
      '<input class="b-input" id="mainQ" style="padding-left:34px" placeholder="输入题名关键词，如 transformer / 扩散模型" value="' + esc(S.q) + '" aria-label="检索关键词">' +
      '<button class="a-btn" style="height:38px" data-act="filters-toggle">筛选' + (activeFilterCount() ? '<span class="n">' + activeFilterCount() + '</span>' : '') + svgIco('m6 9 6 6 6-6') + '</button>' +
      '<button class="a-go" style="height:38px" data-act="search-submit">检索</button>' +
      (S.filtersOpen ? filterPopHtml('a-fpop') : '') +
    '</div>' +
    filterChipsHtml() +
    '<div class="b-body">' +
      '<div class="b-left">' + left + '</div>' +
      '<aside class="b-aside">' +
        '<nav class="dw-tabs">' +
          '<button class="' + (S.tab === 'detail' ? 'is-on' : '') + '" data-act="tab" data-tab="detail">论文详情</button>' +
          '<button class="' + (S.tab === 'graph' ? 'is-on' : '') + '" data-act="tab" data-tab="graph">局部图谱</button>' +
          (S.selected ? '<span class="mono" style="margin-left:auto;font-size:10px;color:var(--text-muted)">' + esc(S.selected) + '</span>' : '') +
        '</nav>' +
        '<div class="dw-body">' + (S.selected ?
          (S.tab === 'detail' ? detailBodyHtml(true) :
            '<div class="g-wrap">' + graphSvg(MOCK.graph, 420) + '<div class="g-nodeinfo">9 节点 · 8 关系 · 4 条路径（上限 30）· 真实 Neo4j</div></div>') :
          '从左侧选择一篇论文，这里显示详情或局部图谱。') +
        '</div>' +
      '</aside>' +
    '</div>' +
  '</div>';
}

/* ================= 方向 C：图谱优先三栏 ================= */
function viewC() {
  var papers = MOCK.papers;
  var hasSel = Boolean(S.selected);
  var listCol = '<div class="c-list">' +
    (S.searched ? '<div class="b-summary" style="padding:8px 16px 6px">' + summaryHtml(papers) + '</div><div class="b-list">' + listHtml(papers, S.selected) + '</div>'
      : '<div class="b-list" style="display:flex;flex-direction:column"><div class="b-sug"><div class="t">试试这些检索</div><div class="b-sug-row">' +
        MOCK.suggests.slice(0, 3).map(function (s) { return '<button class="b-sug-pill" data-act="suggest" data-q="' + esc(s.q) + '">' + esc(s.l) + '</button>'; }).join('') +
        '</div></div></div>') +
    '</div>';
  var graphCol;
  if (!hasSel) {
    graphCol = '<div class="c-graph"><div class="c-g-empty" style="margin:auto">' +
      '<p class="t">选一篇论文，图谱在这里展开</p>' +
      '<p class="d">作者 · 会议 · 方法概念 · 任务 · 数据集，以及它们之间的候选关系。<br>每条关系都带着「候选」标记与来源证据。</p></div></div>';
  } else {
    var d = MOCK.detail;
    var modeSeg = '<div class="seg">' + [['paper', '本篇关系'], ['coauthors', '共同作者'], ['methods', '共享方法']].map(function (m) {
      return '<button class="' + (S.graphMode === m[0] ? 'is-on' : '') + '" data-act="graph-mode" data-mode="' + m[0] + '">' + m[1] + '</button>';
    }).join('') + '</div>';
    graphCol = '<div class="c-graph">' +
      '<div class="c-g-head">' +
        '<div class="c-g-title">' + esc(d.publication.title) + '<div class="c-g-meta">' + d.publication.year + ' · NeurIPS · 9 节点 · 8 关系 · 4 条路径 · 真实 Neo4j</div></div>' +
        modeSeg +
      '</div>' +
      '<div class="c-g-canvas">' +
        '<div class="g-wrap">' + graphSvg(MOCK.graph, 480) + '<div class="g-nodeinfo" id="gNodeInfo">点击节点查看属性；论文节点可打开详情。</div></div>' +
        '<details class="g-paths"><summary>查看实际连接路径（4 条）</summary>' + MOCK.graph.paths.map(function (p) {
          return '<div class="g-path">' + esc(p.text) + '</div>';
        }).join('') + '</details>' +
      '</div>' +
    '</div>';
  }
  var detailCol = '<div class="c-detail">' + (hasSel ? detailBodyHtml(true) :
    '<div style="text-align:center;color:var(--text-tertiary);font-size:12.5px;padding:40px 10px">论文详情会显示在这里：<br>作者身份 · 实体提及 · 候选断言 · 引文草稿</div>') + '</div>';
  return '<div class="dirview">' +
    slimHeaderHtml() +
    '<div class="c-bar">' +
      '<span class="b-barico">' + svgIco(ICO.search) + '</span>' +
      '<input class="b-input" id="mainQ" style="padding-left:34px" placeholder="检索题名 / 方法 / 作者……" value="' + esc(S.q) + '" aria-label="检索关键词">' +
      '<button class="a-btn" data-act="filters-toggle">筛选' + (activeFilterCount() ? '<span class="n">' + activeFilterCount() + '</span>' : '') + '</button>' +
      '<button class="a-go" data-act="search-submit">检索</button>' +
      (S.filtersOpen ? filterPopHtml('a-fpop') : '') +
    '</div>' +
    filterChipsHtml() +
    '<div class="c-body">' + listCol + graphCol + detailCol + '</div>' +
  '</div>';
}

/* ================= 评审控制条 ================= */
var DIRS = [
  { key: 'baseline', label: '现状', cost: '对照基线' },
  { key: 'A', label: 'A 检索优先', cost: 'A · 单列居中 + 详情改右侧抽屉。表单 8→1+筛选面板；graphId/边界收进 ⓘ。零后端改动，抽屉复用 EvidenceDrawer 模式。' },
  { key: 'B', label: 'B 检索带', cost: 'B · 保留双栏，8 字段收成一条检索带 + 筛选弹出。改动最小，零后端改动。' },
  { key: 'C', label: 'C 图谱优先', cost: 'C · 图谱从 tab 升级为主区：列表 300px | 图谱 | 详情卡。零后端改动；后续可移植 NOESIS KnowledgeGraphSigma。' }
];
function renderBar() {
  var cur = DIRS.filter(function (d) { return d.key === S.dir; })[0];
  $('#reviewBar').innerHTML =
    DIRS.map(function (d, i) {
      return '<button class="rv-btn ' + (S.dir === d.key ? 'is-on' : '') + '" data-act="dir" data-dir="' + d.key + '" title="键盘 ' + (i + 1) + '">' +
        '<span class="rv-key">' + (i + 1) + '</span>' + d.label + '</button>';
    }).join('') +
    '<span class="rv-sep"></span>' +
    '<button class="rv-btn" data-act="theme" title="键盘 T">' + (S.theme === 'dark' ? '浅色' : '深色') + '</button>' +
    '<span class="rv-cost">' + (cur ? cur.cost : '') + '</span>';
}

/* ================= 渲染入口 ================= */
function render() {
  document.documentElement.dataset.theme = S.theme;
  renderSidebar();
  renderBar();
  var v = { baseline: viewBaseline, A: viewA, B: viewB, C: viewC }[S.dir];
  $('#stage').innerHTML = v();
  $('#drawer').style.display = 'none';
  $('#mask').style.display = 'none';
}
/* A 方向的详情抽屉（独立于 render 全量重绘，直接开） */
function openDrawer(id) {
  S.selected = id; S.tab = 'detail';
  $('#dwTabs').innerHTML =
    '<button class="is-on" data-act="tab" data-tab="detail">论文详情</button>' +
    '<button data-act="tab" data-tab="graph">局部图谱</button>' +
    '<span class="mono" style="margin-left:auto;font-size:10px;color:var(--text-muted);padding-bottom:6px">' + esc(id) + '</span>' +
    '<button class="icon-btn" data-act="drawer-close" aria-label="关闭" style="margin-left:8px">' + svgIco(ICO.close) + '</button>';
  $('#dwBody').innerHTML = detailBodyHtml(true);
  $('#drawer').style.display = 'flex';
  $('#mask').style.display = 'block';
  document.body.classList.add('is-drawer');
}
function closeDrawer() {
  document.body.classList.remove('is-drawer');
  $('#drawer').style.display = 'none';
  $('#mask').style.display = 'none';
}
function openEvidence() {
  var e = MOCK.evidence, d = MOCK.detail;
  S.evDrawer = true;
  $('#dwTabs').innerHTML = '<button class="is-on">证据详情</button><button class="icon-btn" data-act="drawer-close" aria-label="关闭" style="margin-left:auto">' + svgIco(ICO.close) + '</button>';
  $('#dwBody').innerHTML =
    '<h2 class="dt-title" style="font-size:14px">' + esc(d.publication.title) + '</h2>' +
    '<div class="dt-id">' + esc(d.publication.id) + '</div>' +
    '<div class="dt-sec"><div class="kv" style="display:grid;grid-template-columns:76px 1fr;gap:8px 10px;font-size:12.5px">' +
    '<span style="color:var(--text-tertiary)">来源类型</span><span>' + e.label + '</span>' +
    '<span style="color:var(--text-tertiary)">证据深度</span><span>' + e.level + ' <span style="color:var(--warning)">（仅题名）</span></span>' +
    '<span style="color:var(--text-tertiary)">核验状态</span><span>' + e.ver + '</span>' +
    '<span style="color:var(--text-tertiary)">图谱版本</span><span class="mono" style="font-size:11px">' + esc(GRAPH_ID) + '</span></div></div>' +
    '<div class="dt-notice">' + esc(e.caveat) + '</div>' +
    '<div style="display:flex;gap:8px;margin-top:16px">' +
    '<button class="a-go" style="height:34px;font-size:12.5px" data-act="drawer-open-paper">查看论文详情</button>' +
    '<button class="a-btn" style="height:34px" data-act="noop">在 DBLP 打开来源</button></div>';
  $('#drawer').style.display = 'flex';
  $('#mask').style.display = 'block';
  document.body.classList.add('is-drawer');
}

/* ================= 事件分发 ================= */
function doSearch() {
  var qEl = $('#mainQ');
  if (qEl && qEl.value) S.q = qEl.value;
  S.searched = true; S.filtersOpen = false; S.infoOpen = false;
  if (!S.selected) S.selected = MOCK.papers[1].id;
  render();
  if (S.dir === 'A') openDrawer(S.selected);
}
document.addEventListener('click', function (ev) {
  var el = ev.target.closest('[data-act]');
  if (!el) {
    /* 点空白关闭 popover */
    if (S.filtersOpen || S.infoOpen) {
      if (!ev.target.closest('.pop')) { S.filtersOpen = false; S.infoOpen = false; render(); if (S.dir === 'A' && S.searched) openDrawerKeep(); }
    }
    return;
  }
  var act = el.dataset.act;
  if (act === 'dir') { S.dir = el.dataset.dir; S.filtersOpen = false; S.infoOpen = false; closeDrawer(); render(); return; }
  if (act === 'theme') { S.theme = S.theme === 'dark' ? 'light' : 'dark'; render(); return; }
  if (act === 'nav-agent') { toast('本轮原型聚焦「论文库与图谱」，科研助手视图未改动'); return; }
  if (act === 'new-research') { toast('本轮原型聚焦「论文库与图谱」'); return; }
  if (act === 'noop') { return; }
  if (act === 'info-toggle') { S.infoOpen = !S.infoOpen; S.filtersOpen = false; render(); return; }
  if (act === 'filters-toggle') {
    S.filtersOpen = !S.filtersOpen; S.infoOpen = false;
    if (!S.filters) S.filters = { method: '', task: '', dataset: '', author: '', venue: '', year: '', limit: '10' };
    render(); return;
  }
  if (act === 'filters-clear') { S.filters = null; S.filtersOpen = false; render(); return; }
  if (act === 'filter-remove') {
    if (S.filters) { S.filters[el.dataset.k] = ''; }
    render(); return;
  }
  if (act === 'suggest') { S.q = el.dataset.q; doSearch(); return; }
  if (act === 'search-submit') { doSearch(); return; }
  if (act === 'bl-search') { S.searched = true; render(); return; }
  if (act === 'paper-open') {
    var id = el.dataset.id;
    if (S.dir === 'A') { openDrawer(id); } else { S.selected = id; S.tab = 'detail'; render(); }
    return;
  }
  if (act === 'tab') { S.tab = el.dataset.tab; if (S.dir === 'A') { $('#dwTabs').innerHTML = ''; closeDrawer(); openDrawer(S.selected); S.tab = el.dataset.tab; $('#dwTabs').innerHTML = tabHtmlForDrawer(); $('#dwBody').innerHTML = drawerBodyForTab(); } else render(); return; }
  if (act === 'graph-mode') { S.graphMode = el.dataset.mode; render(); return; }
  if (act === 'drawer-close') { closeDrawer(); S.evDrawer = null; render(); return; }
  if (act === 'drawer-open-paper') { closeDrawer(); if (S.dir !== 'A') { S.selected = MOCK.detail.publication.id; render(); } else openDrawer(MOCK.detail.publication.id); return; }
  if (act === 'evidence-open') { openEvidence(); return; }
  if (act === 'g-node') {
    var nid = el.dataset.node;
    var n = MOCK.graph.nodes.filter(function (x) { return x.id === nid; })[0];
    var info = $('#gNodeInfo');
    if (n && info) info.textContent = KIND_ZH[n.kind] + '：' + n.name + ' · 属性来自真实 Neo4j';
    return;
  }
});
function tabHtmlForDrawer() {
  return '<button class="' + (S.tab === 'detail' ? 'is-on' : '') + '" data-act="tab" data-tab="detail">论文详情</button>' +
    '<button class="' + (S.tab === 'graph' ? 'is-on' : '') + '" data-act="tab" data-tab="graph">局部图谱</button>' +
    '<span class="mono" style="margin-left:auto;font-size:10px;color:var(--text-muted);padding-bottom:6px">' + esc(S.selected || '') + '</span>' +
    '<button class="icon-btn" data-act="drawer-close" aria-label="关闭" style="margin-left:8px">' + svgIco(ICO.close) + '</button>';
}
function drawerBodyForTab() {
  return S.tab === 'detail' ? detailBodyHtml(true) :
    '<div class="g-wrap">' + graphSvg(MOCK.graph, 420) + '<div class="g-nodeinfo">9 节点 · 8 关系 · 4 条路径（上限 30）· 真实 Neo4j</div></div>';
}
function openDrawerKeep() { if (S.dir === 'A' && S.searched && S.selected) openDrawer(S.selected); }
document.addEventListener('keydown', function (ev) {
  if (ev.target && /INPUT|SELECT|TEXTAREA/.test(ev.target.tagName)) {
    if (ev.key === 'Enter' && ev.target.id === 'mainQ') { doSearch(); }
    if (ev.key === 'Escape') { ev.target.blur(); }
    return;
  }
  if (ev.key === '1') { S.dir = 'baseline'; closeDrawer(); render(); }
  if (ev.key === '2') { S.dir = 'A'; closeDrawer(); render(); }
  if (ev.key === '3') { S.dir = 'B'; closeDrawer(); render(); }
  if (ev.key === '4') { S.dir = 'C'; closeDrawer(); render(); }
  if (ev.key === 't' || ev.key === 'T') { S.theme = S.theme === 'dark' ? 'light' : 'dark'; render(); }
  if (ev.key === 'Escape') { closeDrawer(); if (S.filtersOpen || S.infoOpen) { S.filtersOpen = false; S.infoOpen = false; render(); } }
});
document.addEventListener('change', function (ev) {
  var t = ev.target;
  if (t.matches('[data-filter]')) {
    if (!S.filters) S.filters = {};
    S.filters[t.dataset.filter] = t.value;
    render();
  }
});
/* 筛选面板输入不打断输入法：input 事件只记值不重绘，blur/change 落盘 */
document.addEventListener('input', function (ev) {
  var t = ev.target;
  if (t.matches && t.matches('[data-filter]') && S.filters) S.filters[t.dataset.filter] = t.value;
  if (t.id === 'mainQ') S.q = t.value;
});

/* ================= harness 钩子 ================= */
window.__proto = {
  setTheme: function (t) { S.theme = t; render(); },
  setDir: function (d) { S.dir = d; S.filtersOpen = false; S.infoOpen = false; closeDrawer(); render(); },
  search: function (q) { S.q = q || 'transformer'; S.searched = true; S.selected = MOCK.papers[1].id; render(); },
  reset: function () { S.searched = false; S.q = ''; S.selected = null; S.filters = null; S.filtersOpen = false; S.infoOpen = false; closeDrawer(); render(); },
  openDrawer: function (id) { S.searched = true; S.selected = id || MOCK.papers[1].id; if (S.dir !== 'A') S.dir = 'A'; render(); openDrawer(S.selected); },
  closeDrawer: closeDrawer,
  toggleFilters: function () { S.filtersOpen = !S.filtersOpen; if (S.filters) S.filters.method = S.filters.method || ''; if (!S.filters) S.filters = { method: '扩散模型', task: '', dataset: '', author: '', venue: '', year: '', limit: '10' }; render(); },
  toggleInfo: function () { S.infoOpen = !S.infoOpen; render(); },
  openEvidence: openEvidence,
  state: function () { return JSON.parse(JSON.stringify({ dir: S.dir, theme: S.theme, searched: S.searched, selected: S.selected, tab: S.tab, filtersOpen: S.filtersOpen, infoOpen: S.infoOpen })); }
};
render();
