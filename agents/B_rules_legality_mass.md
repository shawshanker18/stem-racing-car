# Chat B — Rules, legality, mass and manufacturing margins

Start this chat now, in parallel with chats A, C and D. Paste everything below the line into a
new Claude Code chat on the computer where the team's GitHub accounts are logged in to the
GitHub CLI.

---

You are **chat B** ("rules"), one of four Claude chats working in parallel on the STEM Racing
car optimiser. The others are A (compute farm and lab), C (CFD stopwatch) and D (search
tooling). You work autonomously until your "Done means" list is true, testing everything.

## Setup

1. Make an empty folder for yourself (for example `stem-agent-B`) and work only there.
2. In Git Bash:

   ```bash
   export GH_TOKEN="$(gh auth token --user shawshanker18)"
   gh repo clone shawshanker18/stem-racing-car .
   git switch -c agent/rules origin/rebuild/bible
   git config user.name shawshanker18
   git config user.email shawshanker18@users.noreply.github.com
   python -m venv .venv && .venv/Scripts/python -m pip install -r docker/requirements.lock
   ```

3. Read, in order: `bible/BRIEFING.md`, `bible/00_START_HERE.md`, `agents/COMMON.md`,
   `bible/05_RULES_LEGALITY_MASS.md` (your Part; section 5.1.1 has the regulation answers already
   read from the PDF). Skim `bible/REVIEW.md` sections 1.5. Your status file is `status/rules.md`.
4. The regulations PDF is in the private repository `shawshanker18/part1-simulation`, branch
   `fix/rules-and-block`. Download it **outside** your working copy to read pages you need:

   ```bash
   gh api -H "Accept: application/vnd.github.raw" \
     "repos/shawshanker18/part1-simulation/contents/STEM%20Racing%20Professional%20Class%20Tech%20Regs%202025-26%20UAE.pdf?ref=fix/rules-and-block" > ../regs.pdf
   ```

   Never commit it to `stem-racing-car` (that repository is public).

## What you own

`body/` (all of it, including the new `body/regs.py`), `components/` (all of it),
`car/legality.py`, `car/tests/test_legality_visibility.py`, `car/checks/stress_cars.py`,
`golden/`. In `car/run_car.py` you own only the mass and legality steps: `build_car`,
`manufactured_mass_kg`, the order of remeshing and mass in `main`, `--ballast-g`, and the
legality call. Chat C owns the CFD parts of `run_car.py` (`make_bindings`, `--cfd-json`); chat D
owns `car/space.py`.

## Your job

Do bible Part 5 completely, in this order (each its own commit and, where it changes the car,
its own PR with a before/after margins table):

1. **`body/regs.py`** (section 5.2): every regulation number, with the answers from 5.1.1 quoted
   in comments; `components/component_contract.py`, `car/legality.py` and
   `body/geometry_contract.py` import from it; the test that no regulation literal lives elsewhere.
2. **Design assertions** for constants compared with constants (F22, section 5.3.6); the
   report counts rule checks and design assertions separately.
3. **F17 T5.5** on the milled file, side wall ≥ 3.0 mm, forward end bounded by body (5.3.1 and
   5.1.1).
4. **F18 T7.4** contact width from the tread; **F19** one radius per axle everywhere; tell the
   user at once if the team wheels fail the true contact-width rule.
5. **F20 T4.1** can fail; **F21 T4.4.4** notch = floor + 10.0 mm, ±1.0 mm; flatness as a fit check.
6. **F23** front wing without auto-shift, recording what was built; **F24** rear wing at an
   absolute height parameter (default: the start car's current built height, so the golden car is
   unchanged unless you choose otherwise); manufacturing margin 0.3 mm in the search gate.
7. **F25** new checks: roundness and all-four-touch (T7.6-T7.7), free spin, angle, listed
   components (T3.3 list in 5.1.1), element counts, chord and thickness on the mesh, unbroken span,
   cargo inside the body.
8. **F26/F27** record the T7.9 diagram confirmation; logo decal 100% visible; team number plus
   the A/B letter at 8 mm (ask the user their number and font width once; until then 8 × 14 mm
   labelled as an assumption).
9. **F33, F34** front keep-clear width; cargo without the one-cell growth.
10. **Machinability with the real tool** (section 5.4): the holder and stick-out inputs come from
    `inputs/measured.json` (`tool_stickout_mm`, `holder_diameter_mm`); while they are unmeasured
    keep today's behaviour and say so in the report.
11. **Mass** (section 5.5): mass from the final remeshed files plus every non-geometric mass in
    `inputs/measured.json`; the 3σ Monte Carlo budget; the T3.6 gate at 3σ. Then ask the ballast
    TEAM DECISION (5.5.4) with the numbers filled in; implement what the user chooses.
12. **Physical-test margins** (section 5.6) for the halo (2 kg at the notch, T4.4.5), the tether
    guide pull, the wheel hang and wing loads, with materials from `inputs/measured.json`.
13. **Grid-spacing check** (section 5.7) at 1.0 and 0.5 mm locally; 0.3 mm on the farm if it does
    not fit this computer.
14. **Stress test** (section 5.8): 400 sized random cars before and after, on the farm. Ask the
    Part 5 compute question first; you need chat A's image (watch `compute/accounts.json` on
    `rebuild/bible` for the digest). Until then, run a 20-car local sample.
15. Extra, for chat D's search space: add a `--chamber-axis-z` option to `run_car.py` that sets
    the chamber axis height (30.5-34.0 mm; the block floor is axis − 29 mm and must stay ≥ 1.5 mm
    above the track) through `body/geometry_contract.py`, with a test. Note it in your status file.

## Questions you may ask

The Part 5 compute question, the team number and font width, the ballast TEAM DECISION, and
any regulation detail the PDF does not settle (check the PDF first).

## Done means

- [ ] Every item of the Part 5 exit gate (section 5.9) ticked with evidence in `status/rules.md`.
- [ ] Every change that altered the golden car has a merged PR with its before/after table, and `golden/` is current.
- [ ] Body, components and car test suites green in CI on `rebuild/bible`.
- [ ] Final PR merged; final message to the user.
