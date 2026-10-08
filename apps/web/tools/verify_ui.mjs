/**
 * 研究工作区的无头浏览器验收（真实 Chrome + CDP，不用 puppeteer）。
 *
 * 覆盖：默认进入科研助手、证据链默认收起且可开关、检索/详情/图谱数据侧、
 * agent 真实运行（工具步骤、回答、引用核查）、证据抽屉、控制台无报错。
 *
 * 用法（需要 API 在 8100、Agent 在 8101、前端 preview 在 4173）：
 *     node tools/verify_ui.mjs [--url http://127.0.0.1:4173] [--shot out.png]
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const CHROME =
  process.env.CHROME_PATH || 'C:\\Users\\Y7000P\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe';

const argv = process.argv.slice(2);
const argValue = (flag, fallback) => {
  const index = argv.indexOf(flag);
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback;
};
const TARGET_URL = argValue('--url', 'http://127.0.0.1:4173');
const SHOT = argValue('--shot', '');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const results = [];
function add(name, ok, detail = '') {
  results.push({ name, ok: Boolean(ok), detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  —— ' + detail : ''}`);
}

function launchChrome() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'nr-web-verify-'));
  return new Promise((resolve, reject) => {
    let settled = false;
    const tryPort = (attempt) => {
      if (attempt >= 6) {
        if (!settled) {
          settled = true;
          reject(new Error('无法连接到 Chrome CDP（端口都被占用或 Chrome 未启动）'));
        }
        return;
      }
      const port = 9310 + Math.floor(Math.random() * 480);
      const child = spawn(
        CHROME,
        [
          '--headless=new', '--disable-gpu', '--hide-scrollbars',
          '--no-first-run', '--no-default-browser-check', '--disable-extensions',
          '--remote-allow-origins=*', '--force-device-scale-factor=1',
          `--user-data-dir=${profile}`, '--window-size=1440,1000',
          `--remote-debugging-port=${port}`, 'about:blank',
        ],
        { stdio: 'ignore' },
      );

      (async () => {
        for (let i = 0; i < 32; i += 1) {
          await sleep(250);
          try {
            const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
            // 必须校验返回的确实是 CDP，而不是恰好占用该端口的别的服务
            const page = (list || []).find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
            if (page) {
              if (!settled) {
                settled = true;
                resolve({ child, profile, wsUrl: page.webSocketDebuggerUrl });
              }
              return;
            }
          } catch { /* 还没起来 */ }
        }
        try { child.kill(); } catch { /* ignore */ }
        tryPort(attempt + 1);
      })();
    };
    tryPort(0);
  });
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    const timer = setTimeout(() => reject(new Error('CDP WebSocket 连接超时 20s')), 20000);
    ws.onopen = () => { clearTimeout(timer); resolve(ws); };
    ws.onerror = (event) => {
      clearTimeout(timer);
      reject(new Error(`CDP WebSocket 错误：${event?.message || 'unknown'}`));
    };
  });
}

