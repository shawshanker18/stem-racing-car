# Part 1 — Compute and accounts (GitHub CLI, many team accounts)

Read `00_START_HERE.md` first. This Part builds the machinery every later Part uses to run CFD and builds on free GitHub Actions machines spread across several team members' GitHub accounts, driven entirely from the GitHub CLI (`gh`).

**Compute budget for this Part:** about 10 short test jobs per account plus one image build. Under 2 hours of wall time.

---

## 1.0 Start of Part: the compute question

Before anything else in this Part, ask the compute question from `00_START_HERE.md` section 0.7, word for word:

```
QUESTION (Part 1, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part 1?
Why I need it: I set up a compute repository and test the login for each confirmed account.
Expected load for Part 1: about 10 short test jobs per account and one image build.
```

Then:

```
QUESTION (Part 1, compute 2): Which <k> accounts? Please give the GitHub usernames,
and for each one say whether it is on GitHub Free (20 parallel jobs), Pro (40) or Team (60),
if you know. Also tell me which one is the main account that owns
shawshanker18/stem-racing-car.
```

Record the answers in `STATUS.md` as shown in section 0.7. In Part 1 every confirmed account gets set up, so later Parts only need logins checked.

---

## 1.1 What the compute is, and the limits that shape everything

| Item | Value | Consequence |
|---|---|---|
| Machine per job | GitHub-hosted `ubuntu-24.04`, 4 vCPU, 16 GB RAM, ~14 GB free disk | One car per job, MPI on 4 ranks. |
| Job time limit | 6 hours (360 min) per job | Long runs must checkpoint and chain (section 1.9). |
| Concurrent jobs per account | Free 20, Pro 40, Team 60 (Linux standard runners) | Total parallelism = sum over confirmed accounts. Queued jobs wait; they do not fail. |
| Matrix size | max 256 jobs per workflow run | Chunk large batches. |
| Minutes | Free and unlimited for standard runners on **public** repositories | Every compute repository must be public. |
| Artifact retention | default 90 days, we set 14 | Collect promptly. |
| API rate limit | 5,000 requests/hour per authenticated account | Poll every 5 minutes, not every second. |
| Workflow dispatch inputs | keep to ≤ 5 short string inputs | Batches are files in the main repository, referenced by commit SHA. |

**Terms of use.** GitHub's Actions terms allow Actions for work related to the software project in the repository. CFD for the car designed by this repository's code is that work. Each account must belong to a real team member who agreed in chat to its use. Never create accounts. Never use an account whose owner has not confirmed. GitHub can throttle heavy use without notice, so never let a deadline depend on the free farm alone (section 1.12 lists paid fallbacks for the user to decide on).

---

## 1.2 Architecture in one picture

```
           ┌──────────────────────────── main account (owner of the code) ─────────────────────────────┐
           │  shawshanker18/stem-racing-car (public)                                                   │
           │    ├── code at commit SHA                                                                 │
           │    ├── batches/<batch_id>.json           ◄── the coordinator commits the batch here       │
           │    ├── release "mesh-families" assets    ◄── base meshes for morphing (Part 6)            │
           │    └── ghcr.io/<owner>/stem-cfd image    ◄── OpenFOAM + Python, built once                │
           └───────────────────────────────────────────────────────────────────────────────────────────┘
                    ▲ checkout code + batch at SHA (public, no token needed)
                    │
 ┌──────────────────┴───────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
 │ alice/stem-compute       │  │ bob/stem-compute         │  │ carol/stem-compute       │   one per confirmed account
 │  .github/workflows/      │  │  .github/workflows/      │  │  .github/workflows/      │   (public, holds ONLY the
 │     car.yml              │  │     car.yml              │  │     car.yml              │    worker workflow)
 │  runs jobs ids [0..37]   │  │  runs ids [38..57]       │  │  runs ids [58..77]       │
 │  uploads result-<id>     │  │  uploads result-<id>     │  │  uploads result-<id>     │
 └──────────────────────────┘  └──────────────────────────┘  └──────────────────────────┘
                    ▲ gh workflow run (as that account)          │ gh run download (as that account)
                    └────────────── coordinator (this machine, compute/dispatch.py, compute/collect.py) ◄──┘
```

