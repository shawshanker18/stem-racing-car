# Agent prompts: how many chats, in what order

The remaining work is split so that chats running at the same time never own the same files.
Run **four chats now, in parallel**, and **one more later**.

| Chat | File | Starts | Owns | Bible Parts |
|---|---|---|---|---|
| A | `A_compute_and_lab.md` | now | `compute/`, `docker/`, workflows, `measure/`, `inputs/`, `docs/lab/` | 1, 3, 4 (validation) |
| B | `B_rules_legality_mass.md` | now | `body/`, `components/`, `car/legality.py`, `golden/` | 5 |
| C | `C_cfd_stopwatch.md` | now | `cfd/`, `compute/kinds_cfd.py`, CFD parts of `car/run_car.py` | 6 |
| D | `D_search_tooling.md` | now | `search/`, `compute/kinds_search.py`, `car/space.py` | 7 (tooling) |
| E | `E_search_run_and_build.md` | after A-D finish | `search/rounds/`, `results/`, reports, `manufacture/` | 7 (run), 8 |

Why this split:

- **A goes first in effect**: B and C need A's container image and compute repositories before
  they can run farm jobs. A merges those early; B, C and D build and test everything that does not
  need the farm in the meantime.
- **B and C** are the two big independent engineering jobs (rules and CFD). They touch different
  folders; the only shared file is `car/run_car.py`, split by function.
- **D** builds the search and proves it on synthetic data, so the real search can start the day
  B and C finish.
- **E** needs everything above, so it starts later. Starting it early would only make it wait.

## How to start a chat

1. Open a new Claude Code chat **on this computer** (the GitHub CLI here is logged in to the
   team's accounts).
2. Open the prompt file, copy everything below its line `---`, and paste it as the first message.
3. The chat makes its own folder and branch, then works on its own. It will ask you only:
   - which accounts it may use, at the start of each Part that runs farm jobs;
   - team decisions (for example ballast);
   - things only you have (lab results, the reference car's files, the competition date);
   - anything that costs money.
4. Each chat writes `status/<name>.md` on the integration branch `rebuild/bible`. That is where to
   look for progress, what is blocked, and what it needs from you.

## Accounts across chats

When two chats ask the compute question at the same time, give them different accounts, or
split one account's capacity. Each account runs at most 20 (Free), 40 (Pro) or 60 (Team) jobs at
once across all chats. Chat A records the caps in `compute/accounts.json`; each chat records its
own confirmed accounts in `compute/confirmations/partN.json`.

## Merging

The chats merge their own pull requests into `rebuild/bible` when CI is green. Only you merge
`rebuild/bible` into `main`. Chat E's final message tells you when that is ready.

## Shared rules

`COMMON.md` (every chat reads it): working copy and branch, ownership, autonomy, testing, git,
the status file, how to finish.
