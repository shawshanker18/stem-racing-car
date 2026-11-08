"""measure/record.py -- write one measured value into inputs/measured.json with its provenance.

    from record import record
    record("charge_mass_g", 7.95, sd=0.06, n=8, source="inputs/raw/M2_cartridge_mass/2026-11-12")

Only measure/*.py scripts (and the agent processing a raw folder) call this. See bible Part 3.13.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

INPUTS = Path(__file__).resolve().parent.parent / "inputs" / "measured.json"


def record(key: str, value, sd=None, n: int = 1, source: str = "", path: Path = INPUTS) -> dict:
    d = json.loads(path.read_text())
    if key not in d:
        raise KeyError(f"{key} is not an input in {path.name}; add it to the schema first (bible 3.13)")
    entry = dict(d[key], value=value, sd=sd, n=n, source=source, measured=True,
                 date=datetime.date.today().isoformat())
    d[key] = entry
    path.write_text(json.dumps(d, indent=1) + "\n")
    return entry


def unmeasured(path: Path = INPUTS) -> list:
    d = json.loads(path.read_text())
    return sorted(k for k, v in d.items() if isinstance(v, dict) and not v.get("measured"))
