"""Patrol package. Adapters are imported from their own subpackages.

The package path also includes Ground, the dog, and Grok so one process can
import ``patrol.ground``, ``patrol.dog``, and ``patrol.grok``.
"""

from pathlib import Path


def _share_patrol_trees() -> None:
    here = Path(__file__).resolve().parent
    for parent in here.parents:
        portions = (
            parent / "ground base" / "patrol",
            parent / "dog backend" / "patrol",
            parent / "person3-grok" / "patrol",
            parent / "patrol",
        )
        drone = parent / "patrol" / "drone"
        if all(path.is_dir() for path in portions) and drone.is_dir():
            for path in portions:
                entry = str(path)
                if entry not in __path__:
                    __path__.append(entry)
            return


_share_patrol_trees()
