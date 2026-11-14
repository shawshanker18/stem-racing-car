"""The carving loop's decisions (BUILD_SPEC 7 steps 1-2, 12.2, 12.4), one round at a time.

A chain is one car being improved. Each round, per chain:
  1. search:  the current car's time (two runs the first time, so noise is known) and one
              candidate per step size along the compass (k candidates);
  2. confirm: the best candidate re-timed on fresh runs (2, then 4, then 8 while it looks better
              but is not yet clear); it is KEPT only if the fresh mean
              beats the current car's mean by z * sigma * sqrt(1/2 + 1/2), with
              z = Phi^-1(1 - 0.05 / k) (Bonferroni over the k candidates) and sigma pooled over
              every repeat pair the chain has (sigma^2 = mean (a - b)^2 / 2). Selection and the
              keep test use different runs, so picking the luckiest of k is not rewarded.
  3. step:    along -H g, H learned from the chain's own kept steps (L-BFGS, see plan); trust
              doubles after a keep at the largest size, halves after no keep. The chain stops
              when trust falls below MIN_SCALE.
A chain also stops, flagged "compass_suspect", once >= 12 candidates are timed and >= 90 % of
them were slower, or when it stops having kept at most one step while >= 75 % of its candidates
were slower than the car they came from: a compass that points uphill.

Everything is a pure function of the state and the results so far, and every timing has a case
id (round, chain, tag), so a round is idempotent: `needed(state)` lists what is missing, a
rerun redoes only that, and `advance(state, results)` moves on once all of it is in.

The problem plugs in through four calls (fake bench: checks/bench.py; real cars: Parts 1-3):
  start(seed) -> x          step(x, direction, size) -> x'
  direction(x) -> the compass, dT/dx in the problem's coordinates   measure(x, case_id) -> time, s
"""
from __future__ import annotations

from statistics import NormalDist

SIZES = (0.25, 0.5, 1.0, 2.0)        # candidates per round, as fractions of the chain's scale
CONFIRM = 2
LOOKS = int(__import__("os").environ.get("P5_LOOKS", 8))  # confirm with 2, 4, ... 256 runs (bench: 32 runs left the curved valley short)
MIN_SCALE = 1 / 64
MAX_ROUNDS = 25
HARD_ROUNDS = 40                     # a chain still keeping (a keep in its last 5 rounds) may run to 40
ALPHA = 0.05
SEED0 = 46000
RESTARTS = 3                         # fresh starts from the plain compass when trust runs out
MEMORY = 5                           # L-BFGS pairs kept per chain


def new_chain(i: int, x, scale: float) -> dict:
    """scale: the first step length; afterwards \"scale\" is the trust multiplier (starts at 1)."""
    return {"id": i, "seed": SEED0 + i, "x": x, "scale": 1.0, "scale0": scale, "round": 0,
            "status": "running", "phase": "search", "times": [], "pairs": [], "history": [],
            "cands": {}, "slower": 0, "timed": 0}


def z_bonferroni(k: int) -> float:
    return NormalDist().inv_cdf(1 - ALPHA / k)


def pooled_sigma(c: dict, prior: float) -> float:
    """sqrt(mean (a - b)^2 / 2) over every repeat pair; the prior counts as one pair until there
    are two of the chain's own."""
    d = [(a - b) ** 2 / 2 for a, b in c["pairs"]]
    if len(d) < 2:
        d = d + [prior ** 2] * (2 - len(d))
    return (sum(d) / len(d)) ** 0.5


def case(c: dict, tag: str) -> str:
    return f"r{c['round']}_c{c['id']}_{tag}"


def cap(c):
    recent = [h["kept"] for h in c["history"][-5:]]
    return HARD_ROUNDS if any(recent) else MAX_ROUNDS


