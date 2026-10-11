/**
 * 思考链对齐原型的无头 CDP 验证（noesis-research 版）
 * 用法：node outputs/_verify_thinking_chain.mjs   →  exit 0 全绿
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const CHROME = process.env.CHROME || 'C:/Users/Y7000P/AppData/Local/Google/Chrome/Application/chrome.exe';
const PAGE = 'file:///D:/a-open_source/noesis-research/outputs/thinking-chain-prototype.html';
const OUT = 'D:/a-open_source/noesis-research/outputs';
const REPORT = OUT + '/_verify_thinking_chain_report.json';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = m => { try { fs.appendFileSync(REPORT.replace(/_report\.json$/, '_run.log'), m + '\n'); } catch {} process.stdout.write(m + '\n'); };

/* ============================ 页面探针 ============================ */
function probe() {
  const out = {};
  const T = (k, f) => { try { out[k] = f(); } catch (e) { out[k] = 'ERR:' + e.message; } };
  const q = s => document.querySelector(s);
  const qa = s => Array.prototype.slice.call(document.querySelectorAll(s));
  const R = el => el.getBoundingClientRect();
  const limited = el => { const r = R(el); return r.height > 0 && r.width > 0; };
  const hasText = el => Array.prototype.slice.call(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());

  T('vw', () => window.innerWidth);
  T('docOverflowX', () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  T('minFont', () => {
    let m = 99;
    qa('#grid *, #rbar *').forEach(el => {
      if (!limited(el) || !hasText(el)) return;
      m = Math.min(m, parseFloat(getComputedStyle(el).fontSize));
    });
    return Math.round(m * 100) / 100;
  });
  T('offscreenText', () => qa('#grid *').filter(el => {
    const r = R(el);
    if (r.width <= 0 || !hasText(el)) return false;
    return r.right > window.innerWidth + 1 || r.left < -1;
  }).map(el => String(el.className || el.tagName).slice(0, 48)).slice(0, 6));
  T('iconMaxSvg', () => {
    const w = qa('svg').map(e => R(e).width).filter(x => x > 0);
    return w.length ? Math.round(Math.max.apply(null, w)) : 0;
  });
  T('clickables', () => qa('#grid button, #rbar button, #grid summary').filter(limited).length);
  T('mainPadBottom', () => parseFloat(getComputedStyle(q('main')).paddingBottom));

  const neo = q('#col-new [data-chain="neo"]');
  T('neo', () => {
    if (!neo) return null;
    const pill = neo.querySelector('.thinking-status-pill');
    const label = neo.querySelector('.thinking-pill-label');
    const countEl = neo.querySelector('.thinking-item-count');
    const body = neo.querySelector('.thinking-area-body');
    const cluster = neo.querySelector('.thinking-tool-cluster');
    const model = q('#col-new .thinking-item-text--model');
    const modelBox = model ? model.closest('.thinking-timeline-item') : null;
    return {
      hasPill: !!pill,
      label: label ? label.textContent.trim() : '',
      count: countEl ? countEl.textContent.trim() : '',
      countN: countEl ? parseInt(countEl.textContent, 10) : -1,
      bodyVisible: !!(body && R(body).height > 0),
      orbs: neo.querySelectorAll('.thinking-orb').length,
      items: neo.querySelectorAll('.thinking-timeline-item').length,
      cards: neo.querySelectorAll('.mcp-tool-activity__item').length,
      loaders: neo.querySelectorAll('.mcp-search-loading').length,
      hasCluster: !!cluster,
      clusterClientH: cluster ? cluster.clientHeight : 0,
      clusterScrollH: cluster ? cluster.scrollHeight : 0,
      clusterScrollTop: cluster ? Math.round(cluster.scrollTop) : 0,
      modelLen: model ? model.textContent.trim().length : 0,
      modelLabel: modelBox ? (modelBox.querySelector('.thinking-item-label') || {}).textContent : '',
      modelIsActive: modelBox ? modelBox.classList.contains('thinking-timeline-item--model') : false,
      labelMono: label ? /Mono|monospace/.test(getComputedStyle(label).fontFamily) : null,
      pillBg: pill ? getComputedStyle(pill).backgroundColor : '',
      pillRadius: pill ? getComputedStyle(pill).borderRadius : '',
      chainH: Math.round(R(neo).height),
      borderW: getComputedStyle(neo).borderTopWidth,
      seamTopShown: !!neo.querySelector('.thinking-tool-seam--top.thinking-tool-seam--show'),
      seamBottomShown: !!neo.querySelector('.thinking-tool-seam--bottom.thinking-tool-seam--show'),
    };
  });

  const base = q('#col-baseline [data-chain="base"]');
  T('base', () => {
    if (!base) return null;
    const sum = base.querySelector('.trace-sum');
    const body = base.querySelector('.trace-body');
    const first = base.querySelector('.tstep .t');
    return {
      hasPill: !!base.querySelector('.thinking-status-pill'),
      hasOrb: !!base.querySelector('.thinking-orb'),
      headerText: sum ? sum.textContent.trim() : '',
      bodyVisible: !!(body && R(body).height > 0),
      steps: base.querySelectorAll('.tstep').length,
      labelMono: first ? /Mono|monospace/.test(getComputedStyle(first).fontFamily) : null,
      traceBorder: getComputedStyle(base).borderTopWidth,
      chainH: Math.round(R(base).height),
    };
  });

  T('refChains', () => {
    const r1 = q('[data-chain="ref1"]'), r2 = q('[data-chain="ref2"]');
    return {
      r1: !!r1, r2: !!r2,
      r1Orbs: r1 ? r1.querySelectorAll('.thinking-orb').length : 0,
      r1BodyVis: r1 ? R(r1.querySelector('.thinking-area-body')).height > 0 : null,
      r2BodyVis: r2 ? R(r2.querySelector('.thinking-area-body')).height > 0 : null,
      r2Label: r2 ? r2.querySelector('.thinking-pill-label').textContent.trim() : '',
    };
  });

  T('contract', () => {
    const tables = qa('#contract-panel table');
    return {
      tables: tables.length,
      mapRows: tables[1] ? tables[1].querySelectorAll('tbody tr').length : -1,
      decs: qa('#contract-panel .dec li').length,
    };
  });
  T('themeColors', () => ({
    docBg: getComputedStyle(document.body).backgroundColor,
    pillBg: q('#col-new .thinking-status-pill') ? getComputedStyle(q('#col-new .thinking-status-pill')).backgroundColor : '',
    titleColor: getComputedStyle(q('.page-title')).color,
  }));
  T('gridCols', () => ({
    layout: q('#grid').getAttribute('data-layout'),
    cols: getComputedStyle(q('.grid2')).gridTemplateColumns,
  }));
  return out;
}
const PROBE_SRC = '(' + probe.toString() + ')()';

/* ============================ 断言骨架 ============================ */
const results = [];
let passed = 0, failed = 0;
function add(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: String(detail) });
  if (ok) passed++; else failed++;
  log((ok ? 'PASS  ' : 'FAIL  ') + name + '   ' + detail);
}