class Session {
  constructor(ws) {
    this.ws = ws;
    this.sessionId = null;
    this.nextId = 1;
    this.pending = new Map();
    this.consoleErrors = [];
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result);
        return;
      }
      if (message.method === 'Runtime.consoleAPICalled' && message.params?.type === 'error') {
        this.consoleErrors.push(message.params.args?.map((a) => a.value ?? a.description).join(' '));
      }
      if (message.method === 'Runtime.exceptionThrown') {
        this.consoleErrors.push(message.params?.exceptionDetails?.text || 'uncaught exception');
      }
    };
  }

  send(method, params = {}, useSession = true) {
    const id = this.nextId++;
    const payload = { id, method, params };
    if (useSession && this.sessionId) payload.sessionId = this.sessionId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify(payload));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP 超时：${method}`));
        }
      }, 60000);
    });
  }

  async eval(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true,
    });
    if (result.exceptionDetails) {
      throw new Error(`页面内异常：${result.exceptionDetails.text} ${result.exceptionDetails.exception?.description || ''}`);
    }
    return result.result?.value;
  }

  async waitFor(expression, { timeout = 20000, interval = 250 } = {}) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const value = await this.eval(expression);
      if (value) return value;
      await sleep(interval);
    }
    throw new Error(`等待超时：${expression}`);
  }
}

const PROBE = `(() => {
  const q = (sel) => document.querySelector(sel);
  const qa = (sel) => Array.from(document.querySelectorAll(sel));
  const visible = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.height > 0 && r.width > 0; };
  const chips = qa('[data-testid="evidence-chip"]');
  const viewTab = qa('[data-testid="view-tab"]').find((el) => el.getAttribute('data-active') === 'true');
  const railToggle = q('[data-testid="rail-toggle"]');
  const cited = qa('[data-testid="cited-id"]');
  return {
    title: document.title,
    activeView: viewTab?.getAttribute('data-view') || '',
    agentChatPresent: Boolean(q('[data-testid="agent-chat"]')),
    exampleCount: qa('[data-testid="prompt-card"]').length,
    railState: railToggle?.getAttribute('data-rail') || '',
    railCount: q('[data-testid="rail-count"]')?.textContent || '',
    railCards: qa('[data-testid="rail-card"]').length,
    railEmptyVisible: visible(q('[data-testid="rail-empty"]')),
    agentStepCount: qa('[data-testid="agent-step"]').length,
    agentStepIcons: qa('[data-testid="agent-step"]').map((el) => el.getAttribute('data-step-icon')),
    agentAnswer: q('[data-testid="agent-answer"]')?.textContent || '',
    citationPasses: q('[data-testid="citation-verdict"]')?.getAttribute('data-passes') || '',
    citationText: q('[data-testid="citation-verdict"]')?.textContent || '',
    citedChips: cited.length,
    citedIds: cited.map((el) => el.getAttribute('data-cited-id')),
    titleOnlyWarning: Boolean(q('[data-testid="title-only-warning"]')),
    agentError: q('[data-testid="agent-error"]')?.textContent || '',
    graphHeader: q('[data-testid="graph-header"]')?.textContent || '',
    pinState: q('[data-testid="pin-state"]')?.textContent || '',
    boundary: Boolean(q('[data-testid="boundary-notice"]')),
    hasSearchForm: Boolean(q('[data-testid="search-form"]')),
    searchSummary: q('[data-testid="search-summary"]')?.textContent || '',
    idFull: q('.lib-idfull')?.textContent || '',
    infoPopoverText: q('[data-testid="info-popover"]')?.textContent || '',
    paperDrawer: Boolean(q('[data-testid="paper-drawer"]')),
    paperDrawerW: Math.round(q('[data-testid="paper-drawer"]')?.getBoundingClientRect().width || 0),
    activeRowCount: qa('[data-testid="paper-item"][aria-current="true"]').length,
    paperCount: qa('[data-testid="paper-item"]').length,
    firstPaperId: q('[data-testid="paper-item"]')?.getAttribute('data-publication-id') || '',
    evidenceChips: chips.length,
    citableChips: chips.filter((el) => el.getAttribute('data-citable') === 'true').length,
    firstSourceId: chips.find((el) => el.getAttribute('data-source-id'))?.getAttribute('data-source-id') || '',
    detailId: q('[data-testid="detail-id"]')?.textContent || '',
    detailTitle: q('[data-testid="detail-title"]')?.textContent || '',
    assertionStatuses: qa('[data-testid="assertion-item"]').map((el) => el.getAttribute('data-status')),
    graphNodes: qa('[data-testid="graph-node"]').length,
    graphCanvas: Boolean(q('[data-testid="graph-panel"] canvas')),
    graphEdges: qa('[data-testid="graph-edge"]').length,
    drawerPresent: Boolean(q('[data-testid="evidence-drawer"]')),
    drawerFields: q('[data-testid="drawer-fields"]')?.textContent || '',
    drawerText: q('[data-testid="evidence-drawer"]')?.textContent || '',
    errorBanner: q('[data-testid="error-banner"]')?.textContent || '',
    rootOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    viewport: window.innerWidth,
    // 布局几何：主列必须占满侧栏以外的宽度，输入容器要在主列内居中
    // （.main 规则曾丢失导致整页左挤——这类回归必须有几何断言看着）
    sbW: Math.round(q('.sidebar')?.getBoundingClientRect().width || 0),
    mainW: Math.round(q('.main')?.getBoundingClientRect().width || 0),
    mainX: Math.round(q('.main')?.getBoundingClientRect().left || -1),
    containerX: Math.round(q('[data-testid="composer"]')?.getBoundingClientRect().left || -1),
    containerW: Math.round(q('[data-testid="composer"]')?.getBoundingClientRect().width || 0),
    composerInEmpty: visible(q('[data-testid="composer"]')),
    welcomeGlyph: Boolean(q('.welcome-glyph svg')),
    promptCount: qa('[data-testid="prompt-card"]').length,
    // SVG 无尺寸规则会退回 300×150 固有尺寸（踩过两次）——图标一律 <= 24px；
    // 两个按设计放行：空态螺旋标（48，同 NOESIS）与建议卡右下角水印（5.375rem 装饰件）
    maxSvgW: Math.max(0, ...qa('svg').filter(visible)
      .filter((el) => !el.closest('.prompt-card-wm') && !el.closest('.welcome-glyph'))
      .map((el) => el.getBoundingClientRect().width)),
  };
})()`;

async function main() {
  if (!fs.existsSync(CHROME)) throw new Error(`找不到 Chrome：${CHROME}`);
  const { child, profile, wsUrl } = await launchChrome();
  const ws = await connect(wsUrl);
  // 一个 WebSocket 只配一个 Session：Target.* 用浏览器级（不带 sessionId），
  // 拿到 sessionId 后原地赋值。建两个实例会互相覆盖 onmessage（踩过）。
  const session = new Session(ws);
  try {
    const { targetInfos } = await session.send('Target.getTargets', {}, false);
    const pageInfo = targetInfos.find((t) => t.type === 'page');
    const attached = await session.send(
      'Target.attachToTarget',
      { targetId: pageInfo.targetId, flatten: true },
      false,
    );
    session.sessionId = attached.sessionId;
    await session.send('Page.enable');
    await session.send('Runtime.enable');

    await session.send('Page.navigate', { url: TARGET_URL });
    await session.waitFor(`document.readyState === 'complete'`, { timeout: 30000 });

    // ---- 主界面：科研助手 + 证据链默认收起 ----
    await session.waitFor(`!!document.querySelector('[data-testid="agent-chat"]')`);
    let probe = await session.eval(PROBE);
    add('默认进入科研助手', probe.activeView === 'agent' && probe.agentChatPresent, `view=${probe.activeView}`);
    add('空态建议卡可一键发问', probe.promptCount > 0, `${probe.promptCount} 个`);
    add('证据链默认收起', probe.railState === 'closed', `rail=${probe.railState}`);
    add('证据链开关带计数', probe.railCount !== '', probe.railCount);
    add('页面无横向溢出', probe.rootOverflow <= 1, `溢出 ${probe.rootOverflow}px`);
    add(
      '主列占满侧栏以外宽度',
      Math.abs(probe.sbW + probe.mainW - probe.viewport) <= 2,
      `sb=${probe.sbW} main=${probe.mainW} viewport=${probe.viewport}`,
    );
    add('提问前有输入区', probe.composerInEmpty === true, '');
    const containerCenter = probe.containerX + probe.containerW / 2;
    const mainCenter = probe.mainX + probe.mainW / 2;
    add(
      '输入容器在主列内居中',
      Math.abs(containerCenter - mainCenter) <= 8 && probe.containerW > 0,
      `容器中心偏移 ${Math.round(containerCenter - mainCenter)}px`,
    );
    add('空态含螺旋标与建议卡', probe.welcomeGlyph === true && probe.promptCount >= 4,
      `prompts=${probe.promptCount}`);
    add('全部图标 <= 24px', probe.maxSvgW <= 24, `最大 ${Math.round(probe.maxSvgW)}px`);

    // 开关能用：此时还没有运行，打开应看到空态说明
    await session.eval(`(() => { document.querySelector('[data-testid="rail-toggle"]').click(); return true; })()`);
    await session.waitFor(`document.querySelector('[data-testid="rail-toggle"]').getAttribute('data-rail') === 'open'`, { timeout: 8000 });
    probe = await session.eval(PROBE);
    add('证据链可打开', probe.railState === 'open', `rail=${probe.railState}`);
    await session.eval(`(() => { document.querySelector('[data-testid="rail-toggle"]').click(); return true; })()`);
    await session.waitFor(`document.querySelector('[data-testid="rail-toggle"]').getAttribute('data-rail') === 'closed'`, { timeout: 8000 });

    // ---- 论文库与图谱（数据侧）----
    await session.eval(`(() => {
      Array.from(document.querySelectorAll('[data-testid="view-tab"]'))
        .find((el) => el.getAttribute('data-view') === 'library').click();
      return true;
    })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="search-form"]')`);
    await session.waitFor(`!!document.querySelector('[data-testid="graph-header"]')`, { timeout: 25000 });
    // 瘦身头部：graphId / 版本锁定 / 边界声明收进 ⓘ 弹层 —— 点开才算数
    await session.eval(`(() => { document.querySelector('[data-testid="info-toggle"]').click(); return true; })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="info-popover"]')`, { timeout: 8000 });
    probe = await session.eval(PROBE);
    add('ⓘ 弹层显示完整 graphId', probe.idFull.length > 10, probe.idFull);
    add('ⓘ 弹层显示版本锁定状态', /已锁定|未锁定/.test(probe.pinState), probe.pinState.trim());
    add('ⓘ 弹层显示书目规模', /20,000|20000/.test(probe.infoPopoverText), probe.infoPopoverText.slice(0, 60));
    add('ⓘ 弹层含边界说明', probe.boundary === true);
    await session.eval(`(() => { document.querySelector('[data-testid="info-toggle"]').click(); return true; })()`);
    await session.waitFor(`!document.querySelector('[data-testid="info-popover"]')`, { timeout: 8000 });
    add('页面无错误横幅', probe.errorBanner === '', probe.errorBanner.slice(0, 80));

    await session.eval(`(() => {
      const input = document.querySelector('input[name="q"]');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, 'transformer');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('[data-testid="search-submit"]').click();
      return true;
    })()`);
    await session.waitFor(`document.querySelectorAll('[data-testid="paper-item"]').length > 0`, { timeout: 25000 });
    probe = await session.eval(PROBE);
    add('检索返回真实论文', probe.paperCount > 0, `${probe.paperCount} 条`);
    add('结果摘要含真实来源', /source=/.test(probe.searchSummary), probe.searchSummary.trim().slice(0, 100));
    add(
      '每条结果都带可点击证据',
      probe.evidenceChips >= probe.paperCount && probe.citableChips === probe.evidenceChips,
      `chips=${probe.evidenceChips} citable=${probe.citableChips} papers=${probe.paperCount}`,
    );

    const firstId = probe.firstPaperId;
    await session.eval(`(() => { document.querySelector('[data-testid="paper-item"]').click(); return true; })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="detail-panel"]')`, { timeout: 25000 });
    probe = await session.eval(PROBE);
    add('论文抽屉打开（480px）', probe.paperDrawer === true && Math.abs(probe.paperDrawerW - 480) <= 2, `w=${probe.paperDrawerW}`);
    add('详情面板打开且是同一篇', probe.detailId === firstId, `detail=${probe.detailId} list=${firstId}`);
    const allCandidate = probe.assertionStatuses.every((s) => s === 'candidate');
    add(
      '断言在 UI 上恒为候选',
      probe.assertionStatuses.length === 0 ? true : allCandidate,
      `statuses=${probe.assertionStatuses.join(',') || '(无)'}`,
    );

    // 切到局部图谱
    await session.eval(`(() => {
      Array.from(document.querySelectorAll('[data-testid="tab"]')).find((el) => el.getAttribute('data-tab') === 'graph').click();
      return true;
    })()`);
    await session.waitFor(`document.querySelectorAll('[data-testid="graph-node"]').length > 0`, { timeout: 25000 });
    probe = await session.eval(PROBE);
    add('局部图谱画出节点', probe.graphNodes > 0, `nodes=${probe.graphNodes} edges=${probe.graphEdges}`);
    add('图谱画布为可交互 canvas', probe.graphCanvas === true, '');

    // 关论文抽屉：不能留下幽灵选中行
    await session.eval(`(() => { document.querySelector('[data-testid="paper-drawer-close"]').click(); return true; })()`);
    await session.waitFor(`!document.querySelector('[data-testid="paper-drawer"]')`, { timeout: 8000 });
    probe = await session.eval(PROBE);
    add('关闭抽屉后无幽灵选中行', probe.activeRowCount === 0, `active=${probe.activeRowCount}`);

    // ---- 证据抽屉（从论文列表的证据徽标进入）----
    await session.eval(`(() => {
      const chip = Array.from(document.querySelectorAll('[data-testid="evidence-chip"]'))
        .find((el) => el.getAttribute('data-clickable') === 'true');
      if (!chip) throw new Error('没有可点击的证据徽标');
      chip.click();
      return true;
    })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="evidence-drawer"]')`, { timeout: 15000 });
    probe = await session.eval(PROBE);
    add('证据抽屉可以打开', probe.drawerPresent === true);
    add('抽屉里有来源 id 与深度', probe.drawerText.includes(probe.firstSourceId) && /题名|摘要|全文/.test(probe.drawerFields), probe.firstSourceId);
    add('抽屉把「不能证明什么」写清楚', /不能证明/.test(probe.drawerText), '');
    await session.eval(`(() => { document.querySelector('[data-testid="drawer-open-paper"]').click(); return true; })()`);
    await session.waitFor(`!document.querySelector('[data-testid="evidence-drawer"]')`, { timeout: 15000 });
    await session.waitFor(`!!document.querySelector('[data-testid="detail-panel"]')`, { timeout: 25000 });
    probe = await session.eval(PROBE);
    add('抽屉能跳到对应论文详情', probe.detailId.length > 0 && probe.detailId === probe.firstSourceId, `detail=${probe.detailId}`);

    // ---- 主界面：让 agent 真的跑一次（模型偶发"浅回答"时重试一次，两次都失败才算挂）----
    await session.eval(`(() => {
      Array.from(document.querySelectorAll('[data-testid="view-tab"]'))
        .find((el) => el.getAttribute('data-view') === 'agent').click();
      return true;
    })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="agent-chat"]')`);

    let passed = false;
    let attempt = 0;
    let lastProbe = null;
    const QUESTIONS = [
      '有哪些关于 transformer 的论文？',
      '图神经网络用在异常检测的有哪些？',
      '2025 年 CVPR 的扩散 transformer',
    ];
    while (attempt < QUESTIONS.length && !passed) {
      const question = QUESTIONS[attempt];
      await session.eval(`(() => {
        const input = document.querySelector('[data-testid="agent-input"]');
        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        setter.call(input, ${JSON.stringify(question)});
        input.dispatchEvent(new Event('input', { bubbles: true }));
        document.querySelector('[data-testid="agent-submit"]').click();
        return true;
      })()`);
      await session.waitFor(
        `document.querySelectorAll('[data-testid="agent-step"]').length > 0 || !!document.querySelector('[data-testid="citation-verdict"]')`,
        { timeout: 240000 },
      );
      await session.waitFor(`!!document.querySelector('[data-testid="citation-verdict"]')`, { timeout: 420000 });
      probe = await session.eval(PROBE);
      lastProbe = probe;
      passed =
        probe.citationPasses === 'true' &&
        probe.agentStepIcons.includes('tool') &&
        !probe.agentStepIcons.includes('error');
      attempt += 1;
      // 逐次详情：步数/图标/回答开头/引用结论 —— DeepSeek 偶发"并行工具调用不被
      // 执行、模型只交 31 字旁白"时，能看清它到底说了什么（闸门如实判失败）
      console.log(
        `  （尝试 ${attempt}：steps=${probe.agentStepCount} icons=[${probe.agentStepIcons.join(',')}] ` +
          `answer=${probe.agentAnswer.length}字 "${probe.agentAnswer.slice(0, 60)}" ` +
          `passes=${probe.citationPasses} cited=${probe.citedChips} error=${probe.agentError.slice(0, 40) || '无'}）`,
      );
      if (!passed && attempt < QUESTIONS.length) {
        await session.eval(`(() => { document.querySelector('[data-testid="new-research"]').click(); return true; })()`);
        await session.waitFor(`!!document.querySelector('[data-testid="agent-intro"]')`, { timeout: 15000 });
      }
    }
    // 后续断言读"最后一次尝试"的状态 —— 重试路径会重置界面，别拿重置后的空状态当结果
    probe = lastProbe || probe;
    add('Agent 真实运行并通过引用闸门', passed, `${attempt} 次尝试`);
    add('Agent 报出了工具调用步骤', probe.agentStepCount > 0, `${probe.agentStepCount} 步：${probe.agentStepIcons.join(',')}`);
    add(
      '步骤里包含真实的工具调用与返回',
      probe.agentStepIcons.includes('tool') && probe.agentStepIcons.length > 0,
      probe.agentStepIcons.join(','),
    );
    add('给出了回答', probe.agentAnswer.length > 0, `${probe.agentAnswer.length} 字｜开头：${probe.agentAnswer.slice(0, 48)}`);
    add(
      '引用核查结论已呈现',
      probe.citationPasses === 'true' || probe.citationPasses === 'false',
      `passes=${probe.citationPasses}｜${probe.citationText.slice(0, 90)}`,
    );
    add('Agent 未报错', probe.agentError === '', probe.agentError.slice(0, 90));
    add(
      '题名级警示与结论一致',
      (probe.citationPasses === 'true') === probe.titleOnlyWarning,
      `passes=${probe.citationPasses} warning=${probe.titleOnlyWarning}`,
    );
    const consistent = probe.citationPasses === 'true' ? probe.citedChips > 0 : probe.citedChips === 0;
    add('引用结论与引用 id 自洽', consistent, `passes=${probe.citationPasses} cited=${probe.citedChips}`);

    // ---- 证据链：跑完后应攒下论文卡，打开可见、可开抽屉 ----
    await session.eval(`(() => { document.querySelector('[data-testid="rail-toggle"]').click(); return true; })()`);
    await session.waitFor(`document.querySelectorAll('[data-testid="rail-card"]').length > 0`, { timeout: 15000 });
    probe = await session.eval(PROBE);
    add('证据链攒下了论文卡', probe.railCards > 0, `${probe.railCards} 张`);
    add('引用 id 全部有效', probe.citedIds.every((id) => id && id.length > 0), `引用 ${probe.citedChips} 条`);
    await session.eval(`(() => { document.querySelector('[data-testid="rail-card"]').click(); return true; })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="evidence-drawer"]')`, { timeout: 15000 });
    probe = await session.eval(PROBE);
    add('证据链卡片可打开抽屉', probe.drawerPresent === true);

    if (SHOT) {
      const shot = await session.send('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(SHOT, Buffer.from(shot.data, 'base64'));
      console.log(`\n截图：${SHOT}`);
    }

    const consoleErrors = session.consoleErrors.filter((line) => line && !/favicon|DevTools/i.test(line));
    add('浏览器控制台无错误', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
  } finally {
    try { if (ws.readyState === 1) ws.close(); } catch { /* ignore */ }
    try { child.kill(); } catch { /* ignore */ }
    fs.promises.rm(profile, { recursive: true, force: true }).catch(() => {});
  }

  const failed = results.filter((r) => !r.ok);
  console.log(`\n==== ${results.length - failed.length} PASS / ${failed.length} FAIL ====`);
  return failed.length;
}

main()
  .then((fail) => {
    process.exitCode = fail ? 1 : 0;
    setTimeout(() => process.exit(process.exitCode), 400).unref();
  })
  .catch((error) => {
    console.error(`FATAL: ${error?.stack || error}`);
    process.exit(2);
  });
