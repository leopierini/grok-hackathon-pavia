"""Local console for the Tello. The page flies the drone; this process owns the link.

    .venv/bin/python -m patrol.drone.live

Then open http://127.0.0.1:8765
Use the venv interpreter: patrol loads the depth model and the video decoder.
The default local brain needs the models in models/ (see patrol/drone/local.py);
the jev brain needs OPENROUTER_API_KEY in the environment or in .env.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from patrol.drone.pilot import Pilot

ROOT = Path(__file__).resolve().parents[2]
FRAMES = ROOT / "artifacts" / "drone" / "recon"
PAGE = Path(__file__).with_name("live.html")
HOST = "127.0.0.1"
PORT = 8765
RUN_ID = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$")
FILE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
KINDS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def resolve_frame(root: Path, run_id: str, name: str) -> Path | None:
    """A photo inside one run folder, or None when the URL leaves that folder."""
    if not RUN_ID.fullmatch(run_id) or not FILE_NAME.fullmatch(name):
        return None
    folder = (root / run_id).resolve()
    file = (folder / name).resolve()
    if file.parent != folder or file.suffix.lower() not in KINDS or not file.is_file():
        return None
    return file


class Handler(BaseHTTPRequestHandler):
    pilot: Pilot
    frames: Path

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._bytes(PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/state.json":
            self._bytes(self._state(), "application/json")
            return
        if path.startswith("/frames/"):
            parts = path.removeprefix("/frames/").split("/")
            if len(parts) != 2:
                self.send_error(404)
                return
            file = resolve_frame(self.frames, parts[0], parts[1])
            if file is None:
                self.send_error(404)
                return
            self._bytes(file.read_bytes(), KINDS[file.suffix.lower()])
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != "/cmd":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 4096:
            self.send_error(413)
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._bytes(b'{"ok":false,"error":"bad json"}', "application/json")
            return
        if not isinstance(body, dict):
            self._bytes(b'{"ok":false,"error":"bad json"}', "application/json")
            return
        result = self.pilot.submit(body)
        self._bytes(json.dumps(result).encode(), "application/json")

    def _state(self) -> bytes:
        live = self.pilot.snapshot()
        if live is not None:
            return json.dumps(live).encode()
        state = self.frames / "state.json"
        if state.is_file():
            try:
                data = json.loads(state.read_bytes())
            except json.JSONDecodeError:
                data = {}
            if isinstance(data, dict):
                data["airborne"] = False
                return json.dumps(data).encode()
        return b'{"phase":"waiting","frames":[],"airborne":false,"run_id":null}'

    def _bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    FRAMES.mkdir(parents=True, exist_ok=True)
    Handler.pilot = Pilot(FRAMES)
    Handler.pilot.start()
    Handler.frames = FRAMES
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"open http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
