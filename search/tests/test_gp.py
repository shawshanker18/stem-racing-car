"""search/gp.py on a known function (bible Part 7 section 7.4.3): it must minimise, scale and
pick its incumbent by the model, not by the luckiest noisy observation."""
import sys
from pathlib import Path

import numpy as np
from scipy.stats import qmc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gp import GP, propose_batch  # noqa: E402

X0 = np.array([0.3, 0.7, 0.55])


def f(X):
    return 10 * np.sum((X - X0) ** 2, axis=1)


def _run(seed: int):
    rng = np.random.default_rng(seed)
    X = qmc.Sobol(3, seed=seed).random(16)
    y = f(X) + rng.normal(0, 0.3, len(X))
    for r in range(6):
        g = GP(X, y, np.full(len(y), 0.09))
        B = propose_batch(g, 8, 0.09, seed=seed + r)
        X = np.vstack([X, B])
        y = np.append(y, f(B) + rng.normal(0, 0.3, len(B)))
    i, _m, _s = GP(X, y, np.full(len(y), 0.09)).incumbent()
    return f(X), i


def test_finds_the_minimum_and_a_sound_incumbent():
    for seed in range(5):
        true, i = _run(seed)
        assert true.min() < 0.5, f"seed {seed}: best evaluated {true.min():.3f}"
        assert true[i] - true.min() < 0.1, f"seed {seed}: incumbent {true[i]:.3f} vs best {true.min():.3f}"