Why this shape:

- **Compute repositories contain only the worker workflow.** They check out the main repository at a fixed commit SHA. The main repository is public, so no token is needed to read it, and every job runs exactly the same code and batch file.
- **Each account's jobs run in a repository owned by that account**, so they count against that account's concurrency, not the main account's.
- **The coordinator is the only thing that writes** to the main repository (batches, results database). Workers only upload artifacts in their own repository. This removes the "repository as a message queue" problem (F41).

---

## 1.3 Install and check the GitHub CLI

You need `gh` version 2.40 or later (multi-account support: `gh auth switch`, `gh auth token --user`).

```bash
gh --version
```

If missing or older:

- Windows: `winget install --id GitHub.cli`
- macOS: `brew install gh`
- Ubuntu/Debian: follow https://github.com/cli/cli/blob/trunk/docs/install_linux.md

Also needed on the coordinator machine: `git`, Python 3.11+, `zstd` (for mesh tarballs).

---

## 1.4 Logging in every confirmed account (the owner approves on their own device)

For each username from the compute question that `gh auth status` does not list:

1. Tell the user:

   ```
   To add <username>, please run this in your own terminal on this machine:

       gh auth login --hostname github.com --git-protocol https --web --scopes workflow

   It prints an 8-character code and a URL (https://github.com/login/device).
   <username>'s owner opens that URL in a browser where THEY are signed in as <username>,
   types the code, and approves. Nobody shares a password. Tell me when it says
   "Logged in as <username>".
   ```

   The `workflow` scope is required: without it, `gh` cannot create or update files under `.github/workflows/` in that account's compute repository.

2. When the user says it is done, verify:

   ```bash
   gh auth status
   ```

   Every confirmed username must appear, each with the `workflow` scope listed in its token scopes. If a scope is missing:

   ```bash
   gh auth switch --user <username>
   gh auth refresh --hostname github.com --scopes workflow
   ```

3. Switch back to the main account when done:

   ```bash
   gh auth switch --user <main_username>
   ```

**Alternative if the owner cannot do the device flow:** the owner creates a fine-grained personal access token on their own account (Settings → Developer settings → Fine-grained tokens), limited to the single repository `<username>/stem-compute` (create it first, empty, public), with permissions Actions: read and write, Contents: read and write, Workflows: read and write, Metadata: read. The owner types it into this machine's terminal themselves:

```bash
gh auth login --hostname github.com --with-token   # the owner pastes the token at the prompt
```

Never ask for the token in chat. Never write it to a file. Never commit it.

**How every later command runs as a given account** — never by switching the active account in a loop (that is slow and races), always by passing that account's token for one command:

```bash
as_user() {                 # usage: as_user alice gh repo view alice/stem-compute
  local u="$1"; shift
  GH_TOKEN="$(gh auth token --user "$u")" "$@"
}
```

The Python scripts in this Part do the same with `subprocess` and an environment variable.

---

## 1.5 Files this Part creates in the main repository

```
compute/
  accounts.json              # who, cap, role; NO tokens
  worker/car.yml             # template of the worker workflow, copied into each compute repo
  worker/README.md           # one paragraph: what this repo is, who to ask
  setup_compute_repos.py     # creates/updates <user>/stem-compute for every account
  dispatch.py                # splits a batch across accounts and dispatches
  collect.py                 # waits, downloads artifacts, appends results/db.jsonl
  gh.py                      # tiny wrapper: run gh as a user, parse JSON
  tests/test_split.py        # the job-splitting test
docker/
  Dockerfile                 # OpenFOAM v2412 + Python deps, pinned
  requirements.lock          # exact Python package versions
.github/workflows/
  image.yml                  # builds and pushes ghcr.io/<owner>/stem-cfd
tools/
  worker.py                  # the single entry point every job runs
batches/                     # one JSON file per batch, committed by the coordinator
results/db.jsonl             # one line per finished case, appended by collect.py
```

