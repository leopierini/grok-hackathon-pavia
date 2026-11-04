"""Offline quality gate for one task's owned files. This command does not edit source."""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.loader import normalize_task
from patrol.ground.kernel.paths import repo_root

_BANNED = {
    "djitellopy",
    "unitree_webrtc_connect",
    "go2_webrtc_connect",
    "xai_sdk",
    "xai",
    "requests",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m patrol.ground.quality")
    parser.add_argument("--task", required=True)
    args = parser.parse_args(argv)
    try:
        files = owned_python(args.task)
    except GroundFault as exc:
        print(f"{exc.error.code}: {exc.error.detail}", file=sys.stderr)
        return 1
    if not files:
        print("quality failed: no owned Python files", file=sys.stderr)
        return 1
    number = normalize_task(args.task)
    boundary = import_boundary(files, number)
    ruff = _tool("ruff", ["check", *files])
    typed = [path for path in files if "tests" not in Path(path).parts]
    mypy = _tool("mypy", [*typed])
    if boundary or ruff.returncode or mypy.returncode:
        return 1
    print(f"quality passed for task {number}: {len(files)} file(s)")
    return 0


def owned_python(task: str) -> list[str]:
    number = normalize_task(task)
    root = repo_root()
    candidates = [
        root / "patrol" / "ground" / "extensions" / f"g{number}",
        root / "tests" / "ground" / f"g{number}",
    ]
    if number == "01":
        candidates.extend(
            [
                root / "patrol" / "__init__.py",
                root / "patrol" / "contract.py",
                root / "patrol" / "ground" / "__init__.py",
                root / "patrol" / "ground" / "__main__.py",
                root / "patrol" / "ground" / "sim.py",
                root / "patrol" / "ground" / "quality.py",
                root / "patrol" / "ground" / "kernel",
                root / "patrol" / "ground" / "testing",
                root / "patrol" / "ground" / "extensions" / "__init__.py",
            ]
        )
    files: list[Path] = []
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix == ".py":
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(path for path in sorted(candidate.rglob("*.py")) if path.is_file())
    return [str(path) for path in files]


def import_boundary(files: list[str], number: str) -> bool:
    failed = False
    own = f"patrol.ground.extensions.g{number}"
    for name in files:
        path = Path(name)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                root_name = module.split(".", 1)[0]
                if root_name in _BANNED or module in _BANNED:
                    print(f"import boundary: {path} imports {module}", file=sys.stderr)
                    failed = True
                if module.startswith("patrol.ground.extensions.g") and not module.startswith(own):
                    print(f"import boundary: {path} imports {module}", file=sys.stderr)
                    failed = True
                if module in {"patrol.dog", "patrol.drone", "patrol.grok"} or module.startswith(
                    ("patrol.dog.", "patrol.drone.", "patrol.grok.")
                ):
                    print(f"import boundary: {path} imports {module}", file=sys.stderr)
                    failed = True
    return failed


def _tool(name: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", name, *args],
        check=False,
        text=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
