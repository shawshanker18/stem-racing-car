"""compute/setup_compute_repos.py -- create/update <user>/stem-compute for every account.

    python compute/setup_compute_repos.py --part 1
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from dispatch import confirmed
from gh import gh

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, required=True)
    a = ap.parse_args()
    cfg = json.loads((HERE / "accounts.json").read_text())
    if "@sha256:" not in cfg["image"]:
        raise SystemExit("accounts.json 'image' must be pinned by digest (section 1.6.3)")
    wf = (HERE / "worker" / "car.yml").read_text().replace("ghcr.io/OWNER/stem-cfd@sha256:DIGEST", cfg["image"])
    readme = (HERE / "worker" / "README.md").read_text()
    name = cfg["compute_repo_name"]
    for acc in cfg["accounts"]:
        if acc["user"] not in confirmed(a.part):
            print(f"skip {acc['user']}: not confirmed for Part {a.part}")
            continue
        u, repo = acc["user"], f"{acc['user']}/{name}"
        exists = gh(u, "repo", "view", repo, "--json", "name", check=False)
        if not exists.strip():
            gh(u, "repo", "create", repo, "--public", "--description",
               "Compute runner for shawshanker18/stem-racing-car (workflow only)")
        for path, text in ((".github/workflows/car.yml", wf), ("README.md", readme)):
            cur = gh(u, "api", f"repos/{repo}/contents/{path}", check=False, json_out=False)
            sha = json.loads(cur).get("sha") if cur.strip().startswith("{") else None
            args = ["api", "-X", "PUT", f"repos/{repo}/contents/{path}",
                    "-f", f"message=Update {path}",
                    "-f", f"content={base64.b64encode(text.encode()).decode()}"]
            if sha:
                args += ["-f", f"sha={sha}"]
            gh(u, *args)
        # Actions must be enabled and allowed to run any action (checkout, upload-artifact)
        gh(u, "api", "-X", "PUT", f"repos/{repo}/actions/permissions",
           "-F", "enabled=true", "-f", "allowed_actions=all")
        print(f"ok {repo}")


if __name__ == "__main__":
    main()