def needed(state: dict) -> dict:
    """{case id: (x, what)} still to time this round, for every running chain."""
    out = {}
    for c in state["chains"]:
        if c["status"] != "running":
            continue
        if c["phase"] == "search":
            for r in range(len(c["times"]), 2):
                out[case(c, f"cur{r}")] = (c["x"], "current")
            for s, x in c["cands"].items():
                out[case(c, f"s{s}")] = (x, "candidate")
        else:
            n = c.get("nconf", CONFIRM)
            for r in range(n):
                out[case(c, f"conf{r}")] = (c["cands"][c["best"]], "confirm")
            for r in range(n - CONFIRM):
                out[case(c, f"curx{r}")] = (c["x"], "current")
    return out


def lbfgs(g, mem):
    """-H g by the L-BFGS two-loop recursion over the chain's (s, y) pairs (s = kept step, y =
    change of the compass across it); with no pairs, the plain downhill direction -g."""
    q = -g
    a = []
    for s, y in reversed(mem):
        r = 1.0 / (y @ s)
        a.append(r * (s @ q))
        q = q - a[-1] * y
    if mem:
        s, y = mem[-1]
        q = q * (s @ y) / (y @ y)
    for (s, y), ai in zip(mem, reversed(a)):
        r = 1.0 / (y @ s)
        q = q + s * (ai - r * (y @ q))
    return q


def plan(state: dict, direction, step) -> None:
    """Make this round's candidates for chains in search that have none yet.

    direction(x) is the compass in the problem's coordinates (+ = slower). The chain learns the
    curvature from its own kept steps (L-BFGS, MEMORY pairs), so the step is -H g; its natural
    length is |H g| once there is a pair, else the chain's starting scale. Candidates sit at
    SIZES x trust x that length; trust doubles after a keep at the largest size and halves after
    a round with no keep."""
    import numpy as np
    for c in state["chains"]:
        if c["status"] == "running" and c["phase"] == "search" and not c["cands"]:
            g = np.asarray(direction(c["x"]), float)
            mem = c.setdefault("mem", [])
            if c.get("g_prev") is not None:
                s, y = np.asarray(c["x"], float) - c["x_prev"], g - c["g_prev"]
                if s @ y > 1e-12 * np.linalg.norm(s) * np.linalg.norm(y):
                    mem.append((s, y))
                    del mem[:-MEMORY]
                c["g_prev"] = None
            c["g"] = g
            d = lbfgs(g, mem)
            n = np.linalg.norm(d)
            if n == 0:
                c["cands"] = {str(f): c["x"] for f in SIZES}
                continue
            length = n if mem else c["scale0"]
            c["cands"] = {str(f): step(c["x"], d / n, f * c["scale"] * length) for f in SIZES}


