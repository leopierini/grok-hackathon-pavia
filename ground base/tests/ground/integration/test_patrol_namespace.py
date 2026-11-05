"""One process can see Ground, the dog, Grok, and the drone together."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_ORDERS = (
    ("person3-grok", "ground base"),
    ("ground base", "person3-grok"),
    ("person3-grok", "dog backend"),
    ("dog backend", "person3-grok"),
    ("dog backend", "person3-grok", "ground base", "."),
)


def _probe(order: tuple[str, ...]) -> None:
    roots = [str(_REPO / name) if name != "." else str(_REPO) for name in order]
    script = """
import sys
sys.path[:0] = sys.argv[1:]
import patrol.dog
import patrol.drone
import patrol.grok
import patrol.ground
from patrol.dog import create_dog
from patrol.drone import create_drone
from patrol.grok import create_reasoner
assert callable(create_dog)
assert callable(create_drone)
assert callable(create_reasoner)
"""
    completed = subprocess.run(
        [sys.executable, "-S", "-c", script, *roots],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_shared_pythonpath_imports_every_patrol_tree() -> None:
    for order in _ORDERS:
        _probe(order)


def test_dog_tree_alone_still_imports_create_dog() -> None:
    script = """
import sys
sys.path[:0] = sys.argv[1:]
from patrol.dog import create_dog
dog = create_dog(mode="fake", config={}, output_dir=".")
assert dog.__class__.__name__ == "FakeDog"
"""
    completed = subprocess.run(
        [sys.executable, "-S", "-c", script, str(_REPO / "dog backend")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
