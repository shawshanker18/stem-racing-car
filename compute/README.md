# compute

Runs batches of cars on free GitHub Actions machines across team members' accounts with the
GitHub CLI. Read `bible/01_COMPUTE_AND_ACCOUNTS.md` first.

| file | what |
|---|---|
| `accounts.json` | the accounts and their parallel-job caps (no tokens) |
| `confirmations/partN.json` | the accounts the user confirmed for Part N, with their words |
| `worker.py`, `kinds_*.py` | the single entry point every job runs, and the job kinds each Part adds |
| `setup_compute_repos.py` | creates or updates `<user>/stem-compute` with the worker workflow |
| `dispatch.py` | splits a committed batch across the accounts confirmed for a Part and dispatches it |
| `collect.py` | waits for the runs, downloads every case result, appends `results/db.jsonl` |
| `gh.py` | runs `gh` as one account by passing that account's token for one command |
| `worker/car.yml` | the worker workflow copied into every compute repository |

An account is used for Part N only after the user confirmed it in chat and
`confirmations/partN.json` lists it. `dispatch.py` refuses otherwise.
