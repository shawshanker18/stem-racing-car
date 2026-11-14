"""Part 4 lab: rebuild the front assembly of the three pinch cars (50135, 50250, 50323)
from their kept inputs, with the nose cut on Ref A (old) and NOSE_CUT_BACK_MM ahead of it
(new), then remesh it as run_car does. Old should reproduce the pinch; new should not."""
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(Path.cwd().parent / p) for p in ("part4-simulation", "part1-simulation")] + [str(Path.cwd())]
import trimesh

import joints
import mesh_fairing

RUNS = {"50135": 43605280301, "50250": 43605313729, "50323": 43605345488}
REPO = "shawshanker18/stem-racing-compute"          # where the kept files are


def relink(o, d):
    if isinstance(o, dict):
        return {k: relink(v, d) for k, v in o.items()}
    if isinstance(o, list):
        return [relink(v, d) for v in o]
    if isinstance(o, str) and o.startswith("/tmp/"):
        p = Path(d) / Path(o).name
        return str(p) if p.exists() else o
    return o


for car, run in RUNS.items():
    d = Path("../out/files") / car
    subprocess.run(["gh", "run", "download", str(run), "-R", REPO, "-D", str(d)], check=False)
    asm_p = glob.glob(str(d / "**" / "assembly.json"), recursive=True)[0]
    folder = Path(asm_p).parent
    asm = relink(json.loads(Path(asm_p).read_text()), folder)
    body = trimesh.load(folder / "body_half.stl", force="mesh")
    xa = asm["x_front_mm"] - 16.0
    rear = asm["x_front_mm"] + asm["W_mm"] + 16.0 + 40.0
    for label, back in (("old (cut on Ref A)", 0.0), ("new", joints.NOSE_CUT_BACK_MM)):
        joints.NOSE_CUT_BACK_MM = back
        out = Path("../out/rebuild") / car / ("old" if back == 0 else "new")
        try:
            rep = joints.make_all(body, dict(asm), xa, rear, out)
            f = rep["manufactured"]["printed_front_assembly"]["file"]
            r = mesh_fairing.remesh_file(f, 0.4)
            print(f"CAR {car} {label}: remeshed {r['remeshed']} slivers {r['faces_under_5deg_pct']:.2f} % "
                  f"closed {r['closed']} pieces {r['pieces']} cm3 {r['file_cm3']:.4f}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"CAR {car} {label}: failed {type(exc).__name__}: {str(exc)[:200]}", flush=True)
