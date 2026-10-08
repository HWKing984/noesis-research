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
    exampleCount: qa('[data-testid="example-question"]').length,
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
    appliedEcho: q('[data-testid="applied-echo"]')?.textContent || '',
    paperCount: qa('[data-testid="paper-item"]').length,
    firstPaperId: q('[data-testid="paper-item"]')?.getAttribute('data-publication-id') || '',
    evidenceChips: chips.length,
    citableChips: chips.filter((el) => el.getAttribute('data-citable') === 'true').length,
    firstSourceId: chips.find((el) => el.getAttribute('data-source-id'))?.getAttribute('data-source-id') || '',
    detailId: q('[data-testid="detail-id"]')?.textContent || '',
    detailTitle: q('[data-testid="detail-title"]')?.textContent || '',
    assertionStatuses: qa('[data-testid="assertion-item"]').map((el) => el.getAttribute('data-status')),
    graphNodes: qa('[data-testid="graph-node"]').length,
    graphEdges: qa('[data-testid="graph-edge"]').length,
    drawerPresent: Boolean(q('[data-testid="evidence-drawer"]')),
    drawerFields: q('[data-testid="drawer-fields"]')?.textContent || '',
    drawerText: q('[data-testid="evidence-drawer"]')?.textContent || '',
    errorBanner: q('[data-testid="error-banner"]')?.textContent || '',
    rootOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    viewport: window.innerWidth,
    // 布局几何：主列必须占满侧栏以外的宽度，内容列要在聊天列内居中（.main 规则曾丢失导致整页左挤）
    sbW: Math.round(q('.sb')?.getBoundingClientRect().width || 0),
    mainW: Math.round(q('.main')?.getBoundingClientRect().width || 0),
    chatcolX: Math.round(q('.chatcol')?.getBoundingClientRect().left || -1),
    chatcolW: Math.round(q('.chatcol')?.getBoundingClientRect().width || 0),
    colX: Math.round(q('.chatcol .col')?.getBoundingClientRect().left || -1),
    colW: Math.round(q('.chatcol .col')?.getBoundingClientRect().width || 0),
    composerInEmpty: visible(q('.col .composer')),
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
    add('提供示例问题一键发问', probe.exampleCount > 0, `${probe.exampleCount} 个`);
    add('证据链默认收起', probe.railState === 'closed', `rail=${probe.railState}`);
    add('证据链开关带计数', probe.railCount !== '', probe.railCount);
    add('页面无横向溢出', probe.rootOverflow <= 1, `溢出 ${probe.rootOverflow}px`);
    add(
      '主列占满侧栏以外宽度',
      Math.abs(probe.sbW + probe.mainW - probe.viewport) <= 2,
      `sb=${probe.sbW} main=${probe.mainW} viewport=${probe.viewport}`,
    );
    add('提问前有输入区', probe.composerInEmpty === true, '');
    const leftPad = probe.colX - probe.chatcolX;
    const rightPad = probe.chatcolX + probe.chatcolW - (probe.colX + probe.colW);
    add(
      '内容列在聊天列内居中',
      Math.abs(leftPad - rightPad) <= 8 && leftPad > 0,
      `左 ${leftPad}px / 右 ${rightPad}px`,
    );

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
    await session.waitFor(
      `(document.querySelector('[data-testid="graph-header"]')?.textContent || '').includes('graphId')`,
      { timeout: 25000 },
    );
    probe = await session.eval(PROBE);
    add('状态条显示 graphId', /graphId/.test(probe.graphHeader), probe.graphHeader.trim().slice(0, 80));
    add('状态条显示版本锁定状态', /版本锁定|未锁定/.test(probe.pinState), probe.pinState.trim());
    add('边界说明可见', probe.boundary === true);
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
    add('实参回显含 q=transformer', /q=transformer/.test(probe.appliedEcho), probe.appliedEcho.trim().slice(0, 100));
    add(
      '每条结果都带可点击证据',
      probe.evidenceChips >= probe.paperCount && probe.citableChips === probe.evidenceChips,
      `chips=${probe.evidenceChips} citable=${probe.citableChips} papers=${probe.paperCount}`,
    );

    const firstId = probe.firstPaperId;
    await session.eval(`(() => { document.querySelector('[data-testid="paper-item"]').click(); return true; })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="detail-panel"]')`, { timeout: 25000 });
    probe = await session.eval(PROBE);
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

    // ---- 主界面：让 agent 真的跑一次 ----
    await session.eval(`(() => {
      Array.from(document.querySelectorAll('[data-testid="view-tab"]'))
        .find((el) => el.getAttribute('data-view') === 'agent').click();
      return true;
    })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="agent-chat"]')`);
    await session.eval(`(() => {
      document.querySelector('[data-testid="example-question"]').click();
      return true;
    })()`);
    await session.waitFor(`document.querySelectorAll('[data-testid="agent-step"]').length > 0`, { timeout: 240000 });
    await session.waitFor(`!!document.querySelector('[data-testid="citation-verdict"]')`, { timeout: 420000 });
    probe = await session.eval(PROBE);
    add('Agent 报出了工具调用步骤', probe.agentStepCount > 0, `${probe.agentStepCount} 步：${probe.agentStepIcons.join(',')}`);
    add(
      '步骤里包含真实的工具调用与返回',
      probe.agentStepIcons.includes('call') && probe.agentStepIcons.includes('result'),
      probe.agentStepIcons.join(','),
    );
    add('给出了回答', probe.agentAnswer.length > 0, `${probe.agentAnswer.length} 字`);
    add(
      '引用核查结论已呈现',
      probe.citationPasses === 'true' || probe.citationPasses === 'false',
      `passes=${probe.citationPasses}｜${probe.citationText.slice(0, 90)}`,
    );
    add('Agent 未报错', probe.agentError === '', probe.agentError.slice(0, 90));
    add('题名级警示呈现', probe.titleOnlyWarning === true);
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
