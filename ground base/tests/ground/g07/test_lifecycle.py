"""Ctrl+C, EOF, and the Windows input path."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from patrol.ground.extensions.g07.implementation import create
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services, service_ports


def test_interrupt_and_eof_are_typed_lifecycle_events(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=3, output_dir=tmp_path)
        console = create(services.kernel, service_ports(services))

        def boom(_message: str) -> None:
            raise RuntimeError("renderer down")

        console.set_writer(boom)
        await console.submit_signal("interrupt")
        assert services.kernel.authority.cancelled is True
        assert "renderer:isolated" in console.trace
        services.kernel.authority.reset_generation("console test recovery")
        await console.submit_signal("eof")
        sources = [event.payload.get("source") for event in console.events]
        kinds = [event.kind for event in console.events]
        assert "ctrl-c" in sources
        assert "eof" in sources
        assert "halt_requested" in kinds
        assert "shutdown_requested" in kinds
        await console.close()
        await console.close()
        assert services.kernel.tasks.pending() == ()

    asyncio.run(body())


def test_input_error_is_recorded_without_a_worker_thread(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=3, output_dir=tmp_path)
        console = create(services.kernel, service_ports(services))
        await console.submit_signal("input-error")
        assert console.input_errors == 1
        assert "input:error" in console.trace
        assert services.adapters.devices.calls == []
        await console.close()

    asyncio.run(body())


def test_default_windows_path_does_not_use_unix_console_apis() -> None:
    root = repo_root() / "patrol" / "ground" / "extensions" / "g07"
    banned_calls = {"add_reader", "add_signal_handler"}
    banned_modules = {"termios", "tty"}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".", 1)[0]]
            else:
                modules = []
            assert banned_modules.isdisjoint(modules)
            if isinstance(node, ast.Attribute) and node.attr in banned_calls:
                pytest.fail(f"{path.name} references {node.attr}")
