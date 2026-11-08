"""compute/gh.py -- run gh as a given account (its token in GH_TOKEN for one call)."""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache


@lru_cache(maxsize=None)
def token(user: str) -> str:
    out = subprocess.run(["gh", "auth", "token", "--user", user], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit(f"{user} is not logged in to gh on this machine: see Part 1 section 1.4")
    return out.stdout.strip()


def gh(user: str, *args: str, check: bool = True, json_out: bool = False):
    env = dict(os.environ, GH_TOKEN=token(user))
    p = subprocess.run(["gh", *args], capture_output=True, text=True, env=env)
    if check and p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} as {user} failed: {p.stderr.strip()[:500]}")
    return json.loads(p.stdout or "null") if json_out else p.stdout
