"""Person 3 packages (Grok, vision v2, presence trigger, Ground bridge).

Importing this package does not open a socket or call xAI.
The package path also includes Ground, the dog, and the drone so a shared
``PYTHONPATH`` does not hide ``patrol.ground`` or ``patrol.dog``.
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
