"""Put the repo root on sys.path so bare `pytest` can import the `patrol` namespace package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