### 1.5.1 `compute/accounts.json`

```json
{
  "main": "shawshanker18",
  "image": "ghcr.io/shawshanker18/stem-cfd@sha256:<digest filled in by section 1.6>",
  "compute_repo_name": "stem-compute",
  "reserve_on_main": 2,
  "accounts": [
    {"user": "shawshanker18", "plan": "pro",  "cap": 40, "confirmed_for": {"part1": "2026-11-09"}},
    {"user": "alice-example", "plan": "free", "cap": 20, "confirmed_for": {"part1": "2026-11-09"}}
  ]
}
```

`confirmed_for` records, per Part, the date the user confirmed this account. `dispatch.py` refuses to use an account that is not confirmed for the current Part (pass `--part N`). This enforces the per-Part question mechanically.

---

## 1.6 The container image (fixes F40: no more apt install per job)

Every job today spends 5-10 minutes installing OpenFOAM and Python packages and sometimes fails on apt mirrors. Build one image, push it once, pin it by digest.

### 1.6.1 Pin the Python packages

On a working environment (a tests job, or locally after `pip install` of the current `PY_DEPS` line from `tests.yml`):

```bash
python -m pip freeze --exclude-editable > docker/requirements.lock
```

Check the lock contains at least: numpy, scipy, pandas, trimesh, scikit-image, shapely, rtree, mapbox-earcut, manifold3d, fast_simplification, jax, jaxlib, matplotlib, pymeshlab, scikit-learn (add scikit-learn now; Part 7 needs it), pytest. Every line must be `name==version`.

### 1.6.2 `docker/Dockerfile`

```dockerfile
# OpenFOAM v2412 (ESI/OpenCFD) + the project's Python stack, pinned.
FROM opencfd/openfoam-default:2412

USER root
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git zstd \
      libgl1 libglu1-mesa libegl1 libopengl0 libgomp1 libxkbcommon0 \
 && rm -rf /var/lib/apt/lists/*

# Python 3.11 via uv, independent of the base image's system Python
# (numpy 2.4 needs >= 3.11; the base image's python3 may be older).
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
 && uv python install 3.11 \
 && uv venv -p 3.11 /opt/venv
COPY docker/requirements.lock /tmp/requirements.lock
RUN uv pip install --python /opt/venv/bin/python --no-cache -r /tmp/requirements.lock

ENV PATH=/opt/venv/bin:$PATH \
    FOAM_BASHRC=/usr/lib/openfoam/openfoam2412/etc/bashrc \
    OMPI_ALLOW_RUN_AS_ROOT=1 \
    OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 \
    OMPI_MCA_rmaps_base_oversubscribe=1 \
    OMPI_MCA_hwloc_base_use_hwthreads_as_cpus=1 \
    PYTHONUNBUFFERED=1

# Smoke test at build time: both stacks load.
RUN bash -c "source $FOAM_BASHRC && simpleFoam -help >/dev/null && snappyHexMesh -help >/dev/null" \
 && python -c "import numpy, scipy, trimesh, manifold3d, pymeshlab, jax, sklearn; print('python ok')"
```

Notes the agent must respect:

- `FOAM_BASHRC` is read by `find_openfoam_bashrc` in `part2-simulation/openfoam_case.py`, so the existing code finds OpenFOAM without changes. Verify the path inside the image with `docker run --rm opencfd/openfoam-default:2412 bash -lc 'ls /usr/lib/openfoam/'` and adjust if it differs.
- OpenMPI refuses to run as root unless the two `OMPI_ALLOW_RUN_AS_ROOT*` variables are set. GitHub job containers run as root (section 1.7 forces it), so they are required.
- If `opencfd/openfoam-default:2412` does not exist on Docker Hub when you build, check `https://hub.docker.com/r/opencfd/openfoam-default/tags` and use the 2412 tag listed there. Do not move to another OpenFOAM version without the user's approval: the adjoint and the case dictionaries were verified against v2412.

### 1.6.3 `.github/workflows/image.yml` (in the main repository)

