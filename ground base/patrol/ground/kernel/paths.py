"""Repository root lookup that does not depend on the process working directory."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.kernel.faults import fault


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "patrol" / "contract.py").is_file():
            return parent
    raise fault("internal", "repository root was not found")
