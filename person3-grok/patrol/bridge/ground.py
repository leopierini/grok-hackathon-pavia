"""Load Ayush's Ground checkers without putting ``ground base`` on ``PYTHONPATH``.

Ground and this tree both own a ``patrol`` package. Importing both through
``sys.path`` would hide one of them. These loaders use file paths only.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


@dataclass(frozen=True)
class GroundModules:
    """Loaded Ground modules and the directory they came from."""

    ground_root: Path
    dog_root: Path | None
    schema_check: ModuleType
    g16: ModuleType
    g17: ModuleType


def resolve_roots(team_repo: str | Path | None = None) -> tuple[Path, Path | None]:
    """Return ``(ground base, dog backend or None)``.

    ``PATROL_TEAM_REPO`` may be the shared repo root or the ``ground base`` directory.
    When it is unset, the parent of ``person3-grok`` is used.
    """
    if team_repo is not None:
        root = Path(team_repo).expanduser().resolve()
    else:
        env = os.environ.get("PATROL_TEAM_REPO")
        if env:
            root = Path(env).expanduser().resolve()
        else:
            root = Path(__file__).resolve().parents[3]
    ground = _ground_root(root)
    repo = ground.parent
    dog = repo / "dog backend"
    if not (dog / "patrol" / "contract.py").is_file():
        return ground, None
    return ground, dog


def load_ground(team_repo: str | Path | None = None) -> GroundModules:
    ground, dog = resolve_roots(team_repo)
    schema = _load(ground / "patrol" / "ground" / "extensions" / "g11" / "schema_check.py", "ground_g11_schema_check")
    g16 = _load(ground / "patrol" / "ground" / "extensions" / "g16" / "decide.py", "ground_g16_decide")
    g17 = _load(ground / "patrol" / "ground" / "extensions" / "g17" / "policy.py", "ground_g17_policy")
    return GroundModules(ground, dog, schema, g16, g17)


def _ground_root(root: Path) -> Path:
    direct = root / "patrol" / "ground" / "extensions" / "g16" / "decide.py"
    nested = root / "ground base" / "patrol" / "ground" / "extensions" / "g16" / "decide.py"
    if direct.is_file():
        return root
    if nested.is_file():
        return root / "ground base"
    raise FileNotFoundError(
        "PATROL_TEAM_REPO does not contain ground base/patrol/ground/extensions/g16/decide.py "
        f"(looked at {root})"
    )


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses look the class's module up in sys.modules while the class body runs.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module
