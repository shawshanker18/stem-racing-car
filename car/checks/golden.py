"""checks/golden.py -- fingerprint a built car so a refactor can prove it changed nothing.

    python checks/golden.py fingerprint ../golden/G1 > ../golden/G1.fp.json
    python checks/golden.py compare ../golden/G1.fp.json ../golden_after/G1
Exit 0 when the car is the same, 1 otherwise, with the differences printed.

"The same" means: every manufacturing STL has the same volume, area and bounds (relative
1e-4: the remesher's output differs in the 6th digit between Windows and Linux, measured
2e-6 in volume and 2e-5 in area on the front assembly), every legality margin agrees to
1e-6 mm, the same rules fail, and the mass agrees to 1e-6 g. File hashes are recorded too; on one machine they are identical, but across operating
systems the last bits of a vertex can differ without changing the car, so hashes alone would
fail a correct build.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

TOL = 1e-6
STL_REL_TOL = 1e-4


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _geom(p: Path) -> list:
    import trimesh
    m = trimesh.load(str(p), force="mesh")
    return [float(abs(m.volume)), float(m.area)] + [float(x) for x in m.bounds.ravel()]


def fingerprint(d: Path) -> dict:
    S = json.loads((d / "summary.json").read_text())
    stls = sorted(p for p in d.rglob("*.stl") if "gates" not in p.parts)
    fp = {"stl_sha": {p.relative_to(d).as_posix(): _sha(p) for p in stls},
          "stl_geom": {p.relative_to(d).as_posix(): _geom(p) for p in stls},
          "legality": {k: v["margin"] for k, v in S["legality"]["checks"].items()},
          "failed": sorted(S["legality"]["summary"]["failed"]),
          "mass_g": S["mass"].get("manufactured_mass_g"),
          "skin": (S.get("body", {}).get("build") or {}).get("skin_offset_mm")}
    if S.get("cfd_initial"):
        fp["D20_N"] = S["cfd_initial"]["D20_N"]
    return fp


def _close(x, y, rel=False) -> bool:
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return abs(x - y) <= (STL_REL_TOL * max(abs(x), abs(y), 1e-12) if rel else TOL)
    if isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
        return all(_close(a, b, rel) for a, b in zip(x, y))
    return x == y


def compare(a: dict, b: dict) -> list:
    diffs = []
    for k in sorted(set(a) | set(b)):
        if k == "stl_sha":
            continue                                   # informational: see the module docstring
        x, y = a.get(k), b.get(k)
        if isinstance(x, dict) and isinstance(y, dict):
            for kk in sorted(set(x) | set(y)):
                if not _close(x.get(kk), y.get(kk), rel=(k == "stl_geom")):
                    diffs.append(f"{k}.{kk}: {x.get(kk)} -> {y.get(kk)}")
        elif not _close(x, y):
            diffs.append(f"{k}: {x} -> {y}")
    return diffs


if __name__ == "__main__":
    if sys.argv[1] == "fingerprint":
        print(json.dumps(fingerprint(Path(sys.argv[2])), indent=1, sort_keys=True))
    else:
        d = compare(json.loads(Path(sys.argv[2]).read_text()), fingerprint(Path(sys.argv[3])))
        print("\n".join(d) or "same car")
        sys.exit(1 if d else 0)
