/**
 * SSR 核对：把 TranslatePop 的三个关键状态渲成静态 HTML + 无头 Chrome 截图。
 *
 *     node tools/explain_pop_check.mjs
 *
 * 产物：outputs/explain-pop-check.html / .png（?static=1 已在页内全局禁动画，
 * 避免 headless 截到 CSS 进场动画的中间帧）。
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const WEB = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')), '..');
const ROOT = path.resolve(WEB, '..', '..');
const OUT = path.join(ROOT, 'outputs');
const ESBUILD = path.join(WEB, 'node_modules', '.pnpm', 'esbuild@0.21.5', 'node_modules', 'esbuild', 'bin', 'esbuild');
const CHROME = String.raw`C:\Users\Y7000P\AppData\Local\Google\Chrome\Application\chrome.exe`;

const tmpBundle = path.join(WEB, 'tools', '_tmp_translatepop.bundle.mjs');
execFileSync(process.execPath, [ESBUILD, path.join(WEB, 'src', 'components', 'TranslatePop.jsx'),
  '--bundle', '--format=esm', '--jsx=automatic',
  '--external:react', '--external:react-dom', '--external:react/jsx-runtime',
  `--outfile=${tmpBundle}`], { stdio: 'inherit' });

const { TranslatePop, ExplainBody } = await import(pathToFileURL(tmpBundle).href);
const { renderToStaticMarkup } = await import('react-dom/server');

const css = readFileSync(path.join(WEB, 'src', 'index.css'), 'utf8');

const EXPLAIN_VALUE = {
  text: 'self-attention',
  kind: 'term',
  style: 'normal',
  category: '概念',
  brief: '让序列中每个位置直接关注所有其他位置并加权聚合信息的机制。',
  detail: '每个位置的表示由全体位置按注意力权重加权求和，权重由相似度归一化而来。\n它摆脱了循环结构，训练可以完全并行。',
  whyItMatters: '它是 Transformer 的核心构件，长程依赖不再随距离衰减。',
  example: '例如“it”在长句中可以同时对照“animal”与“street”来确定指代。',
  cached: false,
  model: 'qwen3:8b',
};
const noop = () => {};
const base = { kind: 'term', text: 'self-attention', pinned: true, popRef: { current: null }, onClose: noop, onTab: noop, onRetranslate: noop, onSimpler: noop, onMouseEnter: noop, onMouseLeave: noop };

const states = [
  { name: 'pinned-translate', pos: { top: 24, left: 40 }, el: TranslatePop({ ...base, pos: { top: 24, left: 40 }, tab: 'tr', style: 'normal', loading: false, error: null, value: { zh: '自注意力', kind: 'text', targetLang: 'zh-Hans', cached: false, keptTerms: [], model: 'm' } }) },
  { name: 'pinned-explain', pos: { top: 320, left: 40 }, el: TranslatePop({ ...base, pos: { top: 320, left: 40 }, tab: 'ex', style: 'normal', loading: false, error: null, value: EXPLAIN_VALUE }) },
  { name: 'explain-fail', pos: { top: 980, left: 40 }, el: TranslatePop({ ...base, pos: { top: 980, left: 40 }, tab: 'ex', style: 'normal', loading: false, error: { code: 'explain_bad_response', message: 'explanation is not the agreed JSON shape' }, value: null }) },
];

const cards = states.map((s) => `<section><h3>${s.name}</h3>${renderToStaticMarkup(s.el)}</section>`).join('\n');

const html = `<!DOCTYPE html>
<html lang="zh" data-static="1">
<head><meta charset="utf-8"><title>explain-pop-check</title>
<style>html[data-static='1'] *{animation:none !important;transition:none !important;}
body{margin:0;padding:20px;background:var(--bg-primary,#f7f7f8);}
section{margin-bottom:26px;}h3{font:600 13px/1.4 system-ui;margin:0 0 6px;}</style>
<style>${css}</style></head>
<body>${cards}
<script>document.documentElement.dataset.ssr='done';</script></body></html>`;

mkdirSync(OUT, { recursive: true });
const htmlPath = path.join(OUT, 'explain-pop-check.html');
writeFileSync(htmlPath, html);
rmSync(tmpBundle, { force: true });

execFileSync(CHROME, [
  '--headless=new', '--disable-gpu', `--screenshot=${path.join(OUT, 'explain-pop-check.png')}`,
  '--window-size=760,1500', '--hide-scrollbars',
  `${pathToFileURL(htmlPath).href}?static=1`,
], { stdio: 'inherit' });

// 量化断言：三个状态的 testid 都必须在 SSR HTML 里出现
const must = ['pop-tab-tr', 'pop-tab-ex', 'translate-zh', 'explain-brief', 'explain-detail', 'explain-why', 'explain-example', 'explain-simpler', 'explain-error', 'explain-category'];
const missing = must.filter((id) => !html.includes(`data-testid="${id}"`));
if (missing.length) {
  console.error('MISSING testids:', missing);
  process.exit(1);
}
console.log('OK: all expected testids present; screenshot + html written to outputs/');
