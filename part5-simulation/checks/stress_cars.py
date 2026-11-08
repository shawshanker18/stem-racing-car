"""
stress_cars.py -- can the car builder make whatever the solver asks for?

Builds random cars across the whole range of every search setting, with no CFD,
and records for each one whether it built and which rules it broke. Any setting
the solver can choose must give a legal, closed car, or fail with a clear reason.

    python checks/stress_cars.py --seed 0 --n 10 --out results/
    python checks/stress_cars.py --summary results/

Cars are built at one fixed skin, not sized, so T3.6 (mass) is ignored here. What this
measures is BUILDER ROBUSTNESS at a fixed skin (does every setting give a closed car that the
rule checks can judge), not the legality rate of sized cars. The old "carve" mode was removed
with the carving method (docs/HISTORY.md).
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import random
import shutil
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import space  # noqa: E402

SETTINGS = None     # set in main: needs Part 1 on the path
FIXED_SKIN_MM = "2.5"
IGNORED = {"T3.6_mass"}
# A car normally takes 75-100 s and well under 8 GB. Past these it is stopped and reported:
# machines 1, 3 and 8 died or hung round after round, taking all their cars' results along.
CAR_LIMIT_S = 900
CAR_LIMIT_GB = 12.0


def _rss_gb(pid: int) -> float:
    try:
        return int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * 4096 / 1e9
    except (OSError, IndexError, ValueError):       # not Linux, or it has just ended
        return 0.0


def guarded(target, args: tuple, limit_s: float, limit_gb: float, poll_s: float = 1.0) -> tuple:
    """Run target(*args) in its own process. ("ok" | "over time" | "over memory" | "died (exit N)", peak GB)."""
    ctx = mp.get_context("fork" if hasattr(os, "fork") else "spawn")
    p = ctx.Process(target=target, args=args)
    p.start()
    t0, peak, state = time.time(), 0.0, None
    while p.is_alive():
        peak = max(peak, _rss_gb(p.pid))
        if peak > limit_gb:
            state = "over memory"
        elif time.time() - t0 > limit_s:
            state = "over time"
        if state:
            p.kill()
            p.join()
            return state, round(peak, 2)
        p.join(poll_s)
    return ("ok" if p.exitcode == 0 else f"died (exit {p.exitcode})"), round(peak, 2)


def random_car(rng: random.Random, share: float) -> dict:
    """A car with `share` of its settings drawn uniformly across their full range."""
    import param_body as pb
    d = {"params": pb.BodyParams().as_dict(), "parts": {}}
    moved = {}
    for name in SETTINGS:
        if rng.random() < share:
            lo, hi = space.bounds(name)
            value = rng.uniform(lo, hi)
            d = space.put(d, name, value)
            moved[name] = value
    # The car's layout as well: the solver has to be free to choose these too.
    layout = {}
    if rng.random() < share:
        layout["W"] = rng.uniform(120.3, 140.0)
    if rng.random() < share:
        layout["x_front"] = rng.uniform(46.0, 56.0)
    if rng.random() < share:
        layout["d_halo"] = rng.uniform(25.0, 75.0)
    moved.update(layout)
    return {"car": d, "moved": moved, "layout": layout}


def build_one(c: dict) -> dict:
    import run_car as rc
    out = Path(tempfile.mkdtemp())
    args = ["--out", str(out), "--skin-mm", FIXED_SKIN_MM, "--support", "beam",
            "--body-json", json.dumps(c["car"]["params"])]
    for key, flag in (("W", "--W"), ("x_front", "--x-front"), ("d_halo", "--d-halo")):
        if key in c.get("layout", {}):
            args += [flag, str(c["layout"][key])]
    for part, flag in space.PART_FLAGS.items():
        if c["car"]["parts"].get(part):
            args += [flag, json.dumps(c["car"]["parts"][part])]
    t0 = time.time()
    row = {"moved": c["moved"], "car": c["car"], "layout": c.get("layout", {})}
    try:
        S = rc.main(args)
        row["failed"] = [k for k in S["legality"]["summary"]["failed"] if k not in IGNORED]
        row["notes"] = {k: S["legality"]["checks"][k]["note"][:80] for k in row["failed"]}
        row["mass_g"] = S["mass"].get("manufactured_mass_g")
        row["status"] = "legal" if not row["failed"] else "illegal"
    except (Exception, SystemExit) as exc:  # noqa: BLE001 -- a car that will not build is the result
        row["status"] = "illegal" if str(exc).startswith("illegal car") else "crash"
        row["failed"], row["notes"] = (["no_nose_root"], {"no_nose_root": str(exc)[:80]}) if row["status"] == "illegal" else ([], {})
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        row["where"] = traceback.format_exc().strip().splitlines()[-3][:160]
    row["seconds"] = round(time.time() - t0, 1)
    shutil.rmtree(out, ignore_errors=True)
    return row


def _describe(c: dict) -> None:
    """One car in the open: what each file it wrote is, on this machine."""
    import numpy as np
    import run_car as rc
    import trimesh
    args = ["--out", tempfile.mkdtemp(), "--skin-mm", FIXED_SKIN_MM, "--support", "beam",
            "--body-json", json.dumps(c["car"]["params"])]
    for key, flag in (("W", "--W"), ("x_front", "--x-front"), ("d_halo", "--d-halo")):
        if key in c.get("layout", {}):
            args += [flag, str(c["layout"][key])]
    for part, flag in space.PART_FLAGS.items():
        if c["car"]["parts"].get(part):
            args += [flag, json.dumps(c["car"]["parts"][part])]
    S = rc.main(args)
    print("car failed:", S["legality"]["summary"]["failed"], flush=True)
    for k in S["legality"]["summary"]["failed"]:
        print(f"car   {k}: {S['legality']['checks'].get(k, {}).get('note')}", flush=True)
    for k, v in S["manufactured"].items():
        if "file" in v:
            m = trimesh.load(v["file"], force="mesh")
            _, n = np.unique(m.edges_sorted, axis=0, return_counts=True)
            print(f"car file {k}: watertight {m.is_watertight} winding {m.is_winding_consistent} volume {m.is_volume} "
                  f"cm3 {float(m.volume) / 1e3:.3f} pieces {len(m.split(only_watertight=False))} expected "
                  f"{v.get('pieces_expected')} bad_edges {(n != 2).sum()} faces {len(m.faces)} reported {v.get('closed')} "
                  f"remeshed {v.get('remeshed')} max_edge {v.get('max_edge_mm')} edge_face_counts "
                  f"{dict(zip(*np.unique(n[n != 2], return_counts=True)))}", flush=True)
            if k == "machined_body":
                import legality as lg
                rf = S.get("layout", {}).get("rear_face_mm")
                mm = m.copy()
                mm.apply_scale(1e-3)             # the file is in mm, the check works in metres
                print(f"car   machined_body bounds {np.round(m.bounds, 1).tolist()}, T5.5 at its own rear face "
                      f"{lg.t55_wall_fraction(mm, rear_face_mm=float(m.bounds[1, 0])):.3f}, layout rear face {rf}, "
                      f"T5.5 note {S['legality']['checks'].get('T5.5_wall', {}).get('note')}", flush=True)
            for p in sorted(m.split(only_watertight=False), key=lambda p: -abs(p.volume))[1:6]:
                print(f"car   extra piece of {k}: {abs(p.volume):.1f} mm3, bounds {np.round(p.bounds, 1).tolist()}", flush=True)


def _build_and_write(c: dict, path: Path) -> None:
    path.write_text(json.dumps(build_one(c), indent=1, default=str))


def summary(root: Path) -> dict:
    rows = [json.loads(p.read_text()) for p in root.rglob("car_*.json")]
    status = Counter(r["status"] for r in rows)
    rules, crashes, blamed = Counter(), Counter(), Counter()
    for r in rows:
        rules.update(r.get("failed", []))
        if r["status"] == "crash":
            crashes[r["error"][:110]] += 1
        if r["status"] != "legal":
            blamed.update(r["moved"].keys())
    print(f"{len(rows)} cars: {dict(status)}")
    print("\nRules broken:")
    for k, n in rules.most_common(25):
        print(f"  {n:4d}  {k}")
    print("\nCrashes:")
    for k, n in crashes.most_common(15):
        print(f"  {n:4d}  {k}")
    # A setting moved in bad cars far more often than in good ones points at the cause.
    good = Counter()
    for r in rows:
        if r["status"] == "legal":
            good.update(r["moved"].keys())
    n_bad = max(sum(1 for r in rows if r["status"] != "legal"), 1)
    n_good = max(status["legal"], 1)
    lift = sorted(((blamed[k] / n_bad - good[k] / n_good, k) for k in blamed), reverse=True)
    print("\nSettings most linked to bad cars:")
    for d, k in lift[:12]:
        print(f"  {d:+.2f}  {k}")
    return dict(status)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default="stress")
    ap.add_argument("--summary", default=None)
    ap.add_argument("--only", type=int, default=None, help="rebuild just this car of the seed, and describe its files")
    a = ap.parse_args()
    if a.summary:
        summary(Path(a.summary))
        return
    global SETTINGS
    import param_body as pb
    SETTINGS = (space.LOFT + [f"mode{i}" for i in range(pb.N_MODES)] + list(space.FLOOR)
                + list(space.PARTS))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)
    for i in range(a.n if a.only is None else a.only + 1):
        # From a few settings moved to all of them: failures from one setting alone
        # are easy to trace, and only all of them together reach the far corners.
        c = random_car(rng, rng.choice((0.05, 0.2, 0.5, 1.0)))
        if a.only is not None:
            if i == a.only:
                _describe(c)
            continue
        path = out / f"car_{a.seed}_{i}.json"
        t0 = time.time()
        state, peak = guarded(_build_and_write, (c, path), CAR_LIMIT_S, CAR_LIMIT_GB)
        if state == "ok":
            row = json.loads(path.read_text())
        else:
            row = {"moved": c["moved"], "car": c["car"], "layout": c.get("layout", {}), "status": "crash",
                   "failed": [], "notes": {}, "error": f"stopped: {state}", "seconds": round(time.time() - t0, 1)}
        row["peak_gb"] = peak
        path.write_text(json.dumps(row, indent=1, default=str))
        print(f"car {a.seed}/{i}: {row['status']} {row.get('failed', row.get('error', ''))} "
              f"({len(c['moved'])} moved, {row['seconds']} s, {peak} GB)", flush=True)


if __name__ == "__main__":
    main()
