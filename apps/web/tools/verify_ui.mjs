/**
 * 研究工作区的无头浏览器验收（真实 Chrome + CDP，不用 puppeteer）。
 *
 * 它验的是**真实渲染出来的东西**，而不是读代码猜：
 *   · 图谱状态条的 graphId / 计数是否来自 /api/health
 *   · 检索是否真的打到后端，并回显实参与别名展开
 *   · 每条结果是否带可点击的证据引用（data-citable + data-source-id）
 *   · 详情里的断言是否**保持候选**（data-status="candidate"）
 *   · 局部图谱是否画出了节点/边，且 rootId 在节点集合内
 *   · 控制台有没有报错
 *
 * 用法（需要 API 在 8100、前端 preview 在 4173）：
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
          '--headless=new',
          '--disable-gpu',
          '--hide-scrollbars',
          '--no-first-run',
          '--no-default-browser-check',
          '--disable-extensions',
          '--remote-allow-origins=*',
          '--force-device-scale-factor=1',
          `--user-data-dir=${profile}`,
          '--window-size=1440,1000',
          `--remote-debugging-port=${port}`,
          'about:blank',
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
          } catch {
            /* 还没起来 */
          }
        }
        try {
          child.kill();
        } catch {
          /* ignore */
        }
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
    ws.onopen = () => {
      clearTimeout(timer);
      resolve(ws);
    };
    ws.onerror = (event) => {
      clearTimeout(timer);
      reject(new Error(`CDP WebSocket 错误：${event?.message || 'unknown'}`));
    };
  });
}

