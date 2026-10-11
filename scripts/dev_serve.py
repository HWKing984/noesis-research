"""本地开发启动器：一键拉起 **KG只读服务 / 业务API / Agent服务 / 前端预览**，等就绪后打开浏览器，并保持运行。

为什么存在：宿主沙箱会在一次工具调用结束后回收它派生的进程树，"先起服务再去看"
必然失败。本脚本作为**唯一父进程**常驻，适合双击 ``start.cmd`` 或由任务计划程序
拉起 —— 这样服务能活到被显式停止为止。

用法：
    python scripts/dev_serve.py start [--no-open]   # 启动并常驻（默认）
    python scripts/dev_serve.py stop                # 停止全部服务（含端口兜底清理）

依赖链（少一层就整体不可用）：
    Neo4j Desktop（7474/7687，需在 GUI 启动）
      └─ AI-Literature-KG 只读应用 127.0.0.1:8765   ← ``D:\\a-open_source\\neo4j``
           └─ NOESIS Research API  127.0.0.1:8100
                └─ 研究工作区前端  127.0.0.1:4173

说明：
* KG 只读应用**尽最大努力启动**：仓库/venv 缺失、密码取不到、8765 已被占用时
  只告警不失败（此时 API 的 ``/api/health`` 按设计返回 503，不返回离线替代数据）。
  密码来源：``NEO4J_PASSWORD`` 环境变量 > NOESIS 工作树 ``backend/.env``（只读，
  值不打印、不落盘、不写日志）。
* 启动前做**前置检查**：venv / node_modules / 前端产物缺失时给出可执行的修复命令，
  不静默降级。前端 ``dist`` 缺失会自动构建一次。
* 端口被占用时**直接报错退出**，不抢端口 —— 否则请求会打到旧代码上（本项目踩过）。
* 就绪判定用 **TCP 连通** 而不是发 HTTP 请求；服务**并行**等待，超时上限
  ``DEV_START_TIMEOUT``（默认 180s，agent 首次导入 deepagents/langchain 冷启动较慢）。
* ``stop`` 只杀"本次启动记录下来的、且正在监听的进程"，避免误杀别人的服务。
* LLM 配置优先取环境变量；缺省时同样回退读 NOESIS 的 ``backend/.env``。生产部署必须显式提供。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "apps" / "web"
AGENT = REPO / "services" / "research-agent"
API_DIR = REPO / "apps" / "api"

API_PY = REPO / ".venv" / "Scripts" / "python.exe"
AGENT_PY = AGENT / ".venv" / "Scripts" / "python.exe"
VITE_JS = WEB / "node_modules" / "vite" / "bin" / "vite.js"
WEB_DIST = WEB / "dist" / "index.html"

STATE_FILE = Path(os.environ.get("TEMP", "/tmp")) / "noesis_dev_serve.json"
LOG_DIR = Path(os.environ.get("TEMP", "/tmp")) / "noesis_dev"

#: NOESIS 工作树（只读）——本机开发时 LLM_* 与 NEO4J_PASSWORD 的缺省来源。
NOESIS_ENV = Path(r"D:\a-Soft\backend\.env")

#: AI-Literature-KG 仓库（只读依赖）——8765 只读应用的来源。
KG_REPO = Path(os.environ.get("KG_REPO_DIR", r"D:\a-open_source\neo4j"))
KG_PY = KG_REPO / ".venv-validation" / "Scripts" / "python.exe"
KG_SCRIPT = KG_REPO / "scripts" / "course_graph.py"
KG_RUNTIME_CONFIG = KG_REPO / "resources" / "course_graph_runtime.json"

API_PORT = 8100
AGENT_PORT = 8101
WEB_PORT = 4173
KG_PORT = 8765

#: 本工程**必须**独享的端口（占用即报错）；KG 是可选依赖，已占用时直接复用不抢。
PORTS = (API_PORT, AGENT_PORT, WEB_PORT)

#: 锁定的图谱版本。KG 只读应用的实际 graphId 与它不符时，API 会返回 503(版本漂移)，绝不静默换图。
DEFAULT_KG_GRAPH_ID = "ai-literature-ed16399925fac2a599ed"

#: 冷启动上限（秒）。agent 首次导入 deepagents/langchain 实测可达 1~2 分钟。
START_TIMEOUT = float(os.environ.get("DEV_START_TIMEOUT", "180"))


def log(message: str) -> None:
    print(f"[dev] {message}", flush=True)


def resolve_node() -> str:
    """优先级：NODE_EXE 环境变量 > 本机托管的 node > PATH 里的 node。"""
    explicit = os.environ.get("NODE_EXE", "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    managed = Path(r"C:\Users\Y7000P\.workbuddy\binaries\node\versions\22.22.2-3\node.exe")
    if managed.is_file():
        return str(managed)
    return "node"


def _read_env_file(path: Path, names: tuple[str, ...]) -> dict[str, str]:
    """从 .env 里挑出指定键。值只进子进程环境，不打印、不落盘、不写日志。"""
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return found
    for line in text.splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if name in names and name not in found:
            found[name] = value.strip().strip('"').strip("'")
    return found


def load_llm_env() -> dict[str, str]:
    """LLM_* 先取环境变量，缺失的键回退读 NOESIS 的 .env。"""
    names = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
    resolved = {n: os.environ[n].strip() for n in names if os.environ.get(n, "").strip()}
    if len(resolved) == len(names) or not NOESIS_ENV.is_file():
        return resolved
    for name, value in _read_env_file(NOESIS_ENV, names).items():
        resolved.setdefault(name, value)
    return resolved


def load_neo4j_password() -> str:
    """Neo4j 密码：环境变量优先，其次 NOESIS 工作树的 ``backend/.env``（只读）。

    与 LLM 凭据同一套口径：值不打印、不落盘。取不到就返回空串（KG 降级为"不启动"）。
    """
    env_value = os.environ.get("NEO4J_PASSWORD", "").strip()
    if env_value:
        return env_value
    if not NOESIS_ENV.is_file():
        return ""
    return _read_env_file(NOESIS_ENV, ("NEO4J_PASSWORD",)).get("NEO4J_PASSWORD", "")


def port_in_use(port: int, host: str = "127.0.0.1", timeout: float = 0.6) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _netstat_listeners() -> dict[int, set[int]]:
    """解析 ``netstat -ano``，返回 ``{端口: {pid}}``（仅 TCP LISTENING）。

    注意：netstat 在中文 Windows 上输出 GBK，**不能用 ``text=True`` 直接解码**
    （会崩在 reader 线程上、``stdout`` 变成 None）。这里收字节再 ``errors="replace"``。
    """
    try:
        raw = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True).stdout or b""
    except OSError:
        return {}
    listeners: dict[int, set[int]] = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[-2].upper() != "LISTENING":
            continue
        if ":" not in parts[1]:
            continue
        try:
            port = int(parts[1].rsplit(":", 1)[1])
        except ValueError:
            continue
        if parts[-1].isdigit():
            listeners.setdefault(port, set()).add(int(parts[-1]))
    return listeners


def build_services() -> list[dict[str, object]]:
    node = resolve_node()
    services: list[dict[str, object]] = []

    api_env = dict(os.environ)
    api_env.setdefault("KG_BASE_URL", f"http://127.0.0.1:{KG_PORT}")
    api_env.setdefault("KG_EXPECTED_GRAPH_ID", DEFAULT_KG_GRAPH_ID)
    services.append(
        {
            "name": "api",
            "port": API_PORT,
            "path": "/api/health",
            "argv": [
                str(API_PY),
                "-m", "uvicorn", "noesis_research_api.app:app",
                "--app-dir", str(API_DIR),
                "--host", "127.0.0.1", "--port", str(API_PORT),
                "--log-level", "warning",
            ],
            "env": api_env,
            "cwd": str(REPO),
        }
    )

    agent_env = dict(api_env)
    for name, value in load_llm_env().items():
        agent_env.setdefault(name, value)
    agent_env["PYTHONPATH"] = str(AGENT)
    services.append(
        {
            "name": "agent",
            "port": AGENT_PORT,
            "path": "/health",
            "argv": [
                str(AGENT_PY),
                "-m", "uvicorn", "noesis_research_agent.server:app",
                "--app-dir", str(AGENT),
                "--host", "127.0.0.1", "--port", str(AGENT_PORT),
                "--log-level", "warning",
            ],
            "env": agent_env,
            "cwd": str(AGENT),
        }
    )

    services.append(
        {
            "name": "web",
            "port": WEB_PORT,
            "path": "/",
            "argv": [
                node,
                str(VITE_JS),
                "preview", "--port", str(WEB_PORT), "--strictPort",
            ],
            "env": dict(os.environ),
            "cwd": str(WEB),
        }
    )
    return services


def kg_graph_id_hint() -> str:
    """读 KG 运行配置里钉住的 graphId（纯文件读取，不发网络请求）。"""
    try:
        return str(json.loads(KG_RUNTIME_CONFIG.read_text(encoding="utf-8")).get("graphId", ""))
    except (OSError, ValueError):
        return ""


def build_kg_service() -> tuple[dict[str, object] | None, str]:
    """构造 AI-Literature-KG 只读服务（8765）。

    返回 ``(service, reason)``。不可用时 service 为 ``None``，``reason`` 说明原因，
    由调用方决定是告警还是继续 —— KG 是外部只读依赖，缺了不应让整个启动失败。
    """
    if port_in_use(KG_PORT):
        return None, f"8765 已在监听，复用现有 KG 服务（不由本脚本接管）"
    if not KG_SCRIPT.is_file():
        return None, f"KG 仓库未就位：{KG_SCRIPT}"
    if not KG_PY.is_file():
        return None, f"KG 的 venv 未就位：{KG_PY}"
    password = load_neo4j_password()
    if not password:
        return None, "取不到 Neo4j 密码（需 NEO4J_PASSWORD 环境变量或 NOESIS backend/.env）"

    env = dict(os.environ)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(name, None)  # 只读应用访问的是 127.0.0.1:7474，不该走任何代理
    env["NO_PROXY"] = (env.get("NO_PROXY", "") + ",127.0.0.1,localhost").lstrip(",")
    env["NEO4J_PASSWORD"] = password  # 只进子进程环境，不打印、不落盘

    return (
        {
            "name": "kg",
            "port": KG_PORT,
            "path": "/api/health",
            "argv": [
                str(KG_PY), "-B", str(KG_SCRIPT), "serve",
                "--database", "neo4j", "--user", "neo4j", "--port", str(KG_PORT),
            ],
            "env": env,
            "cwd": str(KG_REPO),
        },
        "",
    )


def preflight() -> bool:
    """前置检查：缺什么就说什么，并给可直接复制的修复命令。"""
    problems: list[str] = []

    if not API_PY.is_file():
        problems.append(
            f"业务 API 的 venv 缺失：{API_PY}\n"
            "    python -m venv .venv && .venv/Scripts/python -m pip install -r apps/api/requirements.txt"
        )
    if not AGENT_PY.is_file():
        problems.append(
            f"研究 Agent 的 venv 缺失：{AGENT_PY}\n"
            "    python -m venv services/research-agent/.venv && "
            "services/research-agent/.venv/Scripts/python -m pip install -r services/research-agent/requirements.txt"
        )
    if not VITE_JS.is_file():
        problems.append(
            f"前端依赖缺失：{VITE_JS}\n"
            f"    cd apps/web && pnpm install      （目录：{WEB}）"
        )

    if problems:
        log("前置检查未通过：")
        for item in problems:
            log("  - " + item)
        return False

    # dist 缺失时自动构建一次（vite preview 只服务构建产物，没有 dist 起不来）。
    if not WEB_DIST.is_file():
        log("前端产物缺失，先构建一次（vite build）…")
        code = subprocess.run([resolve_node(), str(VITE_JS), "build"], cwd=str(WEB)).returncode
        if code != 0 or not WEB_DIST.is_file():
            log("前端构建失败，无法继续。")
            return False
    return True


def _tail(path: Path, lines: int = 15) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "（无日志）"
    return "\n".join(content[-lines:]) or "（空）"


def stop_handles(handles: list[tuple[dict[str, object], subprocess.Popen, object]]) -> None:
    for _, process, handle in handles:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        try:
            handle.close()  # type: ignore[union-attr]
        except Exception:
            pass
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def _write_state(pids: set[int]) -> None:
    STATE_FILE.write_text(
        json.dumps({"pids": sorted(int(p) for p in pids)}, ensure_ascii=False),
        encoding="utf-8",
    )


def start(argv: list[str]) -> int:
    open_browser = "--no-open" not in argv

    if not preflight():
        return 1

    busy = [p for p in PORTS if port_in_use(p)]
    if busy:
        log(f"端口被占用：{busy}。先停止旧服务再启动（stop.cmd 或 python scripts/dev_serve.py stop）。")
        return 1

    kg_service, kg_reason = build_kg_service()
    if kg_service is not None:
        log(f"kg   将启动 AI-Literature-KG 只读应用（{KG_PORT}）")
        hint = kg_graph_id_hint()
        expected = os.environ.get("KG_EXPECTED_GRAPH_ID", DEFAULT_KG_GRAPH_ID)
        if hint and hint != expected:
            log(f"kg   警告：运行配置 graphId={hint} 与锁定值 {expected} 不一致，API 会返回 503(kg_graph_version_mismatch)")
    elif port_in_use(KG_PORT):
        log(f"kg   复用：{kg_reason}")
    else:
        log(f"kg   跳过：{kg_reason}")
        log(f"kg   后果：{KG_PORT} 无服务 → API 的就绪探针与业务端点都会返回 503（本项目不返回离线替代数据）")

    planned: list[dict[str, object]] = ([kg_service] if kg_service else []) + build_services()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # 遗留毒丸防护（2026-10-10 实锤）：STOP 标记是"上一次运行"的停止指令。验收脚本
    # （outputs/_e2e_once.py）用它停服务，若 launcher 不消费、脚本又漏删，一次中断的
    # 验收就会让之后**每一次** start 都"服务起好即自停、窗口静默关闭"。
    # 语义：start 时刻已存在的标记属于过去，直接清掉；运行期间新写入的才生效。
    stale_stop = LOG_DIR / "STOP"
    if stale_stop.exists():
        stale_stop.unlink()
        log("清除遗留的 STOP 标记（属于上一次运行，不生效）")
    handles: list[tuple[dict[str, object], subprocess.Popen, object]] = []
    for service in planned:
        handle = open(LOG_DIR / f"{service['name']}.log", "w", encoding="utf-8")
        process = subprocess.Popen(
            service["argv"],  # type: ignore[arg-type]
            cwd=str(service["cwd"]),
            env=service["env"],  # type: ignore[arg-type]
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        handles.append((service, process, handle))
        log(f"启动 {service['name']:<5} pid={process.pid} port={service['port']}")

    # 先记"启动的进程"，即使后续就绪失败也能被 stop 收掉。
    _write_state({p.pid for _, p, _ in handles})
    log(f"等待就绪（上限 {START_TIMEOUT:.0f}s）…")

    # 并行等待：各服务冷启动耗时差异大，串行等待会平白累加超时。
    pending: dict[str, tuple[int, subprocess.Popen]] = {
        str(s["name"]): (int(s["port"]), p) for s, p, _ in handles
    }
    ready: dict[str, bool] = {}
    deadline = time.time() + START_TIMEOUT
    started = time.time()
    while pending and time.time() < deadline:
        for name in list(pending):
            port, process = pending[name]
            if port_in_use(port):
                ready[name] = True
                log(f"{name:<5} 就绪 http://127.0.0.1:{port}   ({time.time() - started:.1f}s)")
                del pending[name]
            elif process.poll() is not None:
                ready[name] = False
                log(f"{name:<5} 启动失败（进程已退出 code={process.returncode}）")
                del pending[name]
        if pending:
            time.sleep(0.5)

    for name in pending:
        ready[name] = False
        log(f"{name:<5} 超时未就绪（{START_TIMEOUT:.0f}s 内 port {pending[name][0]} 无监听）")

    # KG 是外部只读依赖：它挂了只降级（API 503），不该拖垮核心三件套。
    failed_core = [n for n, ok in ready.items() if not ok and n != "kg"]
    for service, _, _ in handles:
        if not ready.get(str(service["name"])):
            log(f"---- {service['name']} 日志尾部 ----")
            log(_tail(LOG_DIR / f"{service['name']}.log", 25))
    if failed_core:
        log(f"核心服务未就绪：{failed_core}。停止已拉起的部分。")
        stop_handles(handles)
        return 1
    if "kg" in ready and not ready["kg"]:
        log("kg   未就绪 —— API 的 /api/health 与业务端点会返回 503；其余服务继续运行。")

    # 就绪后再补记"真正监听端口的 PID"（uvicorn 的实际监听者可能是启动进程的子进程），
    # 这样 stop() 能精确命中，不必只靠端口兜底。只记录**本次启动**的服务端口，
    # 复用的外部 KG(8765) 不会被记进来，stop 也就不会去动别人的进程。
    listeners = _netstat_listeners()
    recorded = {p.pid for _, p, _ in handles}
    for service, _, _ in handles:
        recorded |= listeners.get(int(service["port"]), set())
    _write_state(recorded)

    url = f"http://127.0.0.1:{WEB_PORT}"
    log(f"核心服务就绪，前端地址 {url}")
    log(f"日志目录 {LOG_DIR}   停止：Ctrl+C 或 stop.cmd")
    if open_browser:
        try:
            os.startfile(url)  # type: ignore[attr-defined]
        except Exception:
            pass

    try:
        while True:
            time.sleep(5)
            alive = [(name, proc) for name, proc, _ in handles if proc.poll() is None]
            if not alive:
                # 走到这里说明核心服务此前已全部就绪；全部退出（stop.cmd 或崩溃）
                # 都按"正常收尾"退出，避免包装脚本误报"启动失败"。
                log("所有服务都已退出，启动器结束")
                return 0
            if (LOG_DIR / "STOP").exists():
                log("检测到 STOP 标记，开始停止服务")
                (LOG_DIR / "STOP").unlink()  # 消费掉：标记是一次性指令，不消费就会变成毒丸
                break
    finally:
        stop_handles(handles)
        log("已全部停止")
    return 0


def stop() -> int:
    """只杀"本次启动记录下来的、且此刻仍在监听本工程端口"的进程；其余一律不动。

    判定口径 = ``recorded(状态文件) ∩ listening(此刻)``：
    * 状态文件里的陈旧 PID（已被系统回收复用）不会被误杀；
    * thome 自己起的 KG(8765) 不在状态文件里 → **不会被本脚本停掉**；

    两个集合刻意不重合：
    * ``recognized`` 含 8765 —— 由本脚本启动的 KG 必须能被停掉；
    * 兜底端口扫描只扫核心三端口（8100/8101/4173，占用即报错 ⇒ 必然是本次启动的），
      **不含 8765**，否则复用外部 KG 的场景下 stop 会把别人的服务一并杀掉。
    """
    listeners = _netstat_listeners()
    recognized: set[int] = set()
    for port in PORTS + (KG_PORT,):
        recognized |= listeners.get(port, set())

    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "pids" in data:
            recorded = [int(x) for x in data["pids"]]
        else:  # 兼容旧格式 {name: pid}
            recorded = [int(x) for x in data.values()]
        hit = [pid for pid in recorded if pid in recognized]
        stale = [pid for pid in recorded if pid not in recognized]
        for pid in hit:
            result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            log(f"停止 pid={pid} -> exit {result.returncode}")
        if stale:
            log(f"跳过 {len(stale)} 个已不在监听状态的 PID：{stale}")
        STATE_FILE.unlink()
    else:
        log("没有运行中的 PID 记录，改按端口兜底清理")

    for port in PORTS:
        for pid in sorted(listeners.get(port, set())):
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            log(f"兜底清理 监听 {port} 的 pid={pid}")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"
    if mode == "stop":
        raise SystemExit(stop())
    if mode != "start":
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(start(sys.argv[2:]))
