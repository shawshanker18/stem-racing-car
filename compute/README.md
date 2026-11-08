# compute

Runs batches of cars on free GitHub Actions machines across team members' accounts with the
GitHub CLI. Read `bible/01_COMPUTE_AND_ACCOUNTS.md` first.

| file | what |
|---|---|
| `accounts.json` | the accounts, their parallel-job caps, and the Parts each owner confirmed (no tokens) |
| `setup_compute_repos.py` | creates or updates `<user>/stem-compute` with the worker workflow |
| `dispatch.py` | splits a committed batch across the accounts confirmed for a Part and dispatches it |
| `collect.py` | waits for the runs, downloads every case result, appends `results/db.jsonl` |
| `gh.py` | runs `gh` as one account by passing that account's token for one command |
| `worker/car.yml` | the worker workflow copied into every compute repository |

An account is used for Part N only after its owner confirmed it in chat and
`confirmed_for` has a `"partN"` entry. `dispatch.py` refuses otherwise.
