"""The provider stays inside its package and does not touch the drone port."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from patrol.ground.extensions.g17.implementation import SCHEMA, SLOT
from patrol.ground.extensions.g17.samples import armed_context, fixture_dir
from patrol.ground.kernel.paths import repo_root
from tests.ground.g17.support import calls_of, feature, request, run


def test_manifest_registers_the_v2_slot() -> None:
    manifest = json.loads(
        (repo_root() / "patrol" / "ground" / "extensions" / "g17" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest == {
        "schema_version": "ground-task-v2",
        "task_id": "GROUND-17",
        "slot": "feature.v2_drone_command",
        "factory": "patrol.ground.extensions.g17.implementation:create",
        "scenario_factory": "patrol.ground.extensions.g17.scenarios:cases",
    }
    assert SLOT == "feature.v2_drone_command"
    assert SCHEMA == "ground-task-v2"


def test_provider_source_does_not_import_an_sdk_or_socket() -> None:
    root = repo_root() / "patrol" / "ground" / "extensions" / "g17"
    banned = {"djitellopy", "socket", "udp", "xai_sdk", "unitree_webrtc_connect"}
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                assert module.split(".", 1)[0] not in banned
                own = "patrol.ground.extensions.g17"
                assert not (
                    module.startswith("patrol.ground.extensions.g") and not module.startswith(own)
                )
                assert module not in {"patrol.dog", "patrol.drone", "patrol.grok"}


def test_approval_does_not_append_a_device_call(tmp_path: Path) -> None:
    services, port = feature(tmp_path)

    async def body() -> None:
        before = list(calls_of(services))
        result = await port.execute(request(armed_context()))
        assert result.status == "ok"
        assert calls_of(services) == before
        assert fixture_dir().joinpath("ground-to-drone-command.json").is_file()

    run(body)
