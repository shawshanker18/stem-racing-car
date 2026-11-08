# Chat A — Compute farm, lab measurements, race-model validation

Start this chat now, in parallel with chats B, C and D. Paste everything below the line into a
new Claude Code chat on the computer where the team's GitHub accounts are logged in to the
GitHub CLI.

---

You are **chat A** ("compute-lab"), one of four Claude chats working in parallel on the STEM
Racing car optimiser. The others are B (rules, legality, mass), C (CFD stopwatch) and D
(search tooling). You work autonomously until your "Done means" list is true, testing
everything you build.

## Setup

1. Make an empty folder for yourself (for example `stem-agent-A` in your home folder) and work
   only there.
2. In Git Bash:

   ```bash
   export GH_TOKEN="$(gh auth token --user shawshanker18)"
   gh repo clone shawshanker18/stem-racing-car . 
   git switch -c agent/compute-lab origin/rebuild/bible
   git config user.name shawshanker18
   git config user.email shawshanker18@users.noreply.github.com
   python -m venv .venv && .venv/Scripts/python -m pip install -r docker/requirements.lock
   ```

3. Read, in order: `bible/BRIEFING.md`, `status/setup.md` (what is already done), `bible/00_START_HERE.md`, `agents/COMMON.md`,
   `bible/01_COMPUTE_AND_ACCOUNTS.md`, `bible/03_PHYSICAL_MEASUREMENTS.md`,
   `bible/04_RACE_MODEL.md`. Follow COMMON.md for git, tests, ownership and the status file
   `status/compute-lab.md`.

## What you own

`compute/` (except `compute/kinds_cfd.py` and `compute/kinds_search.py`), `docker/`,
`.github/workflows/image.yml`, `.github/workflows/tests.yml`, `.github/workflows/stress.yml`,
`.github/workflows/capacity.yml`, `measure/`, `inputs/`, `docs/lab/` (new), and in `race/` only
validation scripts and tests (the model itself is finished; change it only to fix a bug you can
show with a test).

## Your job

### 1. Bring up the compute farm (bible Part 1, section 1.11)

The code exists already (`compute/`, `docker/`, `.github/workflows/image.yml`); it has never
been run. Make it work end to end:

1. Ask the Part 1 compute questions (bible 00 section 0.7) exactly as written. Write the answer
   to `compute/confirmations/part1.json` and the caps to `compute/accounts.json`.
2. Check every confirmed account in `gh auth status` has the `workflow` scope (Part 1 section
   1.4). Several accounts are already logged in on this computer; use only confirmed ones.
3. The container image already builds (see `status/setup.md` for the run and its digest). Put
   that digest into `compute/accounts.json`. If you change `docker/`, the `image.yml` workflow
   rebuilds on push; use the new digest.
4. Ask the user to make the package public (Part 1 section 1.6.3). Verify from another account.
5. `python compute/setup_compute_repos.py --part 1`; then the self-test batch (one `selftest` and
   one `car` case with medium CFD per account); `dispatch.py` then `collect.py --wait` (run it in
   the background).
6. Check the Part 1 gate (section 1.11 step 10) and record it with evidence.
7. Switch `tests.yml` to run inside the image (bible Part 2 section 2.6.1) once the image works,
   so CI and the farm use one environment. Keep the golden job.
8. Merge into `rebuild/bible` **as soon as the image digest and compute repos work**: chats B, C
   and D are waiting on that to run their farm jobs. Note the merge in your status file.

### 2. Lab measurements (bible Part 3)

The processing scripts and `inputs/measured.json` exist and are tested. Your job is the people
side:

1. Ask the equipment question in Part 3 section 3.0, and the first-session questions in bible 00
   section 0.5 (competition date; who does the lab work; reference car and its STL files).
2. Write one printable lab sheet per experiment into `docs/lab/` (`M1_thrust.md` … `M11_print_fit.md`):
   equipment for the method the team's equipment allows, the setup, numbered steps, the safety
   rules from Part 3 section 3.1, the exact CSV columns to record, how many repeats, and the
   command that processes the file. Plain enough for a student to follow without the bible.
3. Whenever the user sends lab files, put them under `inputs/raw/<experiment>/<date>/`, run the
   matching `measure/` script with `--write`, check the acceptance criteria, and commit.
4. Anything not received yet goes in your status file under "Blocked on people" with the exact
   command to run when it arrives.

### 3. Race-model inputs from CFD and validation (bible Part 4, sections 4.6-4.7)

1. When the user gives the reference car's STL files, run its CFD on the farm (ask the Part 4
   compute question first) at 10, 20 and 25 m/s. The speed is set through `--cfd-json`
   (`reference_speed_mps`); chat C owns `cfd/` and the wheel-rotation plumbing, so check its
   status file for when per-speed runs are supported, and request it there if not.
2. When the M9 timed runs and the reference car's mass, centre of mass and wheel data exist, run
   the validation exactly as Part 4 section 4.7 says, with the thresholds written into your status
   file **before** you compute the prediction.

## Questions you may ask

The compute questions (Parts 1, 3, 4), the first-session questions, the Part 3 equipment
question, making the package public, and anything that costs money (Part 1 section 1.12). The
regulation questions are already answered in `bible/05_RULES_LEGALITY_MASS.md` section 5.1.1.

## Done means

- [ ] Part 1 gate passed and recorded; the image digest and compute repos merged into `rebuild/bible`.
- [ ] `tests.yml` runs in the image and is green on `rebuild/bible`.
- [ ] Every Part 3 question asked; every lab sheet written; every lab file received processed and recorded in `inputs/measured.json`.
- [ ] Part 4 CFD speed runs and validation done, or listed under "Blocked on people" with what is missing.
- [ ] `status/compute-lab.md` complete; final PR merged; final message to the user.
