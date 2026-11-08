"""search/gp.py -- Gaussian-process model and batch expected improvement (minimisation).

Inputs are scaled to [0,1]^d. Outputs are standardised inside. Per-row noise variance is passed
as alpha (real ms^2), so averaged replicates count as less noisy.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm, qmc
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern


class GP:
    def __init__(self, X: np.ndarray, y: np.ndarray, noise_var: np.ndarray, kernel=None):
        self.mu_y, self.sd_y = float(y.mean()), float(y.std()) or 1.0
        ys = (y - self.mu_y) / self.sd_y
        alpha = noise_var / self.sd_y ** 2
        d = X.shape[1]
        if kernel is None:
            kernel = ConstantKernel(1.0, (1e-2, 1e2)) * Matern(
                length_scale=np.full(d, 0.3), length_scale_bounds=(0.02, 20.0), nu=2.5)
            self.m = GaussianProcessRegressor(kernel, alpha=alpha, n_restarts_optimizer=8, random_state=0)
        else:
            self.m = GaussianProcessRegressor(kernel, alpha=alpha, optimizer=None)
        self.m.fit(X, ys)
        self.X, self.y, self.noise_var = X, y, noise_var

    def predict(self, Xq: np.ndarray):
        """Latent mean and sd in real ms (noise not included: alpha only enters at training points)."""
        m, s = self.m.predict(Xq, return_std=True)
        return m * self.sd_y + self.mu_y, s * self.sd_y

    def incumbent(self):
        """The evaluated car with the lowest predicted mean (not the lowest noisy observation)."""
        m, s = self.predict(self.X)
        i = int(np.argmin(m))
        return i, float(m[i]), float(s[i])

    def ei(self, Xq: np.ndarray, best: float) -> np.ndarray:
        m, s = self.predict(Xq)
        s = np.maximum(s, 1e-9)
        z = (best - m) / s
        return (best - m) * norm.cdf(z) + s * norm.pdf(z)

    def fantasy(self, x: np.ndarray, y_fake: float, noise_var: float) -> "GP":
        """Same hyperparameters, one more (pretend) observation: for building a batch."""
        return GP(np.vstack([self.X, x]), np.append(self.y, y_fake),
                  np.append(self.noise_var, noise_var), kernel=self.m.kernel_)


def candidate_pool(d: int, X: np.ndarray, y: np.ndarray, n_sobol: int = 16384, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sob = qmc.Sobol(d, scramble=True, seed=seed).random(n_sobol)
    top = X[np.argsort(y)[:10]]
    local = np.clip(np.repeat(top, 400, axis=0) + rng.normal(0, 0.05, (len(top) * 400, d)), 0, 1)
    return np.vstack([sob, local])


def propose_batch(gp: GP, q: int, noise_var: float, seed: int = 0, min_dist: float = 0.02) -> np.ndarray:
    """Kriging-believer batch: pick the max-EI point, pretend its outcome is the predicted mean,
    refit with fixed hyperparameters, repeat."""
    _, best, _ = gp.incumbent()
    pool = candidate_pool(gp.X.shape[1], gp.X, gp.y, seed=seed)
    chosen, g = [], gp
    for _ in range(q):
        e = g.ei(pool, best)
        if chosen:
            dmin = np.min(np.linalg.norm(pool[:, None, :] - np.array(chosen)[None], axis=2), axis=1)
            e[dmin < min_dist] = -1
        k = int(np.argmax(e))
        x = pool[k]
        chosen.append(x)
        g = g.fantasy(x[None], float(g.predict(x[None])[0][0]), noise_var)
    return np.array(chosen)
