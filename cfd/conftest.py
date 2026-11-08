"""Puts the sibling component folders on the import path for this folder's tests (modules import
each other by bare name; see car/paths.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _name in ("body", "race", "cfd", "components", "car"):
    if str(ROOT / _name) not in sys.path:
        sys.path.append(str(ROOT / _name))