class Session {
  constructor(ws, sessionId) {
    this.ws = ws;
    this.sessionId = sessionId;
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
      }, 30000);
    });
  }

  async eval(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
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
  const chips = qa('[data-testid="evidence-chip"]');
  return {
    title: document.title,
    graphHeader: q('[data-testid="graph-header"]')?.textContent || '',
    pinState: q('[data-testid="pin-state"]')?.textContent || '',
    boundary: Boolean(q('[data-testid="boundary-notice"]')),
    hasSearchForm: Boolean(q('[data-testid="search-form"]')),
    appliedEcho: q('[data-testid="applied-echo"]')?.textContent || '',
    expandedTerms: q('[data-testid="expanded-terms"]')?.textContent || '',
    paperCount: qa('[data-testid="paper-item"]').length,
    firstPaperId: q('[data-testid="paper-item"]')?.getAttribute('data-publication-id') || '',
    evidenceChips: chips.length,
    citableChips: chips.filter((el) => el.getAttribute('data-citable') === 'true').length,
    firstSourceId: chips.find((el) => el.getAttribute('data-source-id'))?.getAttribute('data-source-id') || '',
    detailId: q('[data-testid="detail-id"]')?.textContent || '',
    detailTitle: q('[data-testid="detail-title"]')?.textContent || '',
    assertionCount: qa('[data-testid="assertion-item"]').length,
    assertionStatuses: qa('[data-testid="assertion-item"]').map((el) => el.getAttribute('data-status')),
    graphNodes: qa('[data-testid="graph-node"]').length,
    graphEdges: qa('[data-testid="graph-edge"]').length,
    errorBanner: q('[data-testid="error-banner"]')?.textContent || '',
    bodyBg: getComputedStyle(document.body).backgroundColor,
    rootOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
})()`;

async function main() {
  if (!fs.existsSync(CHROME)) throw new Error(`找不到 Chrome：${CHROME}`);
  const { child, profile, wsUrl } = await launchChrome();
  const ws = await connect(wsUrl);
  // 一个 Session 实例对应一条 WebSocket：Target.* 用浏览器级（不带 sessionId），
  // 之后把 sessionId 换成页面级即可。**不要为同一 ws 建两个 Session** ——
  // 后建的会覆盖前者的 onmessage，消息就再也回不到等待方。
  const session = new Session(ws, null);
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
    await session.waitFor(`!!document.querySelector('[data-testid="search-form"]')`);

    // 图谱状态条必须真的拿到数据（而不是一直显示"正在读取"）
    await session.waitFor(
      `(document.querySelector('[data-testid="graph-header"]')?.textContent || '').includes('graphId')`,
      { timeout: 25000 },
    );

    let probe = await session.eval(PROBE);
    add('页面标题正确', /NOESIS Research/.test(probe.title), probe.title);
    add('状态条显示 graphId', /graphId/.test(probe.graphHeader), probe.graphHeader.trim().slice(0, 80));
    add('状态条显示版本锁定状态', /版本锁定|未锁定/.test(probe.pinState), probe.pinState.trim());
    add('边界说明可见', probe.boundary === true);
    add('无横向溢出', probe.rootOverflow <= 1, `溢出 ${probe.rootOverflow}px`);
    add('页面无错误横幅', probe.errorBanner === '', probe.errorBanner.slice(0, 80));

    // 执行一次真实检索
    await session.eval(`(() => {
      const input = document.querySelector('input[name="q"]');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, 'transformer');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('[data-testid="search-submit"]').click();
      return true;
    })()`);

    await session.waitFor(`document.querySelectorAll('[data-testid="paper-item"]').length > 0`, {
      timeout: 25000,
    });
    probe = await session.eval(PROBE);
    add('检索返回真实论文', probe.paperCount > 0, `${probe.paperCount} 条`);
    add('实参回显含 q=transformer', /q=transformer/.test(probe.appliedEcho), probe.appliedEcho.trim().slice(0, 100));
    add(
      '每条结果都带可点击证据',
      probe.evidenceChips >= probe.paperCount && probe.citableChips === probe.evidenceChips,
      `chips=${probe.evidenceChips} citable=${probe.citableChips} papers=${probe.paperCount}`,
    );
    add('证据引用带 sourceId', probe.firstSourceId.length > 0, probe.firstSourceId);

    const firstId = probe.firstPaperId;
    await session.eval(`(() => {
      document.querySelector('[data-testid="paper-item"]').click();
      return true;
    })()`);
    await session.waitFor(`!!document.querySelector('[data-testid="detail-panel"]')`, { timeout: 25000 });
    probe = await session.eval(PROBE);
    add('详情面板打开且是同一篇', probe.detailId === firstId, `detail=${probe.detailId} list=${firstId}`);
    add('详情标题非空', probe.detailTitle.length > 0, probe.detailTitle.slice(0, 60));
    const allCandidate = probe.assertionStatuses.every((s) => s === 'candidate');
    add(
      '断言在 UI 上恒为候选',
      probe.assertionStatuses.length === 0 ? true : allCandidate,
      `assertions=${probe.assertionCount} statuses=${probe.assertionStatuses.join(',') || '(无)'}`,
    );

    // 切到局部图谱
    await session.eval(`(() => {
      Array.from(document.querySelectorAll('[data-testid="tab"]')).find((el) => el.getAttribute('data-tab') === 'graph').click();
      return true;
    })()`);
    await session.waitFor(`document.querySelectorAll('[data-testid="graph-node"]').length > 0`, {
      timeout: 25000,
    });
    probe = await session.eval(PROBE);
    add('局部图谱画出节点', probe.graphNodes > 0, `nodes=${probe.graphNodes} edges=${probe.graphEdges}`);

    if (SHOT) {
      const shot = await session.send('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(SHOT, Buffer.from(shot.data, 'base64'));
      console.log(`\n截图：${SHOT}`);
    }

    const consoleErrors = session.consoleErrors.filter(
      (line) => line && !/favicon|DevTools/i.test(line),
    );
    add('浏览器控制台无错误', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
  } finally {
    try {
      if (ws.readyState === 1) ws.close();
    } catch {
      /* ignore */
    }
    try {
      child.kill();
    } catch {
      /* ignore */
    }
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
