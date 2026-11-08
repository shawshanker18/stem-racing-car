# Chat C — The CFD stopwatch: fixed frame, mesh choice, morphing, mesh study

Start this chat now, in parallel with chats A, B and D. Paste everything below the line into a
new Claude Code chat on the computer where the team's GitHub accounts are logged in to the
GitHub CLI.

---

You are **chat C** ("cfd"), one of four Claude chats working in parallel on the STEM Racing car
optimiser. The others are A (compute farm and lab), B (rules, legality, mass) and D (search
tooling). You work autonomously until your "Done means" list is true, testing everything.

## Setup

1. Make an empty folder for yourself (for example `stem-agent-C`) and work only there.
2. In Git Bash:

   ```bash
   export GH_TOKEN="$(gh auth token --user shawshanker18)"
   gh repo clone shawshanker18/stem-racing-car .
   git switch -c agent/cfd origin/rebuild/bible
   git config user.name shawshanker18
   git config user.email shawshanker18@users.noreply.github.com
   python -m venv .venv && .venv/Scripts/python -m pip install -r docker/requirements.lock
   ```

3. Read, in order: `bible/BRIEFING.md`, `bible/00_START_HERE.md`, `agents/COMMON.md`,
   `bible/06_CFD_STOPWATCH.md` (your Part), `bible/01_COMPUTE_AND_ACCOUNTS.md` sections 1.7-1.10
   (how jobs run). Your status file is `status/cfd.md`.

OpenFOAM is not installed on this computer. Everything that meshes or solves runs on the GitHub
Actions farm in chat A's container image. Write and unit-test the code here; run it there.

## What you own

`cfd/` (all of it), `compute/kinds_cfd.py` (new: the `fresh`, `family`, `morph`, `speed` and
`chained` job kinds, registered automatically by `compute/worker.py`), and in `car/run_car.py`
only `make_bindings` and the `--cfd-json` handling. The CFD frame constant goes in `cfd/` (for
example `cfd/frame.py`), not in `body/` (chat B owns `body/`).

## Your job

Do bible Part 6 completely:

1. **Global frame** (section 6.3): one fixed meshing frame for every legal layout; every meshing
   input (domain, background cells, `locationInMesh`, underbody box, wake boxes) from the frame;
   the unit test that two cars with different wheelbases give identical `blockMeshDict` and
   refinement boxes.
2. **Configuration keys** (section 6.4.3): `frame_mode`, `wheel_extra_level`,
   `feature_snap_body`, `stl_decimate`, `reference_speed_mps` (inlet, moving ground **and** wheel
   rotation all follow it; the wheel ω is set in `components/assembly.py`, so if it needs a
   change there, make the smallest change and say so per COMMON.md section 2). One test per key.
3. **Morphing** (sections 6.5.1-6.5.7): `cfd/morph.py` exists and its solver and file I/O are
   tested on small cases. Finish it: real patch names from `build_blockmesh_dict`, symmetry and
   ground constraints on shared points, ASCII mesh conversion, the checkMesh gate, warm start
   with updated wheel origins and ω, the identity control. Unit-test everything that does not need
   OpenFOAM (for example, a tiny hand-written polyMesh in the tests).
4. **Job kinds** (section 6.10) in `compute/kinds_cfd.py`, each returning the fields the table
   lists; family packages published as release assets (`mesh-families`) by the coordinator step,
   with `results/families.json`.
5. **Experiments on the farm**, in this order, with every threshold written into
   `status/cfd.md` **before** the batch runs:
   - 6.4 screen-mesh choice (C0-C4, 8 skins each, plus 3 fine references);
   - 6.5.8 morph acceptance M-0 to M-4;
   - 6.6 the settled-mean convergence check;
   - 6.7 mesh study (fine needs about 4.5 h; resolved needs chaining, bible 01 section 1.9);
   - 6.8 speed exponent k (write it into `inputs/measured.json` as a CFD-derived input, through a
     small PR, since chat A owns `inputs/`: say so in the commit);
   - 6.9 geometry-fidelity G-1 to G-4.
   Ask the Part 6 compute question before the first batch. You need chat A's image: watch
   `compute/accounts.json` on `rebuild/bible` for the digest; build and test all code first.
6. Write `docs/CFD_REPORT.md`: every experiment, its pre-registered threshold, the result, the
   decision.

## Questions you may ask

The Part 6 compute question; whether to rent a bigger machine for the resolved or long runs
(with the price, bible 01 section 1.12) if chaining on the free farm would take more than about
three days.

## Done means

- [ ] Every item of the Part 6 exit gate (section 6.11) ticked with evidence in `status/cfd.md`.
- [ ] The chosen screen configuration and the morph range written where chat D and the later search chat will read them: `docs/CFD_REPORT.md` and `results/families.json`.
- [ ] cfd and car test suites green in CI on `rebuild/bible`; golden car unchanged (frame changes alter CFD inputs, not the built car).
- [ ] Final PR merged; final message to the user.