```yaml
name: image
on:
  workflow_dispatch:
  push:
    paths: ["docker/**"]
permissions:
  contents: read
  packages: write
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        id: push
        with:
          context: .
          file: docker/Dockerfile
          push: true
          tags: ghcr.io/${{ github.repository_owner }}/stem-cfd:latest,ghcr.io/${{ github.repository_owner }}/stem-cfd:${{ github.sha }}
          labels: org.opencontainers.image.source=https://github.com/${{ github.repository }}
      - run: echo "DIGEST ${{ steps.push.outputs.digest }}" | tee -a "$GITHUB_STEP_SUMMARY"
```

Run it:

```bash
gh workflow run image.yml -R shawshanker18/stem-racing-car
gh run watch -R shawshanker18/stem-racing-car "$(gh run list -R shawshanker18/stem-racing-car -w image.yml -L 1 --json databaseId -q '.[0].databaseId')"
```

Read the digest from the run summary and write it into `compute/accounts.json` as `image` (`ghcr.io/<owner>/stem-cfd@sha256:…`). Always reference the image by digest, never by `latest`: a later rebuild must not silently change what a running search measures.

**Make the package public** (other accounts' jobs pull it without logging in). There is no reliable CLI for package visibility. Ask the user:

```
QUESTION (Part 1, step 1.6): Please open
https://github.com/users/<owner>/packages/container/stem-cfd/settings
scroll to "Danger Zone", choose "Change visibility" → Public, and confirm.
Why I need it: teammates' compute jobs pull this image without logging in.
```

Then verify from a different account:

```bash
as_user <teammate> gh api /users/<owner>/packages/container/stem-cfd --jq .visibility   # "public"
```

**Fallback if the image cannot be made public:** use `container: opencfd/openfoam-default:2412` directly in the worker and install the Python stack with uv in a first step from `docker/requirements.lock`. It costs about 2 minutes per job.

---

## 1.7 The worker workflow (copied into every `<user>/stem-compute`)

`compute/worker/car.yml`:

```yaml
name: car
run-name: ${{ inputs.tag }}            # the coordinator finds the run by this tag

on:
  workflow_dispatch:
    inputs:
      repo:  { description: "owner/name of the code repository", required: true }
      sha:   { description: "commit SHA of code + batch", required: true }
      batch: { description: "path of the batch file in that commit", required: true }
      ids:   { description: "JSON list of case ids for this run", required: true }
      tag:   { description: "unique run tag", required: true }

permissions:
  contents: read
  actions: read

jobs:
  case:
    runs-on: ubuntu-24.04
    timeout-minutes: 345               # 15 min under the 6 h limit, so the checkpoint can upload
    container:
      image: ghcr.io/OWNER/stem-cfd@sha256:DIGEST     # setup_compute_repos.py fills this in
      options: --user 0 --shm-size=2g                 # root for checkout; MPI needs shared memory
    strategy:
      fail-fast: false
      max-parallel: 256
      matrix:
        id: ${{ fromJSON(inputs.ids) }}
    steps:
      - name: Code and batch at the fixed commit
        uses: actions/checkout@v4
        with:
          repository: ${{ inputs.repo }}
          ref: ${{ inputs.sha }}
          path: code
      - name: Machine
        run: |
          echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)  nproc: $(nproc)  mem: $(free -g | awk '/Mem/{print $2}') GB"
      - name: Run the case
        working-directory: code
        run: python tools/worker.py --batch "${{ inputs.batch }}" --id ${{ matrix.id }} --out ../out
      - name: Results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: result-${{ matrix.id }}
          path: |
            out/case_*.json
            out/logs/
          retention-days: 14
          if-no-files-found: warn
      - name: Checkpoint (only cases that asked for one)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ckpt-${{ matrix.id }}
          path: out/ckpt/*.tar.zst
          retention-days: 7
          if-no-files-found: ignore
```

Rules for the worker:

- The job never pushes anything anywhere. It uploads artifacts only.
- The `Results` step runs `if: always()`, so a failed case still returns its JSON with the error. A failed car is a result.
- One matrix entry is one case. A case may contain more than one CFD solve (for example a base and two morphs); `tools/worker.py` decides.

---

## 1.8 `tools/worker.py` — the single entry point every job runs

The worker reads one case from the batch file and dispatches on `case["kind"]`. Later Parts add kinds. Part 1 implements two kinds: `selftest` and `car`.

```python
"""tools/worker.py -- run ONE case from a batch file on a compute machine.

Reads:  batches/<id>.json (path given by --batch), the case with "id" == --id
Writes: <out>/case_<id>.json  (always, even on failure)
        <out>/logs/...         (solver logs, tails only)
        <out>/ckpt/*.tar.zst   (only for kinds that checkpoint)

Kinds:
  selftest   prints machine info, runs a 1-iteration OpenFOAM tutorial-sized case
  car        builds one car with part5-simulation/run_car.py and (optionally) runs CFD
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
    sys.path.insert(0, str(ROOT / "part5-simulation"))
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
```

### 1.8.1 Batch file format (`batches/<batch_id>.json`)

```json
{
  "batch_id": "p1-selftest-20261109-1",
  "part": 1,
  "created": "2026-11-09T10:00:00Z",
  "purpose": "one selftest per account",
  "cases": [
    {"id": 0, "kind": "selftest"},
    {"id": 1, "kind": "car", "argv": ["--body-json", "{}", "--cfd", "--res", "medium", "--np", "4",
                                      "--cfd-iters", "1000", "--cfd-json", "{\"layer_overrides\":{\"nSurfaceLayers\":0}}"]}
  ]
}
```

Rules:

- `batch_id` is unique forever: `p<part>-<purpose>-<YYYYMMDD>-<n>`.
- Ids are 0..N-1, contiguous.
- The batch file is committed and pushed to the main repository **before** dispatch, and dispatch passes that commit's SHA. A batch file is never edited after dispatch; a correction is a new batch.

---

## 1.9 Checkpointing and chaining long runs (beats the 6-hour limit)

Used by Part 8 (wall-resolved meshes, unsteady averaging) and by any Part-6 study that runs long.

Mechanism:

1. A case of kind `chained` carries `"segment": k` and `"max_minutes": 320`.
2. The worker runs the solver with a wall-clock guard: OpenFOAM's controlDict `stopAt writeNow` is triggered by editing `system/controlDict` when 320 minutes have passed (a Python thread sleeps, then `sed -i 's/^stopAt .*/stopAt writeNow;/'`). OpenFOAM re-reads controlDict every time step (`runTimeModifiable yes`, the default), writes the current time, and exits cleanly.
3. The worker packs the case directory (without `processor*/` if reconstructed, or with them if the next segment continues in parallel) into `out/ckpt/<batch_id>_<id>_seg<k>.tar.zst`:

   ```bash
   tar -C run -cf - . | zstd -T0 -10 -o out/ckpt/${BATCH}_${ID}_seg${K}.tar.zst
   ```
4. The coordinator, on collecting segment k, publishes the checkpoint as a release asset on the main repository (release tag `ckpt`), then dispatches segment k+1 with `"resume_url"` pointing at it:

   ```bash
   gh release upload ckpt out/ckpt/<file> -R shawshanker18/stem-racing-car --clobber
   ```

   The next segment downloads with `curl -L -o ckpt.tar.zst "$URL"` (public release assets need no token), unpacks, sets `startFrom latestTime`, and continues.
5. Release assets are limited to 2 GB each. A 5 M-cell case with fields compresses to roughly 0.5-1.5 GB with zstd -10. If larger, drop `nut`, `yPlus` and other derived fields before packing.
6. Delete checkpoint assets when the chain finishes:

   ```bash
   gh release delete-asset ckpt <file> -R shawshanker18/stem-racing-car --yes
   ```

Base meshes for morphing (Part 6) use the same mechanism under the release tag `mesh-families`.

Create both releases once:

```bash
gh release create ckpt --title "Checkpoints (temporary)" --notes "Chained-run checkpoints. Deleted when each chain finishes." -R shawshanker18/stem-racing-car
gh release create mesh-families --title "Base meshes for morphing" --notes "One asset per mesh family (Part 6)." -R shawshanker18/stem-racing-car
```

---

## 1.10 The coordinator scripts

### 1.10.1 `compute/gh.py`

```python
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
```

### 1.10.2 `compute/setup_compute_repos.py`

Creates `<user>/stem-compute` (public) for every account and writes the worker workflow with the image digest. Idempotent: running it again updates the workflow file.

```python
"""compute/setup_compute_repos.py -- create/update <user>/stem-compute for every account.

    python compute/setup_compute_repos.py --part 1
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

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
        if f"part{a.part}" not in acc.get("confirmed_for", {}):
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
```

### 1.10.3 Splitting a batch across accounts (`compute/dispatch.py`)

The split algorithm, stated plainly:

1. Take the accounts confirmed for this Part. Each has a weight = its concurrency cap; the main account's weight is reduced by `reserve_on_main` (keeps slots free for tests and the image build).
2. Give account i a share of `round(N × w_i / Σw)` cases, then fix rounding so shares add to N (largest remainders first).
3. Hand out cases in **interleaved** order, not contiguous blocks (account 0 gets ids 0, 3, 6…; account 1 gets 1, 4, 7…), weighted. This matters: batches are ordered (for example base car first, then steps), and interleaving spreads the important early cases over all accounts so one slow account does not hold all of them.
4. Split each account's list into chunks of at most 256 ids (matrix limit); one dispatch per chunk.
5. Every dispatch gets a unique tag `<batch_id>__<user>__<chunk>`.

```python
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
```

`compute/tests/test_split.py`:

```python
from dispatch import split


def test_split_covers_every_id_once_and_respects_weights():
    ids = list(range(100))
    out = split(ids, {"a": 38, "b": 20, "c": 20})
    got = sorted(i for v in out.values() for i in v)
    assert got == ids
    assert [len(out[u]) for u in ("a", "b", "c")] == [49, 26, 25] or \
           sorted(len(v) for v in out.values()) == [25, 26, 49]
    # interleaved: the first 6 ids are not all on one account
    assert len({u for u, v in out.items() for i in v if i < 6}) >= 2


def test_split_single_account():
    assert split([0, 1, 2], {"a": 20}) == {"a": [0, 1, 2]}
```

### 1.10.4 `compute/collect.py`

```python
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
```

Notes:

- `collect.py --wait` polls every 5 minutes. Run it in the background (`run_in_background`) or in the user's terminal; never poll faster.
- A case with `"ok": false` is still collected. Its error is evidence; only a **missing** case (machine died, run cancelled) is re-dispatched.
- `results/raw/` holds the raw case JSONs; add `results/raw/` to `.gitignore` if it grows past 50 MB; `results/db.jsonl` is committed after every batch.

---

## 1.11 The Part 1 procedure, step by step

1. **Branch:** `git switch -c part1-compute`.
2. **Ask the compute question** (section 1.0). Record answers.
3. **Log in** every confirmed account (section 1.4). Verify `gh auth status`.
4. **Pin packages** and write `docker/Dockerfile` and `docker/requirements.lock` (section 1.6). Commit, push the branch, run `image.yml` against the branch:
   ```bash
   gh workflow run image.yml -R shawshanker18/stem-racing-car --ref part1-compute
   ```
   (A workflow file must exist on the default branch for `workflow_dispatch` to be available. If `image.yml` is not yet on `main`, ask the user to approve merging a pull request that only adds `image.yml`, or use the `push: paths: docker/**` trigger by pushing to a branch.)
5. **Make the package public** (ask the user). Verify from a teammate account.
6. **Write** `compute/` files and `tools/worker.py`. Run `python -m pytest compute/tests -q`.
7. **Fill** `compute/accounts.json` (no tokens). Commit.
8. **Create the compute repositories:** `python compute/setup_compute_repos.py --part 1`.
9. **Self-test batch:** a batch with one `selftest` case per account plus one `car` case per account (the start car with medium CFD, no layers, 1,000 iterations, exactly the current search settings). Commit and push it, then:
   ```bash
   python compute/dispatch.py --part 1 --batch batches/p1-selftest-<date>-1.json
   python compute/collect.py --batch-id p1-selftest-<date>-1 --wait
   ```
10. **Check the gate:**
    - every account returned its selftest with `foam` showing v2412;
    - every `car` case returned `ok: true`, `converged: true`;
    - the `D20_N` values from all accounts agree within 0.3% of each other (they are the same geometry and the same image; the review measured 0.28 ms spread across 6 machines);
    - the wall time per car case is reported (target: at least 5 minutes faster than the old apt-installing jobs).
11. **Write** the results into `STATUS.md` (per account: cap, time per car, D20) and open a pull request `Part 1: compute across team accounts (F40, F41)`. Ask the user to approve the merge.

---

## 1.12 If the free farm is not enough (the user decides; you never pay)

Present these options with prices checked on the day (prices change; look them up and say the date):

| Option | What it buys | Rough cost (check) | When it is worth it |
|---|---|---|---|
| One dedicated 16-32 core server (for example Hetzner AX-class) | Wall-resolved and unsteady confirmation runs in hours, no 6-hour chaining | about €100-200 per month | Part 8, if chaining is too slow |
| Cloud spot instance (AWS c7a/c7i, 32-64 vCPU) for bursts | Same, pay per hour | about $1-3 per hour on spot | Part 8, a few days only |
| GitHub larger runners (16-64 core) | Bigger machines in the same workflow | per-minute billing, needs a paid org | Rarely: spot instances are cheaper |
| Self-hosted runner on a team member's desktop | More cores, no 6-hour limit (5-day job limit) | free (electricity) | Any time a school or home PC is idle |

**Self-hosted runner safety rule:** never attach a self-hosted runner to a **public** repository (a fork's pull request could run code on that PC). Create a separate **private** repository `<user>/stem-compute-private` for it (self-hosted runners use no GitHub minutes, so private is free), register the runner there with the label `stem-big`, and use a copy of `car.yml` with `runs-on: [self-hosted, stem-big]`. The PC's owner registers the runner themselves from the repository's Settings → Actions → Runners page.

Ask before any of this:

```
QUESTION (Part 1, step 1.12): The free farm gives <X> parallel cars. Part <N> needs about
<Y> job-hours. Do you want to (a) stay on the free farm (<Z> days), (b) add a self-hosted
runner on a team PC, or (c) rent a server (about <price>)?
Default if you say "you decide": (a).
```

---

## 1.13 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gh workflow run` says "workflow not found" | The workflow file is not on the compute repo's default branch, or Actions disabled | Re-run `setup_compute_repos.py`; check `gh api repos/<u>/stem-compute/actions/permissions`. |
| `HTTP 403: Resource not accessible` when writing `.github/workflows/car.yml` | Token lacks `workflow` scope | `gh auth refresh -s workflow` for that user (section 1.4). |
| Runs stay "queued" for hours | Account at its concurrency cap, or GitHub-wide queue | Check that account's other running workflows; reduce its weight in `accounts.json`. |
| `mpirun` "running as root" error | Missing `OMPI_ALLOW_RUN_AS_ROOT*` | They are in the Dockerfile; check the job uses the digest that has them. |
| MPI "shm" or "vader" errors | Docker default 64 MB `/dev/shm` | `options: --shm-size=2g` (in `car.yml`). |
| Image pull "denied" on a teammate account | Package still private | Section 1.6.3 visibility step. |
| `collect.py` finds no run for a tag | Dispatch failed silently, or more than 100 runs since | `gh run list -R <u>/stem-compute -w car.yml -L 300` and search the tag. |
| Artifacts missing after 14 days | Retention | Collect within the week; re-dispatch otherwise. |
| A teammate leaves the project | — | Remove them from `accounts.json`; ask them to delete `<u>/stem-compute` and run `gh auth logout --user <u>` on this machine. |

Now open `02_CLEANUP.md`.
