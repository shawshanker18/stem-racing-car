"""compute/collect.py -- wait for a batch, download every result, append results/db.jsonl.

    python compute/collect.py --batch-id p6-noise-20261112-1 [--wait]
Exit code 0 when every id has a case JSON; 2 when some are missing (re-dispatch those
with dispatch.py --only ...); prints the missing ids.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from gh import gh

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
POLL_S = 300


def run_for(user: str, repo: str, tag: str):
    rows = gh(user, "run", "list", "-R", repo, "-w", "car.yml", "-L", "100",
              "--json", "databaseId,displayTitle,status,conclusion", json_out=True)
    hits = [r for r in rows if r["displayTitle"] == tag]
    return hits[0] if hits else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--wait", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((HERE / "accounts.json").read_text())
    rec = json.loads((HERE / "runs" / f"{a.batch_id}.json").read_text())
    dest = ROOT / "results" / "raw" / a.batch_id
    dest.mkdir(parents=True, exist_ok=True)
    while True:
        pending = []
        for d in rec["dispatches"]:
            repo = f"{d['user']}/{cfg['compute_repo_name']}"
            r = run_for(d["user"], repo, d["tag"])
            if r is None or r["status"] != "completed":
                pending.append(d["tag"])
                continue
            if d.get("downloaded"):
                continue
            tmp = Path(tempfile.mkdtemp())
            gh(d["user"], "run", "download", str(r["databaseId"]), "-R", repo, "-D", str(tmp),
               "-p", "result-*", check=False)
            for f in tmp.rglob("case_*.json"):
                shutil.copy2(f, dest / f.name)
            d["downloaded"] = True
            d["run_id"] = r["databaseId"]
            d["conclusion"] = r["conclusion"]
        (HERE / "runs" / f"{a.batch_id}.json").write_text(json.dumps(rec, indent=1))
        if not pending or not a.wait:
            break
        print(f"{len(pending)} runs still going; next check in {POLL_S // 60} min")
        time.sleep(POLL_S)
    want = {i for d in rec["dispatches"] for i in d["ids"]}
    have = {int(p.stem.split("_")[1]) for p in dest.glob("case_*.json")}
    db = ROOT / "results" / "db.jsonl"
    seen = set()
    if db.exists():
        seen = {(json.loads(l)["batch_id"], json.loads(l)["id"]) for l in db.read_text().splitlines() if l.strip()}
    with db.open("a") as fh:
        for p in sorted(dest.glob("case_*.json")):
            row = json.loads(p.read_text())
            row.pop("trace", None) if row.get("ok") else None
            if (row["batch_id"], row["id"]) not in seen:
                fh.write(json.dumps(row, default=str) + "\n")
    missing = sorted(want - have)
    print(f"{len(have)}/{len(want)} results; missing: {missing}")
    raise SystemExit(0 if not missing else 2)


if __name__ == "__main__":
    main()