async function main() {
  if (!fs.existsSync(CHROME)) { log('NO CHROME at ' + CHROME); process.exit(2); }
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'proto-'));
  const args = ['--headless=new', '--hide-scrollbars', '--force-device-scale-factor=1',
    '--window-size=1440,900', '--remote-debugging-port=0', '--remote-allow-origins=*',
    '--allow-file-access-from-files', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--user-data-dir=' + profile, PAGE];
  const child = spawn(CHROME, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  const wsUrl = await new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error('no DevTools endpoint in 25s: ' + stderr.slice(-400))), 25000);
    child.stderr.on('data', d => { stderr += d.toString(); const m = /DevTools listening on (ws:\/\/\S+)/.exec(stderr); if (m) { clearTimeout(t); res(m[1]); } });
    child.on('exit', c => { clearTimeout(t); rej(new Error('chrome exited ' + c)); });
  });
  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error('WS 超时 20s')), 20000);
    ws.onopen = () => { clearTimeout(t); res(); };
    ws.onerror = e => { clearTimeout(t); rej(e); };
  });

  let id = 0; const pending = new Map(); const jsErrors = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.method === 'Runtime.exceptionThrown') jsErrors.push(JSON.stringify(m.params.exceptionDetails).slice(0, 240));
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error')
      jsErrors.push('console.error: ' + (m.params.args || []).map(a => a.value).join(' ').slice(0, 240));
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  };
  const send = (method, params, sessionId) => new Promise((res, rej) => {
    const mid = ++id;
    const t = setTimeout(() => { pending.delete(mid); rej(new Error('timeout ' + method)); }, 25000);
    pending.set(mid, m => { clearTimeout(t); res(m); });
    ws.send(JSON.stringify(Object.assign({ id: mid, method, params: params || {} }, sessionId ? { sessionId } : {})));
  });

  const targets = (await send('Target.getTargets')).result.targetInfos;
  const page = targets.find(t => t.type === 'page' && t.url === PAGE);
  if (!page) { log('no page target: ' + JSON.stringify(targets.map(t => t.url))); process.exit(3); }
  const sid = (await send('Target.attachToTarget', { targetId: page.targetId, flatten: true })).result.sessionId;
  await send('Runtime.enable', {}, sid);
  await send('Page.enable', {}, sid);

  const ev = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true }, sid);
    if (r.result && r.result.exceptionDetails) throw new Error('eval exception: ' + JSON.stringify(r.result.exceptionDetails).slice(0, 300));
    return r.result && r.result.result ? r.result.result.value : undefined;
  };
  const shot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' }, sid);
    const d = r.result && r.result.data;
    if (!d) { log('SHOT FAIL ' + name + ' ' + JSON.stringify(r.result || r).slice(0, 200)); return; }
    const p = path.join(OUT, name + '.png');
    fs.writeFileSync(p, Buffer.from(d, 'base64'));
    log('SHOT ' + name + ' ' + fs.statSync(p).size + 'B');
  };
  /* 真实点击（走完整事件传播链） */
  await ev('window.__click = function(sel){ var el=document.querySelector(sel); if(!el) return "MISS"; el.dispatchEvent(new MouseEvent("click",{bubbles:true,cancelable:true,view:window})); return "ok"; };');

  for (let i = 0; i < 60; i++) {
    const s = await ev('document.readyState + "|" + (typeof window.__proto) + "|" + (typeof window.__proto.setTheme)');
    if (s === 'complete|object|function') break;
    await sleep(400);
  }
  const ready = await ev('document.readyState + "|" + (typeof window.__proto) + "|" + (typeof window.__proto.setTheme)');
  if (!/complete\|object\|function/.test(String(ready))) { log('page not ready: ' + ready); process.exit(4); }

  const data = {};
  const P = async (tag) => { const m = await ev(PROBE_SRC); data[tag] = m; return m; };

  /* ---------- SC1：light · B · done · auto ---------- */
  await ev('window.__proto.setStatic(false); window.__proto.setTheme("light"); window.__proto.setLayout("both"); window.__proto.setCopy("noesis"); window.__proto.setCollapse("auto"); window.__proto.setDir("B"); window.__proto.setRun("done")');
  await sleep(500);
  let m = await P('sc1-light-B-done');
  add('[SC1] 新链：状态胶囊存在', m.neo && m.neo.hasPill === true, JSON.stringify(m.neo && m.neo.hasPill));
  add('[SC1] 新链：完成文案=思考完成', m.neo.label === '思考完成', m.neo.label);
  add('[SC1] 新链：计数=N 项且=条目数', m.neo.countN === m.neo.items && m.neo.countN === 6, 'count=' + m.neo.count + ' items=' + m.neo.items);
  add('[SC1] 新链：完成后自动收起', m.neo.bodyVisible === false, 'bodyVisible=' + m.neo.bodyVisible);
  add('[SC1] 新链：工具簇 5 张明细卡', m.neo.hasCluster && m.neo.cards === 5 && m.neo.loaders === 0, 'cards=' + m.neo.cards);
  add('[SC1] 新链：胶囊圆角 999px（计算值）', m.neo.pillRadius === '999px', m.neo.pillRadius);
  add('[SC1] 新链：胶囊底色=NOESIS --pill-bg 浅值', m.neo.pillBg === 'rgb(241, 241, 243)', m.neo.pillBg);
  add('[SC1] 新链：思考链无框（区别于现状卡片）', m.neo.borderW === '0px', 'border=' + m.neo.borderW);
  add('[SC1] 现状：无胶囊/无状态球（问题存在）', m.base.hasPill === false && m.base.hasOrb === false, 'pill=' + m.base.hasPill + ' orb=' + m.base.hasOrb);
  add('[SC1] 现状：6 步且默认展开（最后一轮）', m.base.steps === 6 && m.base.bodyVisible === true, 'steps=' + m.base.steps + ' visible=' + m.base.bodyVisible);
  add('[SC1] 现状：步骤标签为等宽字体', m.base.labelMono === true, 'mono=' + m.base.labelMono);
  add('[SC1] 新链：胶囊文字非等宽', m.neo.labelMono === false, 'mono=' + m.neo.labelMono);
  add('[SC1] §1 标杆：两条链齐、运行中有球、完成态收起', m.refChains.r1 && m.refChains.r2 && m.refChains.r1Orbs > 0 && m.refChains.r1BodyVis === true && m.refChains.r2BodyVis === false && m.refChains.r2Label === '思考完成', JSON.stringify(m.refChains));
  add('[SC1] §3 契约：2 张表 / 映射 10 行 / 3 决策', m.contract.tables === 2 && m.contract.mapRows === 10 && m.contract.decs === 3, JSON.stringify(m.contract));
  add('[SC1] 无横向溢出', m.docOverflowX <= 1, 'over=' + m.docOverflowX);
  add('[SC1] 最小字号 >= 11px', m.minFont >= 11, 'min=' + m.minFont);
  add('[SC1] 无文字越界', Array.isArray(m.offscreenText) && m.offscreenText.length === 0, JSON.stringify(m.offscreenText));
  add('[SC1] 图标 svg <= 24px', m.iconMaxSvg <= 24, 'max=' + m.iconMaxSvg);
  add('[SC1] 可点元素 >= 10', m.clickables >= 10, 'n=' + m.clickables);
  add('[SC1] 底部让位余量 >= 100px', m.mainPadBottom >= 100, 'pad=' + m.mainPadBottom);
  data.colorsLight = m.themeColors;

  /* ---------- SC2：真实点击审计 ---------- */
  let r1 = await ev('window.__click("#col-new .thinking-area-header")'); await sleep(150);
  m = await P('sc2-click-expand'); add('[SC2] 点胶囊 -> 展开', r1 === 'ok' && m.neo.bodyVisible === true, 'res=' + r1 + ' vis=' + m.neo.bodyVisible);
  r1 = await ev('window.__click("#col-new .thinking-area-header")'); await sleep(150);
  m = await P('sc2-click-collapse'); add('[SC2] 再点 -> 收起', r1 === 'ok' && m.neo.bodyVisible === false, 'res=' + r1 + ' vis=' + m.neo.bodyVisible);
  r1 = await ev('window.__click("button[data-seg=\\"copy\\"][data-val=\\"research\\"]")'); await sleep(150);
  m = await P('sc2-copy-research'); add('[SC2] 文案切研究口径 -> 思考完成=研究完成', r1 === 'ok' && m.neo.label === '研究完成', 'label=' + m.neo.label);
  r1 = await ev('window.__click("button[data-seg=\\"run\\"][data-val=\\"streaming\\"]")'); await sleep(200);
  m = await P('sc2-streaming'); add('[SC2] 切运行中 -> 深度研究中…/点阵球/展开/1 张进行中卡', r1 === 'ok' && m.neo.label === '深度研究中…' && m.neo.orbs > 0 && m.neo.bodyVisible === true && m.neo.loaders === 1, JSON.stringify({ label: m.neo.label, orbs: m.neo.orbs, vis: m.neo.bodyVisible, loaders: m.neo.loaders }));
  add('[SC2] 运行中计数=5 项=条目数', m.neo.countN === 5 && m.neo.countN === m.neo.items, 'count=' + m.neo.count + ' items=' + m.neo.items);
  add('[SC2] 工具簇自动跟随到底（上 seam 亮 / 下 seam 灭）', m.neo.clusterScrollTop > 0 && m.neo.seamTopShown === true && m.neo.seamBottomShown === false, JSON.stringify({ top: m.neo.clusterScrollTop, st: m.neo.seamTopShown, sb: m.neo.seamBottomShown, h: m.neo.clusterClientH + '/' + m.neo.clusterScrollH }));
  await ev('window.__click("button[data-seg=\\"collapse\\"][data-val=\\"keep\\"]")'); await sleep(120);
  await ev('window.__click("button[data-seg=\\"run\\"][data-val=\\"done\\"]")'); await sleep(200);
  m = await P('sc2-done-keep'); add('[SC2] 完成后保持展开（keep）', m.neo.bodyVisible === true && m.neo.label === '研究完成', 'vis=' + m.neo.bodyVisible + ' label=' + m.neo.label);
  await ev('window.__click("button[data-seg=\\"copy\\"][data-val=\\"noesis\\"]")'); await sleep(120);
  await ev('window.__click("button[data-seg=\\"collapse\\"][data-val=\\"auto\\"]")'); await sleep(120);

  /* ---------- SC3：C 方向 · 运行中 · static ---------- */
  await ev('window.__proto.setStatic(true); window.__proto.setDir("C"); window.__proto.setRun("streaming")'); await sleep(300);
  m = await P('sc3-C-streaming');
  add('[SC3] C：模型推演条目存在且为 model 类', m.neo.modelLen >= 100 && m.neo.modelIsActive === true, 'len=' + m.neo.modelLen);
  add('[SC3] C：推演标签=研究推演', String(m.neo.modelLabel).indexOf('研究推演') >= 0, m.neo.modelLabel);
  add('[SC3] C：计数=6 项（含推演+重试+4 工具）', m.neo.countN === 6 && m.neo.countN === m.neo.items, 'count=' + m.neo.count + ' items=' + m.neo.items);

  /* ---------- SC4：dark ---------- */
  await ev('window.__proto.setTheme("dark")'); await sleep(300);
  m = await P('sc4-dark');
  const cL = data.colorsLight, cD = m.themeColors;
  add('[SC4] 暗色：页面底色与浅色不同', cD.docBg !== cL.docBg, cL.docBg + ' -> ' + cD.docBg);
  add('[SC4] 暗色：胶囊底色与浅色不同', cD.pillBg !== cL.pillBg, cL.pillBg + ' -> ' + cD.pillBg);
  add('[SC4] 暗色：正文颜色与浅色不同', cD.titleColor !== cL.titleColor, cL.titleColor + ' -> ' + cD.titleColor);
  add('[SC4] 暗色无横向溢出', m.docOverflowX <= 1, 'over=' + m.docOverflowX);
  data.colorsDark = cD;

  /* ---------- SC5：宽窗口复检 ---------- */
  for (const w of [1600, 1760]) {
    await send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false }, sid);
    await sleep(500);
    m = await P('sc5-' + w);
    add('[' + w + 'px] 无横向溢出', m.docOverflowX <= 1, 'over=' + m.docOverflowX);
    add('[' + w + 'px] 并排仍为两列', String(m.gridCols.cols).split(' ').length === 2, m.gridCols.cols);
  }
  await send('Emulation.clearDeviceMetricsOverride', {}, sid); await sleep(400);

  /* ---------- 截图（static 冻结动画，确定性帧） ---------- */
  await ev('window.__proto.setStatic(true); window.__proto.setTheme("light"); window.__proto.setLayout("both"); window.__proto.setCopy("noesis"); window.__proto.setCollapse("auto"); window.__proto.setDir("B"); window.__proto.setRun("done"); window.scrollTo(0,0)');
  await sleep(400);
  await shot('thinking-chain-ref-noesis-light');
  await ev('document.getElementById("col-new").scrollIntoView({block:"start"})'); await sleep(300);
  await shot('thinking-chain-B-done-collapsed-light');
  await ev('window.__proto.setCollapse("keep")'); await sleep(300);
  await shot('thinking-chain-B-done-expanded-light');
  await ev('window.__proto.setRun("streaming")'); await sleep(300);
  await shot('thinking-chain-B-streaming-light');
  await ev('window.__proto.setTheme("dark")'); await sleep(300);
  await shot('thinking-chain-B-streaming-dark');
  await ev('window.__proto.setTheme("light"); window.__proto.setDir("C"); window.__proto.setRun("streaming")'); await sleep(300);
  await shot('thinking-chain-C-streaming-light');
  await ev('window.__proto.setDir("A"); window.__proto.setRun("done"); window.__proto.setCollapse("keep")'); await sleep(300);
  await shot('thinking-chain-A-done-light');

  add('全过程无 JS 运行时报错', jsErrors.length === 0, jsErrors.join(' || ') || 'none');

  fs.writeFileSync(REPORT, JSON.stringify({ passed, failed, results, data, jsErrors }, null, 2), 'utf8');
  log('\n==== ' + passed + ' passed / ' + failed + ' failed ====');
  try { ws.close(); } catch {}
  child.kill('SIGKILL');
  process.exit(failed ? 1 : 0);
}

main().catch(e => { log('FATAL ' + (e && e.stack || e)); process.exit(9); });
