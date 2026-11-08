One file per Part, `partN.json`, written when the user confirms which GitHub accounts Part N may use
(bible 00 section 0.7):

```json
{"users": ["alice", "bob"], "user_said": "<their words>", "date": "2026-11-09"}
```

`dispatch.py` and `setup_compute_repos.py` refuse any account not listed for the Part they run.
Caps (parallel jobs per account) live in `../accounts.json`, owned by the compute chat.
