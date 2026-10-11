/**
 * SSR 核对：把 ThinkingChain 的三个关键状态渲成静态 HTML + 无头 Chrome 截图。
 *
 *     node tools/thinking_chain_check.mjs
 *
 * 产物：outputs/thinking-chain-check.html / .png（?static=1 已在页内全局禁动画，
 * 避免 headless 截到 CSS 进场动画的中间帧）。分工：元素树结构归
 * chainModel.test.mjs / node --test；"长什么样"归本脚本（SSR → 真实 Chrome）。
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

const tmpBundle = path.join(WEB, 'tools', '_tmp_thinkingchain.bundle.mjs');
execFileSync(process.execPath, [ESBUILD, path.join(WEB, 'src', 'components', 'ThinkingChain.jsx'),
  '--bundle', '--format=esm', '--jsx=automatic',
  '--external:react', '--external:react-dom', '--external:react/jsx-runtime',
  `--outfile=${tmpBundle}`], { stdio: 'inherit' });

const { default: ThinkingChain } = await import(pathToFileURL(tmpBundle).href);
const React = (await import('react')).default;
const { renderToStaticMarkup } = await import('react-dom/server');

const css = readFileSync(path.join(WEB, 'src', 'index.css'), 'utf8');

/* ---- 样例事件（字段形状与 runner.py 实际产出一致） ---- */
const paperItems = [
  { publicationId: 'a', title: 'Denoising Diffusion Probabilistic Models', year: 2020, evidenceLevel: 'title', verificationStatus: 'unverified' },
  { publicationId: 'b', title: 'High-Resolution Image Synthesis with Latent Diffusion Models', year: 2022, evidenceLevel: 'abstract', verificationStatus: 'id_valid' },
  { publicationId: 'c', title: 'Photorealistic Text-to-Image Diffusion Models with Deep Language Understanding', year: 2022, evidenceLevel: 'title', verificationStatus: 'unverified' },
  { publicationId: 'd', title: 'Hierarchical Text-Conditional Image Generation with CLIP Latents', year: 2022, evidenceLevel: 'title', verificationStatus: 'unverified' },
  { publicationId: 'e', title: 'Adding Conditional Control to Text-to-Image Diffusion Models', year: 2023, evidenceLevel: 'title', verificationStatus: 'unverified' },
];
const scopeStep = {
  type: 'tool_step', tool: 'report_graph_scope', label: '查询图谱规模', args: {},
  summary: { status: 'ready', scope: { bibliographyTitles: 20000, candidateAssertions: 21497 } },
  evidenceIds: [], evidenceRefs: [],
};
const searchStep = {
  type: 'tool_step', tool: 'search_papers', label: '检索论文',
  args: { query: 'diffusion model image generation', limit: 25 },
  summary: { papers: 18, applied: { q: 'diffusion model image generation', limit: '25' }, paperItems },
  evidenceIds: ['a', 'b', 'c', 'd', 'e'],
  evidenceRefs: [
    { sourceId: 'a', evidenceLevel: 'title', evidenceText: 'Denoising Diffusion…' },
    { sourceId: 'b', evidenceLevel: 'abstract', evidenceText: 'By leveraging the perceptual…' },
    { sourceId: 'c', evidenceLevel: 'title', evidenceText: 'Photorealistic Text-to-Image…' },
  ],
};
const abstractStep = {
  type: 'tool_step', tool: 'read_paper_abstract', label: '读取摘要',
  args: { publication_id: 'b' },
  summary: { title: 'High-Resolution Image Synthesis with Latent Diffusion Models', available: true },
  evidenceIds: ['b'],
  evidenceRefs: [{ sourceId: 'b', evidenceLevel: 'abstract', evidenceText: 'By leveraging the perceptual…' }],
};
const RETRY = { type: 'run_retry', attempt: 2, reason: '上一轮模型调用没有取得工具结果，自动重试一次' };
const REASONING = '先拆解问题：用户在问图像生成方向的扩散模型，属于「方法 → 任务」检索。\n\n计划：先查图谱规模确认覆盖范围；再用英文关键词检索；对高相关论文补摘要级证据；最后按代表性与影响力挑选 3–5 篇。';

const noop = () => {};
/* ThinkingChain 用了 hooks，必须走 createElement（直接函数调用没有 dispatcher） */
const chain = (props) => React.createElement(ThinkingChain, props);
const states = [
  { name: 'running（流式中：推演打字机 + 已完成工具卡）', el: chain({
      events: [scopeStep, searchStep], reasoning: REASONING, running: true, open: true, onToggle: noop }) },
  { name: 'done-open（完成后保持展开：会话最后一轮的研究侧纪律）', el: chain({
      events: [RETRY, scopeStep, searchStep, abstractStep], reasoning: REASONING, running: false, open: true, onToggle: noop }) },
  { name: 'done-collapsed（NOESIS 行为：完成后收起成胶囊）', el: chain({
      events: [RETRY, scopeStep, searchStep, abstractStep], reasoning: REASONING, running: false, open: false, onToggle: noop }) },
];

const cards = states.map((s) => `<section><h3>${s.name}</h3>${renderToStaticMarkup(s.el)}</section>`).join('\n');

const html = `<!DOCTYPE html>
<html lang="zh" data-static="1">
<head><meta charset="utf-8"><title>thinking-chain-check</title>
<style>html[data-static='1'] *{animation:none !important;transition:none !important;}
body{margin:0;padding:20px;background:var(--bg-secondary,#f7f7f8);}
section{margin-bottom:26px;max-width:720px;}h3{font:600 13px/1.4 system-ui;margin:0 0 6px;color:#525257;}</style>
<style>${css}</style></head>
<body>${cards}
<script>document.documentElement.dataset.ssr='done';</script></body></html>`;

mkdirSync(OUT, { recursive: true });
const htmlPath = path.join(OUT, 'thinking-chain-check.html');
writeFileSync(htmlPath, html);
rmSync(tmpBundle, { force: true });

execFileSync(CHROME, [
  '--headless=new', '--disable-gpu', `--screenshot=${path.join(OUT, 'thinking-chain-check.png')}`,
  '--window-size=780,1650', '--hide-scrollbars',
  `${pathToFileURL(htmlPath).href}?static=1`,
], { stdio: 'inherit' });

// 量化断言：关键 testid / 类名 / 文案都必须出现在 SSR HTML 里
const stepIconCount = (html.match(/data-step-icon="tool"/g) || []).length;
const mustContain = [
  'data-testid="agent-trace"', 'data-testid="agent-trace-toggle"', 'data-testid="agent-steps"',
  'data-testid="agent-step"', 'thinking-status-pill', 'thinking-tool-cluster',
  '深度思考中...', '思考完成', '研究推演', '自动重试（第 2 轮）', '另有 1 条资料',
];
const missing = mustContain.filter((needle) => !html.includes(needle));
if (missing.length) {
  console.error('MISSING:', missing);
  process.exit(1);
}
if (stepIconCount < 4) {
  console.error('tool 步骤条目不足:', stepIconCount);
  process.exit(1);
}
console.log(`OK: all expected markers present (tool steps = ${stepIconCount}); screenshot + html written to outputs/`);
