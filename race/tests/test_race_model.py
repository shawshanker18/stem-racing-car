"""race_model.py against answers worked out by hand (bible Part 4 section 4.8)."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from race_model import Car, Thrust, race_time, exchange_rates, time_with_uncertainty  # noqa: E402

G = 9.80665


def _const(F=5.0):
    t = np.linspace(0, 5, 5001)
    return Thrust(t, np.full_like(t, F), np.zeros_like(t))


def _bare(**kw):
    base = dict(m_car=0.1, m_shell=0.0, D20=0.0, I_f=0.0, I_r=0.0, mu=0.0, h_T=0.025, h_g=0.025)
    base.update(kw)
    return Car(**base)


def _cartridge_like():
    t = np.arange(0, 1.5, 5e-4)
    F = np.where(t < 0.5, 9.2 * np.exp(-t / 0.25), 0.0)
    I = np.concatenate([[0], np.cumsum(0.5 * (F[1:] + F[:-1]) * 5e-4)])
    return Thrust(t, F, 0.008 * (1 - I / I[-1]))


def test_constant_thrust_no_losses():
    assert abs(race_time(_bare(), _const()).time_s - np.sqrt(2 * 20 * 0.1 / 5)) < 1e-4


def test_constant_thrust_with_rolling():
    car = _bare(mu=0.05, x_g=(0.062 + 0.182) / 2)
    a = 50.0 - 0.05 * G
    assert abs(race_time(car, _const()).time_s - np.sqrt(40 / a)) < 1e-4


def test_effective_mass_of_the_wheels():
    I = 0.1 * 0.01413 ** 2 / 4                     # 4 I / r^2 = m
    t = race_time(_bare(I_f=I, I_r=I), _const()).time_s
    assert abs(t / np.sqrt(2 * 20 * 0.1 / 5) - np.sqrt(2)) < 1e-4


def test_axle_loads_at_rest():
    from race_model import _forces
    car = _bare(x_g=0.150)                          # 32 mm ahead of the rear axle on a 120 mm base
    th = Thrust(np.array([0.0, 1.0]), np.zeros(2), np.zeros(2))
    _a, low, _g = _forces(car, th, 0.0, 0.0, 0.0)
    m = 0.1
    Nf, Nr = m * G * 0.032 / 0.12, m * G * (0.12 - 0.032) / 0.12
    assert abs(low - min(Nf, Nr)) < 1e-9


def test_thrust_above_the_com_unloads_the_rear():
    th = _const(9.0)
    high = race_time(_bare(m_car=0.069, h_T=0.031, h_g=0.021, mu_guide=0.3), th)
    level = race_time(_bare(m_car=0.069, h_T=0.031, h_g=0.031, mu_guide=0.3), th)
    assert high.launch_margin_N < 0 < level.launch_margin_N
    assert high.guide_impulse_Ns > 0 and high.time_s > level.time_s


def test_step_count_converged():
    car = Car(m_car=0.0482, m_shell=0.02115, D20=0.41, h_T=0.03, h_g=0.03)
    th = _cartridge_like()
    assert abs(race_time(car, th, n_steps=2000).time_s - race_time(car, th, n_steps=8000).time_s) < 5e-5


def test_regression_against_the_retired_jax_model():
    """Computed once with race_objective.py (JAX, RBF thrust fit) at commit 921b199, before it
    was deleted: D20 0.41 N, 48.2 g + 21.15 g cartridge, mu 0.010, I 1.39e-7 every wheel,
    r 14.13 mm, no lift, COM penalties excluded (T_raw). Old: 1.555827 s, 0.475398 s/N,
    16.632816 s/kg."""
    th = Thrust.from_csv(str(HERE / "co2_thrust_data.csv"))
    car = Car(m_car=0.0482, m_shell=0.02115, D20=0.41, I_f=1.39e-7, I_r=1.39e-7, h_T=0.025, h_g=0.025)
    assert abs(race_time(car, th).time_s - 1.555827) < 2e-3
    x = exchange_rates(car, th)
    assert abs(x["ms_per_mN_drag"] - 0.475398) / 0.475398 < 0.02
    assert abs(x["ms_per_g_mass"] - 16.632816) / 16.632816 < 0.02


def test_exchange_rate_units():
    th = _cartridge_like()
    car = Car(m_car=0.0482, m_shell=0.02115, D20=0.41, h_T=0.03, h_g=0.03)
    by_hand_ms = (race_time(replace(car, D20=0.411), th).time_s - race_time(replace(car, D20=0.409), th).time_s) / 2 * 1e3
    # exchange_rates steps 5 mN, this steps 1 mN: they agree to about 0.4 %. The test is about
    # units (a slip would be a factor of 1000), so 1 % is the right bar.
    assert abs(exchange_rates(car, th)["ms_per_mN_drag"] - by_hand_ms) / by_hand_ms < 1e-2


def test_uncertainty_is_zero_without_spread():
    th = _cartridge_like()
    car = Car(m_car=0.0482, m_shell=0.02115, D20=0.41, h_T=0.03, h_g=0.03)
    mean, sd = time_with_uncertainty(car, [th], {"D20": 0.0}, n=5)
    assert sd < 1e-12 and abs(mean - race_time(car, th).time_s) < 1e-12
