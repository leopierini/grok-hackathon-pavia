#!/usr/bin/env python3
"""Local page that sends map-frame goals to the running Go2 stack. 127.0.0.1 only."""
import json
import math
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "ui" / "index.html"
GUEST_ENV = ROOT / "guest-env.sh"
GOAL = ROOT / "goal.py"
STOP = ROOT / "stop.py"
POSE = ROOT / "pose_watch.py"
LIMIT_M = 8.0
HOST = "127.0.0.1"
PORT = 8765

latest = {"ok": False}
lock = threading.Lock()
send_lock = threading.Lock()


def check_goal(x, y):
    x = float(x)
    y = float(y)
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("x and y have to be numbers")
    if math.hypot(x, y) > LIMIT_M:
        raise ValueError(f"keep the goal inside {LIMIT_M:.0f} m of the start")
    return x, y


def _self_check():
    assert check_goal("1.5", "-0.25") == (1.5, -0.25)
    try:
        check_goal(9, 0)
    except ValueError:
        return
    raise SystemExit("limit check failed")


def guest(script):
    return subprocess.run(
        ["limactl", "shell", "go2", "--", "bash", "-lc", script],
        capture_output=True,
        text=True,
        timeout=40,
    )


def pose_loop():
    cmd = [
        "limactl",
        "shell",
        "go2",
        "--",
        "bash",
        "-lc",
        f"source {GUEST_ENV} && python3 -u {POSE}",
    ]
    while True:
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                data = json.loads(line)
                data["ok"] = True
                data["wall"] = time.time()
                with lock:
                    latest.clear()
                    latest.update(data)
            proc.wait(timeout=2)
        except Exception as exc:
            with lock:
                latest["ok"] = False
                latest["error"] = str(exc)
        time.sleep(1)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read(self):
        n = int(self.headers.get("Content-Length", "0"))
        if n > 4096:
            raise ValueError("body too large")
        if n == 0:
            return {}
        return json.loads(self.rfile.read(n))

    def do_GET(self):
        if self.path == "/api/pose":
            with lock:
                body = dict(latest)
            wall = body.get("wall")
            if wall:
                body["age"] = round(time.time() - wall, 2)
            self._json(200, body)
            return
        if self.path != "/":
            self.send_error(404)
            return
        raw = HTML.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path not in ("/api/goal", "/api/stop"):
            self.send_error(404)
            return
        if not send_lock.acquire(blocking=False):
            self._json(409, {"ok": False, "error": "busy, wait for the last command"})
            return
        try:
            if self.path == "/api/stop":
                result = guest(f"source {GUEST_ENV} && python3 {STOP}")
                ok = result.returncode == 0
                self._json(
                    200 if ok else 500,
                    {"ok": ok, "error": "" if ok else (result.stderr or result.stdout)[-400:]},
                )
                return
            body = self._read()
            x, y = check_goal(body.get("x"), body.get("y"))
            result = guest(f"source {GUEST_ENV} && python3 {GOAL} {x:.3f} {y:.3f}")
            ok = result.returncode == 0
            self._json(
                200 if ok else 500,
                {
                    "ok": ok,
                    "x": x,
                    "y": y,
                    "error": "" if ok else (result.stderr or result.stdout)[-400:],
                },
            )
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except subprocess.TimeoutExpired:
            self._json(504, {"ok": False, "error": "the virtual machine did not answer"})
        finally:
            send_lock.release()


def main():
    _self_check()
    threading.Thread(target=pose_loop, daemon=True).start()
    server = None
    for port in (PORT, PORT + 1):
        try:
            server = ThreadingHTTPServer((HOST, port), Handler)
        except OSError:
            continue
        print(f"http://{HOST}:{port}", flush=True)
        break
    if server is None:
        raise SystemExit(f"{PORT} and {PORT + 1} are both in use")
    server.serve_forever()


if __name__ == "__main__":
    main()
