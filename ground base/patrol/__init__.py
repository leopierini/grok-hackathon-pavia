"""Robot Patrol package.

Importing this module does not import device adapters or open a connection.
Sibling trees (dog, Grok, drone) are added to this package path so one
process can import ``patrol.dog``, ``patrol.grok``, and ``patrol.drone``.
"""

from pathlib import Path

__version__ = "0.1.0"


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
