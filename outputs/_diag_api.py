"""Start api alone, probe health + data endpoints, stop it. Single call."""
import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path(r"D:\a-open_source\noesis-research")
PY = REPO / ".venv" / "Scripts" / "python.exe"
OUT = REPO / "outputs" / "_diag.txt"
report = []
def emit(s):
    report.append(s)
    OUT.write_text("\n".join(report), encoding="utf-8")

def port_up(p):
    with socket.socket() as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", p)) == 0

emit(f"kg8765 up={port_up(8765)}")
env = dict(os.environ) if (os := __import__("os")) else {}
env.setdefault("KG_BASE_URL", "http://127.0.0.1:8765")
env.setdefault("KG_EXPECTED_GRAPH_ID", "ai-literature-ed16399925fac2a599ed")
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    env.pop(k, None)

api = subprocess.Popen(
    [str(PY), "-m", "uvicorn", "noesis_research_api.app:app",
     "--app-dir", str(REPO / "apps" / "api"),
     "--host", "127.0.0.1", "--port", "8100", "--log-level", "warning"],
    cwd=str(REPO), env=env,
    stdout=open(REPO / "outputs" / "_api_diag.log", "w", encoding="utf-8"),
    stderr=subprocess.STDOUT,
)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    for _ in range(40):
        if port_up(8100):
            break
        time.sleep(0.5)
    time.sleep(0.5)
    for path in ("/api/health", "/api/papers/search?q=transformer&limit=3", "/api/graph/stats"):
        try:
            with opener.open("http://127.0.0.1:8100" + path, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
                emit(f"GET {path} -> {r.status}: {body[:400]}")
        except urllib.error.HTTPError as e:
            emit(f"GET {path} -> HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}")
        except Exception as exc:  # noqa: BLE001
            emit(f"GET {path} -> {type(exc).__name__}: {exc}")
finally:
    api.terminate()
    try:
        api.wait(timeout=8)
    except subprocess.TimeoutExpired:
        api.kill()
    emit("api stopped")
print("ok")
