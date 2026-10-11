import os
import shutil
import subprocess
import sys

WEB = "D:/a-open_source/noesis-research/apps/web"
NODE = "C:/Users/Y7000P/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"
ESBUILD = WEB + "/node_modules/.pnpm/esbuild@0.21.5/node_modules/esbuild/bin/esbuild"
CHROME = r"C:\Users\Y7000P\AppData\Local\Google\Chrome\Application\chrome.exe"
SSR = WEB + "/_ssr"

RENDER_JS = r'''
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { TranslatePop } from './TranslatePop.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CSS = fs.readFileSync(path.join(HERE, '..', 'src', 'index.css'), 'utf8');

const noop = () => {};
const base = { popRef: { current: null }, onClose: noop, onRetranslate: noop, onMouseEnter: noop, onMouseLeave: noop };

const pops = [
  // ① 钉住 + 成功（标题）：译文 / 原文 / 术语处理 / 声明 / 操作
  React.createElement(TranslatePop, {
    ...base, kind: 'title', pinned: true, loading: false,
    pos: { top: 70, left: 60 },
    text: 'High-Resolution Image Synthesis with Latent Diffusion Models',
    value: { zh: '基于潜在扩散模型的高分辨率图像合成', cached: false, keptTerms: ['Latent Diffusion'], model: 'qwen3:8b' },
  }),
  // ② 钉住 + 失败（摘要）：503 的文案必须如实
  React.createElement(TranslatePop, {
    ...base, kind: 'abstract', pinned: true, loading: false,
    pos: { top: 400, left: 60 },
    text: 'Deeper neural networks are more difficult to train.',
    value: null,
    error: { code: 'translate_unavailable', message: '上游模型未响应' },
  }),
  // ③ 未钉住的 hover 预览
  React.createElement(TranslatePop, {
    ...base, kind: 'title', pinned: false, loading: false,
    pos: { top: 400, left: 560 },
    text: 'Scalable Diffusion Models with Transformers',
    value: { zh: '可扩展的扩散模型：Transformer 骨干', cached: true, keptTerms: ['Transformer'], model: 'qwen3:8b' },
  }),
];

const body = renderToStaticMarkup(React.createElement('div', null, pops));
const ok = {
  zh: body.includes('基于潜在扩散模型的高分辨率图像合成'),
  keep: body.includes('保留原文：Latent Diffusion'),
  note: body.includes('不是证据'),
  fail: body.includes('翻译服务不可用'),
  hint: body.includes('点击可钉住'),
  mt: body.includes('机器翻译'),
};
console.log('self-check', JSON.stringify(ok));

const page = `<!DOCTYPE html><html lang="zh-CN" data-theme="light"><head><meta charset="utf-8" />
<title>NOESIS Research - 点击翻译浮层核对</title>
<style>${CSS}
body{margin:0;background:var(--bg-secondary);}
.stand{max-width:820px;margin:0 auto;padding:18px 24px;font:13px/1.7 var(--font-body);color:var(--text-secondary);}
.stand b{color:var(--text-primary);}
</style></head><body>
<div class="stand"><b>TranslatePop 真实 SSR 输出</b> · ① 钉住成功（标题）② 钉住失败（503 如实显示）③ hover 预览（带"来自缓存"）。
注意每张浮层都带「机器翻译」标记；钉住态里都有「译文不是证据」声明。</div>
${body}
</body></html>`;

fs.writeFileSync('D:/a-open_source/noesis-research/outputs/translate-pop-check.html', page, 'utf8');
console.log('wrote outputs/translate-pop-check.html');
'''

os.makedirs(SSR, exist_ok=True)
r = subprocess.run(
    [NODE, ESBUILD, "src/components/TranslatePop.jsx", "--bundle", "--format=esm",
     "--outfile=_ssr/TranslatePop.mjs", "--loader:.jsx=jsx", "--jsx=automatic",
     "--external:react", "--external:react-dom", "--external:react/jsx-runtime",
     "--platform=node", "--log-level=warning"],
    cwd=WEB, capture_output=True, text=True, timeout=120,
)
print("esbuild exit", r.returncode, (r.stderr or "")[-300:])
if r.returncode != 0:
    sys.exit(1)

with open(SSR + "/render.mjs", "w", encoding="utf-8") as handle:
    handle.write(RENDER_JS)

r = subprocess.run([NODE, "render.mjs"], cwd=SSR, capture_output=True, text=True, timeout=90)
print("render exit", r.returncode)
print(r.stdout.strip())
print((r.stderr or "")[-400:])

png = "D:/a-open_source/noesis-research/outputs/translate-pop-check.png"
subprocess.run(
    [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
     "--window-size=960,780", "--virtual-time-budget=2500", "--screenshot=" + png,
     "file:///D:/a-open_source/noesis-research/outputs/translate-pop-check.html"],
    capture_output=True, text=True, timeout=90,
)
print("png", os.path.getsize(png) if os.path.isfile(png) else "MISS")

shutil.rmtree(SSR, ignore_errors=True)
print("temp removed:", not os.path.isdir(SSR))
