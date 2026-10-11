"""One-shot e2e: start services via dev_serve (reusing thome's KG at 8765),
run verify_ui.mjs (real Chrome + one real agent run), then stop everything.
All in this single process — the sandbox reaps children after the tool call."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(r"D:\a-open_source\noesis-research")
PY = REPO / ".venv" / "Scripts" / "python.exe"
NODE = Path(r"C:\Users\Y7000P\.workbuddy\binaries\node\versions\22.22.2-3\node.exe")
OUT = REPO / "outputs" / "_e2e_result.txt"
LOG_DIR = Path(os.environ.get("TEMP", r"C:\Temp")) / "noesis_dev"

def port_up(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", port)) == 0

report = []
def emit(line: str) -> None:
    report.append(line)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(report))

emit(f"== e2e start {time.strftime('%H:%M:%S')}")

# 1) start services (dev_serve watches a STOP file; --no-open skips the browser)
serve = subprocess.Popen(
    [str(PY), "-X", "utf8", "scripts/dev_serve.py", "start", "--no-open"],
    cwd=str(REPO), stdout=open(LOG_DIR / "launcher.log", "w", encoding="utf-8"),
    stderr=subprocess.STDOUT,
)
try:
    deadline = time.time() + 200
    needed = (8100, 8101, 4173)
    while time.time() < deadline:
        if all(port_up(p) for p in needed):
            break
        if serve.poll() is not None:
            emit(f"launcher exited early code={serve.returncode}")
            break
        time.sleep(1.0)
    up = {str(p): port_up(p) for p in needed}
    emit(f"ports: {up}")
    if not all(up.values()):
        emit("services not ready; aborting (launcher log tail follows)")
        emit((LOG_DIR / "launcher.log").read_text(encoding="utf-8", errors="replace")[-1500:])
        sys.exit(0)

    # 2) full UI verification (includes one real agent run; 3-5 min)
    t0 = time.time()
    proc = subprocess.run(
        [str(NODE), "tools/verify_ui.mjs"],
        cwd=str(REPO / "apps" / "web"), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=420,
    )
    emit(f"== verify_ui exit={proc.returncode}  ({time.time() - t0:.0f}s)")
    emit(proc.stdout or "")
    if proc.returncode != 0 and proc.stderr:
        emit("[stderr tail]")
        emit(proc.stderr[-1200:])
finally:
    # 3) stop: dev_serve watches %TEMP%/noesis_dev/STOP
    try:
        (LOG_DIR / "STOP").write_text("stop", encoding="utf-8")
        serve.wait(timeout=30)
        emit(f"launcher stopped code={serve.returncode}")
    except Exception as exc:  # noqa: BLE001
        emit(f"stop path issue: {exc}")
        serve.terminate()
emit("== e2e done")
print("ok")
