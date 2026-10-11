"""Probe service ports + KG health; results to disk."""
import json
import socket
import urllib.request

OUT = r"D:\a-open_source\noesis-research\outputs\_probe.txt"
result = {}
for port, name in [(8100, "api"), (8101, "agent"), (4173, "web"), (8765, "kg")]:
    s = socket.socket()
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", port))
        result[name] = "LISTENING"
    except OSError:
        result[name] = "down"
    finally:
        s.close()

# api health detail (KG reachable?)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open("http://127.0.0.1:8100/api/health", timeout=8) as r:
        result["api_health"] = json.loads(r.read().decode("utf-8", "replace"))
except Exception as exc:  # noqa: BLE001
    result["api_health"] = f"{type(exc).__name__}: {exc}"

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(json.dumps(result, ensure_ascii=False, indent=1))
print("ok")
