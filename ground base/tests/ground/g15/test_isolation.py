"""Scheduling does not call the network, the model, or either robot."""

from __future__ import annotations

import ast
import socket
from pathlib import Path

from patrol.ground.kernel.contracts import FeatureRequest
from patrol.ground.kernel.paths import repo_root
from tests.ground.g15.support import call, calls_of, opened, payload, run


def test_emit_does_not_call_devices_or_the_journal(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        result = await call(port, payload(built, "drone-downward-001"))
        assert result.data["outcome"] == "emitted"
        assert calls_of(built) == []
        assert built.journal.records == []
        assert result.events == ()
        encoded = str(result.data["message"])
        assert "vision.decision" not in encoded
        for name in ("run_route", "inspect", "takeoff", "land", "halt"):
            assert name not in encoded

    run(body)


def test_cancellation_and_a_stale_ticket_block_emission(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        ticket = built.kernel.authority.issue("mission-15", "vision")
        built.kernel.authority.reset_generation("recover")
        stale = await port.execute(
            FeatureRequest("stage", "schedule", ticket, payload(built, "drone-downward-001"))
        )
        assert stale.status == "blocked"
        assert stale.error is not None
        assert stale.error.code == "stale_ticket"
        built.kernel.authority.latch_cancel("operator halt")
        halted = await call(port, payload(built, "drone-downward-001"))
        assert halted.status == "blocked"
        assert halted.error is not None
        assert halted.error.code == "cancelled"
        assert calls_of(built) == []

    run(body)


def test_no_socket_is_opened(tmp_path: Path) -> None:
    async def body() -> None:
        opened_sockets = 0
        original = socket.socket.__init__

        def guarded(sock: socket.socket, *args: object, **kwargs: object) -> None:
            nonlocal opened_sockets
            opened_sockets += 1
            raise RuntimeError("vision scheduler opened a socket")

        socket.socket.__init__ = guarded  # type: ignore[method-assign]
        try:
            built, port = opened(tmp_path)
            result = await call(port, payload(built, "drone-downward-001"))
            assert result.data["outcome"] == "emitted"
            assert opened_sockets == 0
        finally:
            socket.socket.__init__ = original  # type: ignore[method-assign]

    run(body)


def test_owned_sources_do_not_import_network_or_robot_sdks() -> None:
    root = repo_root() / "patrol" / "ground" / "extensions" / "g15"
    banned = {"socket", "urllib", "http", "requests", "httpx", "djitellopy", "xai", "xai_sdk"}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                assert module.split(".", 1)[0] not in banned
