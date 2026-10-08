/** 临时探针：量 A+B 布局的真实盒子宽度。用完即删。 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const CHROME = 'C:\\Users\\Y7000P\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'http://127.0.0.1:4173';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'nr-probe-'));
const child = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--disable-extensions',
  '--remote-allow-origins=*', `--user-data-dir=${profile}`,
  '--window-size=1440,900', '--remote-debugging-port=9377', 'about:blank',
], { stdio: 'ignore' });

let ws = null;
for (let i = 0; i < 40 && !ws; i++) {
  await sleep(250);
  try {
    const list = await (await fetch('http://127.0.0.1:9377/json/list')).json();
    const page = (list || []).find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
    if (page) ws = page.webSocketDebuggerUrl;
  } catch { /* retry */ }
}
if (!ws) { console.error('NO CDP'); process.exit(2); }

const socket = new WebSocket(ws);
await new Promise((res, rej) => { const t = setTimeout(() => rej(new Error('ws timeout')), 20000); socket.onopen = () => { clearTimeout(t); res(); }; socket.onerror = rej; });

let id = 0;
const pending = new Map();
socket.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { const { resolve, reject } = pending.get(m.id); pending.delete(m.id); m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result); }
};
function send(method, params = {}, useSession = true) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    pending.set(msgId, { resolve, reject });
    const payload = { id: msgId, method, params };
    if (useSession && globalThis.__sid) payload.sessionId = globalThis.__sid;
    socket.send(JSON.stringify(payload));
  });
}

const targets = await send('Target.getTargets', {}, false);
const page = targets.targetInfos.find((t) => t.type === 'page');
const attached = await send('Target.attachToTarget', { targetId: page.targetId, flatten: true }, false);
globalThis.__sid = attached.sessionId;
await send('Page.enable');
await send('Page.navigate', { url: URL });
for (let i = 0; i < 60; i++) {
  await sleep(400);
  const ready = await send('Runtime.evaluate', { expression: `!!document.querySelector('[data-testid="agent-chat"]')`, returnByValue: true }).catch(() => null);
  if (ready?.result?.value === true) break;
}
const expr = `(() => {
  const w = (sel) => { const el = document.querySelector(sel); if (!el) return null;
    const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    return { w: Math.round(r.width), x: Math.round(r.left), display: cs.display, flex: cs.flex, widthCss: cs.width }; };
  return {
    viewport: window.innerWidth,
    app: w('.app'), sb: w('.sb'), main: w('.main'), top: w('.top'),
    row: w('.main > div:nth-of-type(2)'), chatcol: w('.chatcol'), stage: w('.chatcol .stage'),
    col: w('.col'), rail: w('.rail'), railInner: w('.rail-inner'),
    isRail: document.body.classList.contains('is-rail'),
    chatMax: getComputedStyle(document.body).getPropertyValue('--chat-max'),
    docScroll: document.documentElement.scrollWidth + 'x' + document.documentElement.scrollHeight,
    stageScroll: (() => { const s = document.querySelector('.chatcol .stage'); return s ? s.scrollHeight + '/' + s.clientHeight : 'na'; })(),
    composerInEmpty: !!document.querySelector('.col .composer'),
    heroText: (document.querySelector('.hero h1') || {}).textContent || '',
  };
})()`;
const out = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
console.log(JSON.stringify(out.result?.value, null, 2));
try { child.kill(); } catch { /* ignore */ }
fs.promises.rm(profile, { recursive: true, force: true }).catch(() => {});
setTimeout(() => process.exit(0), 300).unref();
