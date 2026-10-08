"""端到端验收编排：一次调用内把三个服务拉起来 → 跑无头浏览器断言 → 收尾清理。

为什么存在：本机沙箱会在一次工具调用结束后回收它派生的进程，所以"先起服务、
下一步再验"必然失败。把启动/就绪等待/验收/清理收进同一个进程，服务就活得到验收结束。

用法（在 apps/web 下）：
    python tools/e2e.py [--skip-tests] [--keep-logs]

前置条件：Neo4j 与 KG 服务（127.0.0.1:8765）在跑；
LLM 由环境变量提供（LLM_API_KEY / LLM_MODEL / LLM_BASE_URL）。
为方便本机验证，LLM 缺省时**仅在本地 harness 里**回退到 ollama 的
qwen3-vl:8b —— 这只是让验收能跑起来，不代表生产模型选型。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
REPO = WEB.parents[1]
TMP = Path(os.environ.get("TEMP", "/tmp"))

NODE = os.environ.get(
    "NODE_EXE",
    r"C:\Users\Y7000P\.workbuddy\binaries\node\versions\22.22.2-3\node.exe",
)
API_PY = REPO / ".venv" / "Scripts" / "python.exe"
AGENT_PY = REPO / "services" / "research-agent" / ".venv" / "Scripts" / "python.exe"

API_PORT = 8100
AGENT_PORT = 8101
WEB_PORT = 4173

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(message: str) -> None:
    print(f"[e2e] {message}", flush=True)


def wait_port(port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            OPENER.open(f"http://127.0.0.1:{port}/", timeout=3).read(16)
            return True
        except urllib.error.HTTPError:
            return True  # 有响应即端口已就绪（哪怕是 404）
        except Exception:
            time.sleep(0.4)
    return False


def run_command(command: list[str], *, cwd: Path, label: str) -> int:
    log(f"{label}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=str(cwd))
    log(f"{label}: exit {completed.returncode}")
    return completed.returncode


def spawn(label: str, command: list[str], env: dict[str, str]) -> subprocess.Popen:
    log_path = TMP / f"e2e_{label}.log"
    handle = open(log_path, "w", encoding="utf-8")
    log(f"spawn {label} -> {log_path.name}")
    process = subprocess.Popen(
        command,
        cwd=str(WEB if label == "web" else REPO),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    process._e2e_log_handle = handle  # noqa: SLF001 - 便于收尾关闭
    return process


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
    try:
        process._e2e_log_handle.close()  # noqa: SLF001
    except Exception:
        pass


def main(argv: list[str]) -> int:
    skip_tests = "--skip-tests" in argv
    failures: list[str] = []

    node_tests = [
        NODE,
        "--test",
        str(WEB / "src" / "lib" / "evidence.test.mjs"),
        str(WEB / "src" / "lib" / "agentApi.test.mjs"),
    ]
    if not skip_tests:
        if run_command(node_tests, cwd=WEB, label="web unit tests") != 0:
            failures.append("web unit tests")

    if run_command([NODE, str(WEB / "node_modules" / "vite" / "bin" / "vite.js"), "build"], cwd=WEB, label="vite build") != 0:
        failures.append("vite build")
        print("[e2e] 构建失败，无法继续端到端验收")
        return 1

    api_env = dict(os.environ)
    api_env["KG_BASE_URL"] = os.environ.get("KG_BASE_URL", "http://127.0.0.1:8765")
    api_env["KG_EXPECTED_GRAPH_ID"] = os.environ.get(
        "KG_EXPECTED_GRAPH_ID", "ai-literature-ed16399925fac2a599ed"
    )

    agent_env = dict(api_env)
    # 仅本地 harness 的缺省：生产必须显式配置，不得依赖这条回退。
    agent_env.setdefault("LLM_API_KEY", "ollama-local")
    agent_env.setdefault("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    agent_env.setdefault("LLM_MODEL", "qwen3-vl:8b")

    processes = []
    try:
        processes.append(
            spawn(
                "api",
                [
                    str(API_PY),
                    "-m",
                    "uvicorn",
                    "noesis_research_api.app:app",
                    "--app-dir",
                    str(REPO / "apps" / "api"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(API_PORT),
                    "--log-level",
                    "warning",
                ],
                api_env,
            )
        )
        processes.append(
            spawn(
                "agent",
                [
                    str(AGENT_PY),
                    "-m",
                    "uvicorn",
                    "noesis_research_agent.server:app",
                    "--app-dir",
                    str(REPO / "services" / "research-agent"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(AGENT_PORT),
                    "--log-level",
                    "warning",
                ],
                agent_env,
            )
        )
        processes.append(
            spawn(
                "web",
                [
                    NODE,
                    str(WEB / "node_modules" / "vite" / "bin" / "vite.js"),
                    "preview",
                    "--port",
                    str(WEB_PORT),
                    "--strictPort",
                ],
                dict(os.environ),
            )
        )

        for port, name in ((API_PORT, "api"), (AGENT_PORT, "agent"), (WEB_PORT, "web")):
            if not wait_port(port):
                failures.append(f"{name} service did not come up on {port}")

        if failures:
            print(f"[e2e] 服务未就绪，终止：{failures}")
            return 1

        log("三个服务均已就绪，开始无头浏览器验收")
        code = run_command(
            [
                NODE,
                str(WEB / "tools" / "verify_ui.mjs"),
                "--url",
                f"http://127.0.0.1:{WEB_PORT}",
                "--shot",
                str(TMP / "noesis_e2e.png"),
            ],
            cwd=WEB,
            label="browser verification",
        )
        if code != 0:
            failures.append("browser verification")

        # 无头浏览器验收里的引用闸门结论只是"界面是否如实呈现"，
        # 真实的引用合格与否由服务端 citation 报告判定，两者不能混为一谈。
        print("[e2e] 浏览器验收退出码：" + str(code))
    finally:
        for process in processes:
            stop(process)
        log("所有服务已停止")

    if failures:
        print(f"[e2e] FAILED: {', '.join(failures)}")
        return 1
    print("[e2e] all green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
