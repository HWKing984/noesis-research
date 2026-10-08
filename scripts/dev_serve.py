"""本地开发启动器：同时拉起 业务API / Agent服务 / 前端预览，并保持运行。

为什么存在：本机沙箱会在一次工具调用结束后回收它派生的进程树，"先起服务再去看"
必然失败。本脚本作为**唯一父进程**常驻，适合用 WMI（``Win32_Process.Create``）这类
脱离当前进程树的方式启动 —— 这样服务能活到被显式停止为止。

用法：
    python scripts/dev_serve.py start   # 启动并常驻（默认）
    python scripts/dev_serve.py stop    # 按 PID 记录停止全部服务

说明：
* LLM 配置优先取环境变量；缺省时**仅在本机开发场景**回退读取 NOESIS 工作树的
  ``backend/.env``（只读，值不打印、不写日志）。生产部署必须显式提供。
* 停止也可以直接按端口杀：8100 / 8101 / 4173。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "apps" / "web"
AGENT = REPO / "services" / "research-agent"
NODE_EXE = os.environ.get(
    "NODE_EXE",
    r"C:\Users\Y7000P\.workbuddy\binaries\node\versions\22.22.2-3\node.exe",
)
STATE_FILE = Path(os.environ.get("TEMP", "/tmp")) / "noesis_dev_serve.json"

API_PORT = 8100
AGENT_PORT = 8101
WEB_PORT = 4173

#: NOESIS 工作树（只读）——本机开发时缺省的 LLM 配置来源。
NOESIS_ENV = Path(r"D:\a-Soft\backend\.env")


def load_llm_env() -> dict[str, str]:
    """LLM_* 缺省时只读 NOESIS 的 .env；值只进子进程环境，不打印。"""
    resolved: dict[str, str] = {}
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        value = os.environ.get(name, "").strip()
        if value:
            resolved[name] = value
    if len(resolved) == 3 or not NOESIS_ENV.is_file():
        return resolved
    try:
        for line in NOESIS_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            if name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL") and name not in resolved:
                resolved[name] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return resolved


def build_services() -> list[dict[str, object]]:
    services: list[dict[str, object]] = []

    api_env = dict(os.environ)
    api_env.setdefault("KG_BASE_URL", "http://127.0.0.1:8765")
    api_env.setdefault("KG_EXPECTED_GRAPH_ID", "ai-literature-ed16399925fac2a599ed")
    services.append(
        {
            "name": "api",
            "port": API_PORT,
            "argv": [
                str(REPO / ".venv" / "Scripts" / "python.exe"),
                "-m", "uvicorn", "noesis_research_api.app:app",
                "--app-dir", str(REPO / "apps" / "api"),
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
            "argv": [
                str(AGENT / ".venv" / "Scripts" / "python.exe"),
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
            "argv": [
                NODE_EXE,
                str(WEB / "node_modules" / "vite" / "bin" / "vite.js"),
                "preview", "--port", str(WEB_PORT), "--strictPort",
            ],
            "env": dict(os.environ),
            "cwd": str(WEB),
        }
    )
    return services


def start() -> int:
    log_dir = Path(os.environ.get("TEMP", "/tmp")) / "noesis_dev"
    log_dir.mkdir(parents=True, exist_ok=True)
    handles: list[tuple[dict[str, object], subprocess.Popen, object]] = []
    for service in build_services():
        handle = open(log_dir / f"{service['name']}.log", "w", encoding="utf-8")
        process = subprocess.Popen(
            service["argv"],  # type: ignore[arg-type]
            cwd=str(service["cwd"]),
            env=service["env"],  # type: ignore[arg-type]
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        handles.append((service, process, handle))
        print(f"[dev] {service['name']} pid={process.pid} port={service['port']}", flush=True)

    STATE_FILE.write_text(
        json.dumps({str(s["name"]): p.pid for s, p, _ in handles}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[dev] pid 记录在 {STATE_FILE}", flush=True)
    print(f"[dev] 前端地址 http://127.0.0.1:{WEB_PORT}", flush=True)

    try:
        while True:
            time.sleep(5)
            alive = [(name, proc) for name, proc, _ in handles if proc.poll() is None]
            if not alive:
                print("[dev] 所有服务都已退出，启动器结束", flush=True)
                return 1
            stop_requested = (log_dir / "STOP").exists()
            if stop_requested:
                print("[dev] 检测到 STOP 标记，开始停止服务", flush=True)
                break
    finally:
        for _, process, handle in handles:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
            handle.close()
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("[dev] 已全部停止", flush=True)
    return 0


def stop() -> int:
    if not STATE_FILE.exists():
        print("[dev] 没有运行中的记录")
        return 0
    pids = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    for name, pid in pids.items():
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
        )
        print(f"[dev] stop {name} pid={pid} -> exit {result.returncode}")
    STATE_FILE.unlink()
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"
    if mode == "stop":
        raise SystemExit(stop())
    if mode != "start":
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(start())
