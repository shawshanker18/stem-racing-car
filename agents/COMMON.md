# Rules every agent chat follows

Every prompt in this folder points here. Read it once at the start, after `bible/00_START_HERE.md`.
If this file and the bible disagree, the bible wins.

## 1. Where you work

- One chat = one working copy = one branch. Never work in another chat's folder.
- Repository: `shawshanker18/stem-racing-car` (public). Integration branch: `rebuild/bible`.
  Your branch: `agent/<your-name>`, cut from `origin/rebuild/bible`.
- The GitHub CLI on this computer is logged in to several team accounts. **Never** run
  `gh auth switch` (other chats share the same login store and would be switched too). Run every
  `gh` or `git push` as a specific account by giving that account's token for one command:

  ```bash
  export GH_TOKEN="$(gh auth token --user shawshanker18)"       # in this shell only
  git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin agent/<name>
  ```

- Python: create a virtual environment in your working copy and install the pinned packages:

  ```bash
  python -m venv .venv
  .venv/Scripts/python -m pip install -r docker/requirements.lock    # Windows; .venv/bin/python elsewhere
  ```

  `.venv/` is ignored by git. OpenFOAM is **not** installed on this computer: anything that
  runs CFD runs on the GitHub Actions farm (bible Part 1) or not at all.

## 2. Ownership: what you may edit

Each prompt lists the files and folders you own. You may **read** anything. You may **edit**
only what you own, plus:

- your own status file `status/<your-name>.md` (create it on your first commit);
- new files inside folders you own;
- a file another chat owns **only** for a change of at most a few lines that your work cannot do
  without (an import, a registration line). Say so in the commit message and in your status file.

If you need a larger change in a file you do not own, write it in your status file under
"Requests to other chats" with the exact change, and carry on with everything else.

## 3. Autonomy

- Work until your prompt's "Done means" list is true. Do not stop to report progress.
- Ask the user only the questions your prompt and the bible name: the compute question
  (bible 00 section 0.7) before your Part's first farm job, regulation details the PDF does not
  settle, team decisions marked TEAM DECISION, money, and merging into `main`. Ask each one once,
  in the bible's question format, then wait for the answer before doing the work that depends on
  it. Everything that does not depend on the answer, do while you wait.
- If you are blocked on another chat (for example the container image is not built yet), do every
  other task first. Then wait with a background check against the integration branch (an
  until-loop with `git fetch` every 15 minutes), never with a foreground sleep.
- If something is blocked on people (lab data, a regulation answer, a team decision), write it in
  your status file under "Blocked on people", with exactly what is needed and the command to run
  when it arrives, and finish everything else.

## 4. Testing (no exceptions)

- Every new function with logic gets a test in that folder's `tests/`.
- Before every push: run the test suites of every folder you touched, plus `car/tests`.
- Before every merge: the golden-car check, from `car/`:

  ```bash
  python run_car.py --out ../out/G1 --body-json '{}' --skin-mm 3.93
  python checks/golden.py compare ../golden/G1.fp.json ../out/G1
  ```

  "same car", or the PR says exactly why the car changed and you update `golden/` in that PR
  with a before/after table of every changed legality margin and the mass.
- CI (`.github/workflows/tests.yml`) runs on every push. A PR is mergeable only when it is green.

## 5. Git and pull requests

- Commit messages: `Part N: <what changed> (<finding IDs>)`. Small commits.
- **No AI attribution anywhere**: no `Co-Authored-By` trailers, no "Generated with" lines, no
  AI collaborators. This is the repository owner's standing instruction.
- Commit as the repository's identity: `git config user.name shawshanker18` and
  `git config user.email shawshanker18@users.noreply.github.com` (in your working copy only).
- Open pull requests **into `rebuild/bible`**, small and often (at least once per finished
  step), so the other chats see your work and conflicts stay small. Before opening: rebase on
  `origin/rebuild/bible` and rerun tests.
- You may merge your own PR into `rebuild/bible` when CI is green and the golden check passes
  (or the PR explains the change). Use a merge commit (`gh pr merge --merge`), not squash.
- Never push to `main`. Never merge into `main`. Never force-push `rebuild/bible`.
- Never commit the regulations PDF, tokens, or anything from `.venv/` or `out/`.

## 6. Status file `status/<your-name>.md`

Keep it current; it is how the user and the other chats see you:

```markdown
# <your-name> — <one-line job>
Updated: <date time>
## Done
- <step> — <evidence: test names, CI run link, PR link>
## In progress
## Blocked on people
- <what> — <who> — <the exact command to run when it arrives>
## Requests to other chats
- <chat>: <exact change wanted, file, why>
## Decisions taken (with the user's words)
## Gate
- [ ] <each item of your Part's exit gate, ticked with evidence>
```

## 7. Finishing

When "Done means" is true: final PR merged into `rebuild/bible`, status file complete, and a
final message to the user that says plainly what was done, what was tested and how, what is
blocked on people, and what the next chat needs from your work.
