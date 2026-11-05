"""The published /ws/robot/v2 route accepts one authenticated JSON frame."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from patrol.ground.operator.app import create_app
from starlette.websockets import WebSocketDisconnect

_TOKEN = "operator-token-test"
_REPO = Path(__file__).resolve().parents[4]


def test_robot_v2_accepts_a_command_and_rejects_a_missing_token(tmp_path: Path) -> None:
    app = create_app(_TOKEN, tmp_path)
    client = TestClient(app)
    with client.websocket_connect(
        "/ws/robot/v2",
        headers={"x-ground-operator-token": _TOKEN},
    ) as socket:
        socket.send_text(json.dumps({"kind": "dog.command", "payload": {"action": "halt"}}))
        reply = socket.receive_json()
    assert reply["ok"] is True
    assert reply["kind"] == "dog.command"
    assert app.state.robot_v2_messages[0]["payload"]["action"] == "halt"

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/robot/v2"):
            pass


def test_vision_v2_prints_the_published_endpoint() -> None:
    script = """
import sys
sys.path[:0] = sys.argv[1:]
from patrol.vision_v2.__main__ import main
raise SystemExit(main())
"""
    completed = subprocess.run(
        [sys.executable, "-S", "-c", script, str(_REPO / "person3-grok")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    endpoint = json.loads(completed.stdout)
    assert endpoint["host"] == "127.0.0.1"
    assert endpoint["port"] == 8765
    assert endpoint["route"] == "/ws/robot/v2"
    assert endpoint["auth_header"] == "x-ground-operator-token"
    assert endpoint["auth_env"] == "GROUND_OPERATOR_TOKEN"
