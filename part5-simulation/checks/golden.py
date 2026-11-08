"""checks/golden.py -- fingerprint a built car so a refactor can prove it changed nothing.

    python checks/golden.py fingerprint ../golden/G1 > ../golden/G1.fp.json
    python checks/golden.py compare ../golden/G1.fp.json ../golden_after/G1
Exit 0 when identical (or within tolerance for floats), 1 otherwise, with the differences printed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FLOAT_TOL = 1e-9


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def fingerprint(d: Path) -> dict:
    S = json.loads((d / "summary.json").read_text())
    fp = {"stl": {p.relative_to(d).as_posix(): _sha(p) for p in sorted(d.rglob("*.stl"))},
          "legality": {k: round(v["margin"], 9) for k, v in S["legality"]["checks"].items()},
          "failed": S["legality"]["summary"]["failed"],
          "mass_g": S["mass"].get("manufactured_mass_g"),
          "skin": (S.get("body", {}).get("build") or {}).get("skin_offset_mm")}
    if S.get("cfd_initial"):
        fp["D20_N"] = S["cfd_initial"]["D20_N"]
    return fp


def compare(a: dict, b: dict) -> list:
    diffs = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if isinstance(x, dict) and isinstance(y, dict):
            for kk in sorted(set(x) | set(y)):
                if x.get(kk) != y.get(kk) and not (
                        isinstance(x.get(kk), float) and isinstance(y.get(kk), float)
                        and abs(x[kk] - y[kk]) <= FLOAT_TOL):
                    diffs.append(f"{k}.{kk}: {x.get(kk)} -> {y.get(kk)}")
        elif x != y and not (isinstance(x, float) and isinstance(y, float) and abs(x - y) <= FLOAT_TOL):
            diffs.append(f"{k}: {x} -> {y}")
    return diffs


if __name__ == "__main__":
    if sys.argv[1] == "fingerprint":
        print(json.dumps(fingerprint(Path(sys.argv[2])), indent=1, sort_keys=True))
    else:
        d = compare(json.loads(Path(sys.argv[2]).read_text()), fingerprint(Path(sys.argv[3])))
        print("\n".join(d) or "identical")
        sys.exit(1 if d else 0)
