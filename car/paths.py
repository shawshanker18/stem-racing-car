"""Put the sibling parts on sys.path (repo folders side by side)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The component folders every module imports from, by bare module name (bible 0.11).
PARTS = {n: ROOT / n for n in ("body", "race", "cfd", "components")}


def add_parts() -> None:
    for p in PARTS.values():
        if p.is_dir() and str(p) not in sys.path:
            sys.path.append(str(p))


add_parts()
