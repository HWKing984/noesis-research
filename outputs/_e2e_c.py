"""C 方向落地后的端到端验收包装：把 NOESIS .env 的 LLM_* 注入环境后跑 e2e.py。

值不打印、不落盘（只进子进程环境）。输出流式落盘，超时也能看到进度。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(r"D:\a-open_source\noesis-research")
NOESIS_ENV = Path(r"D:\a-Soft\backend\.env")
LOG = REPO / "outputs" / "_e2e_c_run.log"
WRAPPER_TIMEOUT = 540  # 秒；外层 bash 上限 600s，留余量收尾

env = dict(os.environ)
if NOESIS_ENV.exists():
    for line in NOESIS_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "NEO4J_PASSWORD") and not env.get(key, "").strip():
            env[key] = value.strip()

LOG.parent.mkdir(parents=True, exist_ok=True)
with LOG.open("w", encoding="utf-8", errors="replace") as log_file:
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "apps" / "web" / "tools" / "e2e.py")],
        cwd=str(REPO / "apps" / "web"),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + WRAPPER_TIMEOUT
    while time.time() < deadline:
        code = proc.poll()
        if code is not None:
            break
        time.sleep(2)
    else:
        # 超时：连树一起收，避免孤儿服务占 8100/8101/4173
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        print(f"TIMEOUT after {WRAPPER_TIMEOUT}s; partial log tail below")
        print(LOG.read_text(encoding="utf-8", errors="replace")[-3000:])
        sys.exit(3)

print(LOG.read_text(encoding="utf-8", errors="replace")[-4500:])
print(f"e2e exit = {proc.returncode}")
sys.exit(proc.returncode)
