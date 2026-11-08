"""compute/dispatch.py -- split a committed batch across confirmed accounts and dispatch.

    python compute/dispatch.py --part 6 --batch batches/p6-noise-20261112-1.json
Writes compute/runs/<batch_id>.json: which ids went to which account and run tag.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from gh import gh

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def weights(cfg: dict, part: int) -> dict:
    w = {}
    for acc in cfg["accounts"]:
        if f"part{part}" in acc.get("confirmed_for", {}):
            cap = acc["cap"] - (cfg["reserve_on_main"] if acc["user"] == cfg["main"] else 0)
            if cap > 0:
                w[acc["user"]] = cap
    if not w:
        raise SystemExit(f"no account confirmed for Part {part}: ask the compute question (00 section 0.7)")
    return w


def split(ids: list, w: dict) -> dict:
    """Weighted, interleaved split. Deterministic for the same inputs."""
    users = sorted(w)
    total = sum(w.values())
    exact = {u: len(ids) * w[u] / total for u in users}
    share = {u: int(exact[u]) for u in users}
    for u in sorted(users, key=lambda u: exact[u] - share[u], reverse=True)[: len(ids) - sum(share.values())]:
        share[u] += 1
    out = {u: [] for u in users}
    credit = {u: 0.0 for u in users}
    for i in ids:                       # smooth weighted round robin
        for u in users:
            credit[u] += w[u]
        u = max((u for u in users if len(out[u]) < share[u]), key=lambda u: credit[u])
        credit[u] -= total
        out[u].append(i)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--only", default=None, help="comma list of ids to (re)dispatch")
    a = ap.parse_args()
    cfg = json.loads((HERE / "accounts.json").read_text())
    batch = json.loads((ROOT / a.batch).read_text())
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", sha, a.batch],
                             capture_output=True, text=True).stdout.strip()
    if tracked != a.batch:
        raise SystemExit(f"{a.batch} is not committed at HEAD {sha}: commit and push it first")
    pushed = subprocess.run(["git", "-C", str(ROOT), "branch", "-r", "--contains", sha],
                            capture_output=True, text=True).stdout.strip()
    if not pushed:
        raise SystemExit(f"commit {sha} is not pushed: git push first")
    ids = [c["id"] for c in batch["cases"]]
    if a.only:
        ids = [int(x) for x in a.only.split(",")]
    plan = split(ids, weights(cfg, a.part))
    record = {"batch_id": batch["batch_id"], "sha": sha, "batch": a.batch, "dispatches": []}
    repo_code = "shawshanker18/stem-racing-car"
    for u, mine in plan.items():
        for k in range(0, len(mine), 256):
            chunk = mine[k:k + 256]
            if not chunk:
                continue
            tag = f"{batch['batch_id']}__{u}__{k // 256}"
            gh(u, "workflow", "run", "car.yml", "-R", f"{u}/{cfg['compute_repo_name']}",
               "-f", f"repo={repo_code}", "-f", f"sha={sha}", "-f", f"batch={a.batch}",
               "-f", f"ids={json.dumps(chunk)}", "-f", f"tag={tag}")
            record["dispatches"].append({"user": u, "tag": tag, "ids": chunk})
            print(f"{u}: {len(chunk)} cases, tag {tag}")
    runs = HERE / "runs"
    runs.mkdir(exist_ok=True)
    (runs / f"{batch['batch_id']}.json").write_text(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
