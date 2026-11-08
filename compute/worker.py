"""compute/worker.py -- run ONE case from a batch file on a compute machine.

Reads:  batches/<id>.json (path given by --batch), the case with "id" == --id
Writes: <out>/case_<id>.json  (always, even on failure)
        <out>/logs/...         (solver logs, tails only)
        <out>/ckpt/*.tar.zst   (only for kinds that checkpoint)

Kinds:
  selftest   prints machine info, runs a 1-iteration OpenFOAM tutorial-sized case
  car        builds one car with car/run_car.py and (optionally) runs CFD
  (Part 6 adds: family, morph, mesh_study; Part 7 adds: legal_only; Part 8 adds: chained)
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _case(batch_path: str, case_id: int) -> dict:
    batch = json.loads((ROOT / batch_path).read_text())
    for c in batch["cases"]:
        if c["id"] == case_id:
            return dict(c, _batch_id=batch["batch_id"])
    raise SystemExit(f"case {case_id} not in {batch_path}")


def run_selftest(case: dict, out: Path) -> dict:
    bashrc = os.environ["FOAM_BASHRC"]
    v = subprocess.run(["bash", "-lc", f"source {bashrc} && foamVersion"],
                       capture_output=True, text=True, timeout=120)
    import numpy, scipy, trimesh  # noqa: F401
    return {"foam": v.stdout.strip() or v.stderr.strip()[-200:], "python": platform.python_version(),
            "nproc": os.cpu_count()}


def run_car(case: dict, out: Path) -> dict:
    sys.path.insert(0, str(ROOT / "car"))
    import run_car as rc
    args = ["--out", str(out / "car")] + list(case["argv"])     # the batch carries run_car's argv
    S = rc.main(args)
    ci = S.get("cfd_initial") or {}
    return {"legal_failed": S["legality"]["summary"]["failed"],
            "mass_g": S["mass"].get("manufactured_mass_g"),
            "D20_N": ci.get("D20_N"), "L_N": ci.get("L_N"),
            "T_at_target_s": ci.get("T_at_target_s"), "converged": ci.get("converged"),
            "stderr": ci.get("stderr"), "drift": ci.get("drift"), "parts": ci.get("parts")}


KINDS = {"selftest": run_selftest, "car": run_car}

# More kinds register from their own files, so parallel work never edits this one:
# compute/kinds_cfd.py (Part 6: fresh, family, morph, speed, chained) and
# compute/kinds_search.py (Part 7: legal_only). Each defines KINDS = {"name": function}.
for _mod in ("kinds_cfd", "kinds_search"):
    try:
        KINDS.update(__import__(_mod).KINDS)
    except ModuleNotFoundError as _exc:
        if _exc.name != _mod:
            raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    case = _case(a.batch, a.id)
    row = {"batch_id": case["_batch_id"], "id": a.id, "kind": case["kind"], "ok": False,
           "started": time.time(), "runner": os.environ.get("RUNNER_NAME"),
           "repo": os.environ.get("GITHUB_REPOSITORY"), "run_id": os.environ.get("GITHUB_RUN_ID")}
    try:
        row["result"] = KINDS[case["kind"]](case, out)
        row["ok"] = True
    except BaseException as exc:          # noqa: BLE001 -- a failed case is a result
        row["error"] = f"{type(exc).__name__}: {exc}"[:2000]
        row["trace"] = traceback.format_exc()[-4000:]
    row["seconds"] = round(time.time() - row["started"], 1)
    (out / f"case_{a.id}.json").write_text(json.dumps(row, indent=1, default=str))
    print(json.dumps({k: row[k] for k in ("id", "ok", "seconds")}))


if __name__ == "__main__":
    main()
