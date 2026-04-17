"""Daemon lifecycle for the MCP server — start/stop/status over localhost HTTP.

Models (Qwen3 embedder, mxbai reranker) load once per daemon. Every CLI call
that sets ONELENS_SERVER_URL goes to the warm server (~200ms) instead of
paying a ~30s cold load per stdio subprocess spawn.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 8765
PID_FILE = Path.home() / ".onelens" / "daemon.pid"
LOG_FILE = Path.home() / ".onelens" / "daemon.log"


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _ping(port: int, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/mcp/", timeout=timeout) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        return False


def status(port: int = DEFAULT_PORT) -> dict:
    pid = _read_pid()
    running = bool(pid and _alive(pid))
    reachable = _ping(port) if running else False
    return {
        "pid": pid,
        "port": port,
        "running": running,
        "reachable": reachable,
        "url": f"http://127.0.0.1:{port}" if reachable else None,
        "log": str(LOG_FILE),
    }


def start(port: int = DEFAULT_PORT, wait_for_warm: bool = True) -> dict:
    """Spawn the FastMCP HTTP daemon with eager model warmup. Idempotent."""
    s = status(port)
    if s["reachable"]:
        return {"already_running": True, **s}

    # Clean stale PID file if process is gone.
    if s["pid"] and not s["running"]:
        PID_FILE.unlink(missing_ok=True)

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(LOG_FILE, "ab", buffering=0)

    env = {**os.environ, "ONELENS_WARM_ON_START": "1"}
    # Resolve the mcp_server.py file path so we can pass "file:mcp" to fastmcp
    # (the only form that honors --transport / --port; `-m` mode ignores them).
    import onelens.mcp_server as _srv

    server_file = _srv.__file__
    fastmcp_bin = Path(sys.executable).parent / "fastmcp"
    proc = subprocess.Popen(
        [
            str(fastmcp_bin),
            "run",
            f"{server_file}:mcp",
            "--transport",
            "http",
            "--port",
            str(port),
        ],
        env=env,
        stdout=log_fd,
        stderr=log_fd,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))

    if wait_for_warm:
        for _ in range(120):  # up to 60s for model load
            if _ping(port):
                break
            if proc.poll() is not None:
                return {
                    "ok": False,
                    "error": f"daemon exited (rc={proc.returncode}) — see {LOG_FILE}",
                    "pid": proc.pid,
                }
            time.sleep(0.5)

    return {"ok": _ping(port), "pid": proc.pid, "port": port, "log": str(LOG_FILE)}


def stop(port: int = DEFAULT_PORT) -> dict:
    pid = _read_pid()
    if not pid or not _alive(pid):
        PID_FILE.unlink(missing_ok=True)
        return {"already_stopped": True}
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return {"already_stopped": True}
    for _ in range(20):
        if not _alive(pid):
            break
        time.sleep(0.25)
    if _alive(pid):
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}
