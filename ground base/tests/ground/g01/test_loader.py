"""Manifest ownership, schema, and fail-closed provider lookup."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from patrol.ground.extensions.g01.implementation import _write_extension
from patrol.ground.kernel import (
    SCHEMA_VERSION,
    GroundFault,
    absence_enables_hardware,
    discover,
    live_motion_allowed,
    missing_mandatory,
)
from patrol.ground.kernel.build import build_kernel
from patrol.ground.kernel.catalog import SLOT_SPECS
from patrol.ground.kernel.paths import repo_root


def test_real_foundation_manifest_loads() -> None:
    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="01")
    assert len(found) == 1
    manifest = found[0]
    assert manifest.slot == "kernel.foundation"
    assert manifest.schema_version == SCHEMA_VERSION
    assert manifest.task_id == "GROUND-01"


def test_duplicate_slot_schema_escape_and_command(tmp_path: Path) -> None:
    _write_extension(tmp_path, "23", "feature.status", SCHEMA_VERSION)
    _write_extension(tmp_path, "24", "feature.status", SCHEMA_VERSION)
    with pytest.raises(GroundFault) as duplicate:
        discover(tmp_path)
    assert duplicate.value.error.code == "duplicate_slot"

    schema_root = tmp_path / "schema"
    _write_extension(schema_root, "23", "feature.status", "ground-task-v0")
    with pytest.raises(GroundFault) as schema:
        discover(schema_root, only_task="23")
    assert schema.value.error.code == "schema_mismatch"

    escape_root = tmp_path / "escape"
    _write_extension(
        escape_root,
        "23",
        "feature.status",
        SCHEMA_VERSION,
        factory="patrol.ground.extensions.g99.implementation:create",
    )
    with pytest.raises(GroundFault) as escaped:
        discover(escape_root, only_task="23")
    assert escaped.value.error.code == "path_escape"

    command_root = tmp_path / "command"
    _write_extension(
        command_root,
        "23",
        "feature.status",
        SCHEMA_VERSION,
        extra={"command": "python -c print(1)"},
    )
    with pytest.raises(GroundFault) as command:
        discover(command_root, only_task="23")
    assert command.value.error.code == "forbidden_command"


def test_owner_mismatch_and_missing_provider(tmp_path: Path) -> None:
    _write_extension(tmp_path, "24", "feature.status", SCHEMA_VERSION)
    with pytest.raises(GroundFault) as mismatch:
        discover(tmp_path, only_task="24")
    assert mismatch.value.error.code == "owner_mismatch"
    kernel = build_kernel()
    with pytest.raises(GroundFault) as missing:
        kernel.features.get("feature.dispatch")
    assert missing.value.error.code == "missing_provider"


def test_optional_absence_does_not_enable_hardware() -> None:
    installed = {spec.slot for spec in SLOT_SPECS if spec.mandatory_live}
    assert "feature.network_diagnostics" not in installed
    assert absence_enables_hardware("feature.network_diagnostics") is False
    assert live_motion_allowed(installed) is False
    assert "base.safety" in missing_mandatory(set())


def test_manifest_outside_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "extensions"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "task_id": "GROUND-23",
        "slot": "feature.status",
        "factory": "patrol.ground.extensions.g23.implementation:create",
        "scenario_factory": "patrol.ground.extensions.g23.scenarios:cases",
    }
    path = outside / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    from patrol.ground.kernel.loader import parse_manifest

    with pytest.raises(GroundFault) as caught:
        parse_manifest(path, root)
    assert caught.value.error.code == "path_escape"


def test_live_command_refuses_without_v2_teammate_bridges() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "patrol.ground",
            "--dog",
            "real",
            "--drone",
            "fake",
            "--grok",
            "fake",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root(),
    )
    assert completed.returncode == 2
    assert "live operation refused" in completed.stderr
    assert "teammate transport/factory bridges" in completed.stderr
