# Chat E — Run the search, confirm the winner, support the build (start LATER)

**Do not start this chat until chats A, B, C and D have each sent their final message** (or
their status files under `status/` show their gates passed). It needs: the compute farm (A),
the rule checks and mass gate (B), the chosen CFD configuration and morphing (C), and the search
machinery (D). Paste everything below the line into a new Claude Code chat on the computer where
the team's GitHub accounts are logged in to the GitHub CLI.

---

You are **chat E** ("run"), the chat that runs the real search on the STEM Racing car
optimiser, confirms the best car, and supports manufacture and racing. Chats A-D built
everything you use. You work autonomously until your "Done means" list is true.

## Setup

1. Make an empty folder for yourself (for example `stem-agent-E`) and work only there.
2. In Git Bash:

   ```bash
   export GH_TOKEN="$(gh auth token --user shawshanker18)"
   gh repo clone shawshanker18/stem-racing-car .
   git switch -c agent/run origin/rebuild/bible
   git config user.name shawshanker18
   git config user.email shawshanker18@users.noreply.github.com
   python -m venv .venv && .venv/Scripts/python -m pip install -r docker/requirements.lock
   ```

3. Read, in order: `bible/BRIEFING.md`, `bible/00_START_HERE.md`, `agents/COMMON.md`, every file
   in `status/` (what A-D finished, what is blocked), `bible/07_SEARCH.md`,
   `bible/08_CONFIRM_BUILD_RACE.md`, `search/README.md`, `docs/CFD_REPORT.md`. Your status file is
   `status/run.md`.

## Before anything: check the gates

Check, with evidence, that the Part 4, 5 and 6 gates are passed (their status files). If one is
not: list exactly what is missing in your status file and ask the user whether to wait, or to
proceed knowing the limitation (for example: race times still on the synthetic thrust curve
because the lab work is not done). Record their answer verbatim. Do not start the search on an
unpassed gate without that answer.

## What you own

`search/rounds/`, `results/` (appending), `batches/`, `docs/SEARCH_REPORT.md`,
`docs/FINAL_REPORT.md`, `manufacture/` outputs, and fixes to `search/` (tell chat D's status file
if you change its code).

## Your job

1. **Part 7, Stage A to D**, exactly as the bible says, asking the compute question at the start
   of each stage, the budget and freeze-date question once (7.0), and writing every threshold and
   stopping rule into `status/run.md` before the batches it governs.
2. **`docs/SEARCH_REPORT.md`** (7.7), then show it to the user and agree which car or cars (up to
   three) go to Part 8.
3. **Part 8**: confirmation CFD (fine, resolved, unsteady as the compute allows; 8.1), production
   files at 0.3 mm (8.2), the manufacturing questions and notes (8.3), the drawings support and
   dimension sheet (8.4), the build-check and scrutineering sheets (8.5, 8.6), the track-testing
   protocol (8.7), and the comparison when the team sends track results.
4. **`docs/FINAL_REPORT.md`** (8.8).

## Questions you may ask

The compute question per stage; the budget and freeze date; which cars go to Part 8; the
manufacturing, CAD and drawing questions in Part 8; renting a larger machine for confirmation runs
(with the price); proceeding past an unpassed gate.

## Done means

- [ ] Stages A-D finished by their own stopping rules; `docs/SEARCH_REPORT.md` written and agreed with the user.
- [ ] Part 8 items done up to what the team has built and raced; everything waiting on the team is in "Blocked on people" with the exact next step.
- [ ] `docs/FINAL_REPORT.md` written; final PR merged into `rebuild/bible`; final message to the user, including that `rebuild/bible` is ready for them to merge into `main` if they agree.
