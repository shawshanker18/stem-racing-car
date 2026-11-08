# Chat D — Search tooling (built and proven on synthetic data)

Start this chat now, in parallel with chats A, B and C. Paste everything below the line into a
new Claude Code chat on the computer where the team's GitHub accounts are logged in to the
GitHub CLI.

---

You are **chat D** ("search"), one of four Claude chats working in parallel on the STEM Racing
car optimiser. The others are A (compute farm and lab), B (rules, legality, mass) and C (CFD
stopwatch). You build and fully test the search machinery so that a later chat (E) can run the
real search the moment the CFD and rules work is finished. You do **not** run real CFD.

## Setup

1. Make an empty folder for yourself (for example `stem-agent-D`) and work only there.
2. In Git Bash:

   ```bash
   export GH_TOKEN="$(gh auth token --user shawshanker18)"
   gh repo clone shawshanker18/stem-racing-car .
   git switch -c agent/search origin/rebuild/bible
   git config user.name shawshanker18
   git config user.email shawshanker18@users.noreply.github.com
   python -m venv .venv && .venv/Scripts/python -m pip install -r docker/requirements.lock
   ```

3. Read, in order: `bible/BRIEFING.md`, `bible/00_START_HERE.md`, `agents/COMMON.md`,
   `bible/07_SEARCH.md` (your Part), `bible/01_COMPUTE_AND_ACCOUNTS.md` sections 1.8-1.10 (batch
   files, dispatch, collect), `bible/06_CFD_STOPWATCH.md` sections 6.2, 6.5 and 6.10 (what the
   CFD job kinds return). Your status file is `status/search.md`.

## What you own

`search/` (all of it; `search/gp.py` exists and is tested), `compute/kinds_search.py` (new: the
`legal_only` job kind, registered automatically by `compute/worker.py`), and `car/space.py`.

## Your job

Build bible Part 7's machinery, end to end, and prove it on synthetic data:

1. **Search space** (section 7.2): `search/space.json` generated from `car/space.py` plus the new
   settings (rear wing through `--rwing-json`, `ballast_g` through `--ballast-g`,
   `chamber_axis_z_mm` through `--chamber-axis-z`, which chat B is adding: mark it unavailable
   until B's status file says it is merged). Each entry: type, bounds, step, start,
   `morphable_step` (null until chat C publishes the morph range in `docs/CFD_REPORT.md`; make it a
   setting the round planner reads at run time).
2. **Batch writers** for every stage: Stage A screening around a family (morph cases ± h, re-sized,
   identity controls, fresh-mesh replicates for bool/topology settings); Stage B rounds (initial
   design from the old solver's chain cars in `archive/search-2026-11/` plus Sobol, the legal-only
   filter batch, the CFD batch); Stage C trust-region steps; Stage D perturbations. Each writes a
   batch file exactly in the format of bible 01 section 1.8.1, with the case kinds of 01 and 06.
3. **`search/ingest.py`** (section 7.4.2): reads `results/db.jsonl`, builds X, y (real ms) and
   per-row noise; handles failed, illegal and non-converged rows correctly.
4. **`search/round.py`** with `plan`, `filter` and `ingest` (section 7.4.6), the held-out score,
   the stopping rule (7.4.7) and the validity gate, `predicted.json` written **before** each run.
5. **Stage A analysis** (slopes, curvature, potential, the selection rule 7.3.3); **Stage C**
   step logic (7.5.2); **Stage D** robustness Monte Carlo (7.6); the report generator for
   `docs/SEARCH_REPORT.md` (7.7) with its plots.
6. **`legal_only`** job kind: runs `car/run_car.py` without CFD and returns legality, mass,
   centre of mass and launch-margin geometry.
7. **Synthetic dry run, whole loop**: a fake `fresh`/`morph`/`legal_only` result generator
   (a known smooth function of the settings plus noise of the size Part 6 measured, and a known
   illegal region) that writes case JSONs exactly like real workers. Run Stage A → B (several
   rounds) → C → D through the real file formats, `ingest`, `round.py` and the report. It must find
   the known optimum within the noise and stop by its stopping rule. Commit it as a test (a short
   version that runs in CI in under 5 minutes) and as a script (the long version).
8. A one-page `search/README.md` for chat E: the exact commands, in order, for a real run.

## Questions you may ask

None are needed for this work. If something in the bible is ambiguous, choose the reading that
is safest for the real run, write it in your status file, and carry on.

## Done means

- [ ] Every module above exists with tests; `search/` and `compute` test suites green in CI.
- [ ] The synthetic dry run passes in CI and its long version is documented with its output.
- [ ] `search/README.md` gives chat E a complete run book.
- [ ] Final PR merged into `rebuild/bible`; `status/search.md` complete; final message to the user.