def advance(state: dict, results: dict, prior_sigma: float, shape_sigma: float) -> None:
    """shape_sigma: Part 2's measured car-to-car noise on the loop's mesh (s). Re-timing one shape
    repeats its own error, so it never averages away: the keep bar always carries 2 shape_sigma^2
    (current car and candidate are two shapes), however many copies are timed."""
    """Use whatever results exist; move each chain on once its round's cases are all in."""
    need = needed(state)
    for c in state["chains"]:
        if c["status"] != "running":
            continue
        mine = {k for k in need if k.startswith(f"r{c['round']}_c{c['id']}_")}
        if not mine <= set(results):
            continue
        if c["phase"] == "search":
            for r in range(len(c["times"]), 2):
                c["times"].append(results[case(c, f"cur{r}")])
            if len(c["times"]) == 2 and not c["pairs"]:
                c["pairs"].append(tuple(c["times"][:2]))
            T0 = sum(c["times"]) / len(c["times"])
            dT = {s: results[case(c, f"s{s}")] - T0 for s in c["cands"]}
            c["timed"] += len(dT)
            c["slower"] += sum(v > 0 for v in dT.values())
            c["dT"] = dT
            c["best"] = min(dT, key=dT.get)
            c["phase"] = "confirm"
            continue
        n = c.get("nconf", CONFIRM)
        conf = [results[case(c, f"conf{r}")] for r in range(n)]
        cur = c["times"] + [results[case(c, f"curx{r}")] for r in range(n - CONFIRM)]
        T0 = sum(cur) / len(cur)
        sig = pooled_sigma(c, prior_sigma)
        # Bonferroni over the k candidates AND the LOOKS confirm looks (2, 4, 8 runs)
        z = z_bonferroni(len(c["cands"]) * LOOKS)
        gain = T0 - sum(conf) / n
        bar = z * (sig ** 2 * (1 / len(cur) + 1 / n) + 2 * shape_sigma ** 2) ** 0.5
        keep = gain > bar
        copies_help = sig ** 2 * (1 / len(cur) + 1 / n) > 0.1 * 2 * shape_sigma ** 2   # more copies only cut repeat noise
        if not keep and gain > 0 and copies_help and n < CONFIRM * 2 ** (LOOKS - 1):
            c["nconf"] = 2 * n                    # promising but not yet clear: time both more
            continue
        c["pairs"] += [(conf[i], conf[i + 1]) for i in range(0, n - 1, 2)]
        c["pairs"] += [(cur[i], cur[i + 1]) for i in range(len(c["times"]), len(cur) - 1, 2)]
        c["nconf"] = CONFIRM
        c["history"].append({"round": c["round"], "scale": c["scale"], "best": float(c["best"]),
                             "dT_search": c["dT"][c["best"]], "gain_confirm": gain, "sigma": sig,
                             "z": z, "bar": bar, "confirm_runs": n, "kept": keep})
        if keep:
            c["x_prev"], c["g_prev"] = c["x"], c["g"]
            c["x"], c["times"] = c["cands"][c["best"]], list(conf)
            if float(c["best"]) == max(SIZES):
                c["scale"] *= 2
        elif gain <= 0 or c["dT"][c["best"]] >= 0:
            c["scale"] /= 2                     # nothing better: shrink; a real but unclear gain keeps the size
        c["round"] += 1
        c["phase"], c["cands"] = "search", {}
        if c["scale"] < MIN_SCALE and c["round"] < cap(c) and c.get("restarts", 0) < RESTARTS:
            # restart while rounds are left: forget the learned curvature and step from the plain
            # compass again (a stale curvature model stalls in curved valleys)
            c["scale"], c["mem"], c["g_prev"] = 1.0, [], None
            c["restarts"] = c.get("restarts", 0) + 1
        kept = sum(h["kept"] for h in c["history"])
        stopping = c["scale"] < MIN_SCALE or c["round"] >= cap(c)
        if (c["timed"] >= 12 and c["slower"] >= 0.9 * c["timed"]) or (stopping and kept <= 1 and c["slower"] >= 0.75 * c["timed"]):
            c["status"] = "compass_suspect"
        elif c["scale"] < MIN_SCALE:
            c["status"] = "converged"
        elif c["round"] >= cap(c):
            c["status"] = "out_of_rounds"


def to_start(state: dict, results: dict, running: set, free: int) -> list:
    """The next timings to dispatch on the farm: what needed() lists, minus what is done or
    running, at most `free` of them, taken round-robin across chains so N chains share a short
    farm evenly and no chain waits behind another's whole round (slots fill gradually)."""
    per = {}
    for k in needed(state):
        if k not in results and k not in running:
            per.setdefault(k.split("_")[1], []).append(k)
    out, queues = [], [per[c] for c in sorted(per)]
    while len(out) < free and any(queues):
        for q in queues:
            if q and len(out) < free:
                out.append(q.pop(0))
    return out


def run_local(state: dict, direction, step, measure, prior_sigma: float, shape_sigma: float) -> dict:
    """The whole loop with an immediate stopwatch (the fake bench); the farm does the same with
    needed/advance across GitHub jobs."""
    results = {}
    while any(c["status"] == "running" for c in state["chains"]):
        plan(state, direction, step)
        for k, (x, _) in needed(state).items():
            results[k] = measure(x, k)
        advance(state, results, prior_sigma, shape_sigma)
    return state
