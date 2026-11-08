# Part 3 — Physical measurements (the team measures, the agent guides and processes)

> **Status on 2026-11-08 (branch `rebuild/bible`). Owner: chat A.** Processing scripts (`measure/`) and `inputs/measured.json` done and tested on synthetic data. Not yet done: every lab experiment (team work), the lab sheets, processing real data.
> See `status/` for live progress and `agents/` for the chat prompts.

Read `00_START_HERE.md` first. This Part replaces every guessed physical input with a measured one. It is the highest-value work in the whole project: today the race model runs on a synthetic thrust curve with about 60% of a real cartridge's impulse, an unmeasured rolling coefficient, an unmeasured foam density and no tether term. No amount of CFD can fix a wrong input.

The agent cannot take measurements. The agent's job here is to:

1. tell the team exactly what to build, buy, do and record, one experiment at a time;
2. write the processing scripts in `measure/` before the data arrives, and test them on synthetic data;
3. process the data files the team sends, check them against the acceptance criteria, and write the results into `inputs/measured.json` with full provenance.

**Compute budget for this Part:** none on GitHub beyond the test suite. Processing runs locally in seconds. One optional batch at the end (about 10 CFD cars) to get drag at coast-down speeds for experiment M3.

---

## 3.0 Start of Part: the compute question

Ask, word for word:

```
QUESTION (Part 3, compute 1): How many team members are confirming that their GitHub
accounts can be used for Part 3?
Why I need it: Part 3 is mostly lab work; I only need compute for one optional batch of
about 10 CFD cars (drag at low speed, for the coast-down fit).
Expected load for Part 3: about 10 jobs, under 2 hours. One account is enough; 0 is fine.
```

Then compute 2 (which accounts) if the number is not 0. Record in `STATUS.md`.

Then ask the equipment question:

```
QUESTION (Part 3, equipment): Which of these does the team have or can borrow?
  1. A force sensor that samples at 1,000 per second or faster (for example a Vernier
     Dual-Range Force Sensor or Go Direct Force sensor with a LabQuest or computer interface,
     a PASCO force sensor, or a strain-gauge load cell with a fast ADC such as an ADS1256 board)
  2. A practice launch pod (the striker that fires the cartridge), or access to the official one
  3. A 20 m practice track with tether line, and timing gates
  4. A phone or camera that records slow motion (240 frames per second or more)
  5. A digital scale reading to 0.01 g (0.001 g is better)
  6. Digital calipers
  7. A laser/optical tachometer
  8. Spare official CO2 cartridges (how many?)
Why I need it: each experiment below has a method for each kind of equipment.
```

Record the answers in `STATUS.md` and pick the method for each experiment accordingly.

---

## 3.1 Safety rules (repeat them to the team before every experiment with cartridges)

- An adult supervisor (teacher or lab technician) is present for every cartridge firing.
- Everyone within 3 m wears eye protection. Ear protection for the person nearest the rig.
- The cartridge is always restrained in a holder that is bolted down. A punctured cartridge that is not restrained becomes a projectile.
- Nobody stands behind the cartridge's nozzle (the jet) or in front of the rig.
- Spent cartridges are cold (the expanding gas chills them); handle with gloves for the first minute.
- Never pierce a cartridge by hand or with improvised tools. Use the launch pod's striker only.
- Never heat a cartridge. Store cartridges below 40 °C.
- If anything about a rig feels flimsy, stop and fix it. Report it to the agent; the agent stops the experiment.

---

## 3.2 Where data goes

```
inputs/
  measured.json                     # the single source of physical inputs (schema in 3.13)
  thrust_measured.csv               # the processed mean thrust curve the race model reads
  raw/
    M1_thrust/<YYYY-MM-DD>/run01.csv, run02.csv, ..., calibration.csv, notes.md
    M2_cartridge_mass/<date>/masses.csv
    M3_coastdown/<date>/run01.csv, ..., car.json, notes.md
    M4_spindown/<date>/...
    M5_wheel_inertia/<date>/...
    M6_density/<date>/...
    M7_tether/<date>/...
    M8_launch_video/<date>/*.mp4 (or a link), notes.md
    M9_track_runs/<date>/runs.csv, conditions.csv, car.json
    M10_machining/<date>/...
    M11_print_fit/<date>/...
measure/
  thrust.py coastdown.py spindown.py inertia.py density.py tether.py air.py track.py
  tests/  (one test per script, on synthetic data with a known answer)
```

Every raw folder has a `notes.md` written by the team: who, when, equipment model numbers, anything unusual. The agent asks for it if missing.

Raw files are committed to the repository (they are small). Videos are not committed; put a link in `notes.md`.

---

## 3.3 Order of experiments and how long each takes

| Id | Experiment | Calendar time | Feeds | Priority |
|---|---|---|---|---|
| M2 | Cartridge masses, full and empty | 30 min (with M1) | propellant mass, shell mass | 1 |
| M1 | Thrust curve on a force sensor | 1 afternoon + building the holder | thrust curve | 1 |
| M6 | Densities: foam block, PA12, PLA, glue | 1 hour | mass sizing | 1 |
| M9 | Timed runs of a reference car | 1 session | model validation | 1 |
| M3 | Coast-down on the track | 1 session | rolling and constant resistance | 2 |
| M5 | Wheel inertia | 1 hour | effective mass | 2 |
| M4 | Bearing spin-down | 1 hour | speed-dependent bearing loss | 2 |
| M7 | Tether guide friction | 1 hour | tether resistance | 2 |
| M8 | Launch slow-motion video | with M9 | launch pitch check | 2 |
| M10 | Machining test block | 1 machine session | sanding loss, real radii | 3 |
| M11 | Print fit coupon | 1 print | glue gap, press fits | 3 |

Start M1, M2, M6 and M9 in the first week. M9 needs a car that already exists (last season's car, or any car the team has built): **ASK THE USER** which car, and whether its CAD (STL) exists, because the model needs its geometry and mass to predict its time.

---

## 3.4 M1 — Thrust curve

### 3.4.1 Why

The race model's single biggest input. The current curve is synthetic (it even carries simulated distance and velocity columns). Its peak is 8.5 N at 0.18 s after a slow ramp from 0.22 N, and its impulse is 1.214 N·s. Published fits to measured 8 g cartridges peak near 9 N within milliseconds and deliver about 2 N·s. The difference changes the predicted race time by about 0.5 s and changes how much every millisecond of drag is worth by a factor of about 1.8.

### 3.4.2 What to build: the cartridge holder

- A rigid holder with a bore exactly like the car's chamber: **18.15 mm diameter, 52 mm deep** (the values in `body/geometry_contract.py`, `MODEL_BLOCK_BORE_DIA_MM` and `MODEL_BLOCK_BORE_DEPTH_MM`). The cartridge must sit in it exactly as in the car so the gas exits the same way. Best: mill it from a spare Model Block offcut with the official pre-bored hole. Acceptable: SLS PA12 or aluminium.
- The holder pushes forward on the force sensor along the cartridge axis. The cartridge's rear (neck) faces the launch pod's striker, as in a race.
- The holder must **not slide**: it is bolted to the sensor, and the sensor is bolted to a heavy base (at least 5 kg, clamped to a bench). A forward stop behind the sensor prevents overload damage.
- The axis must be horizontal and aligned with the sensor's measuring axis within 2° (check with a phone inclinometer app).
- The whole assembly must be **stiff**: its first resonance should be above 500 Hz. Test: tap the holder with a pencil while recording at the full sample rate; the ringing frequency appears in the FFT (the processing script prints it). If it is below 300 Hz, stiffen (shorter, thicker mounts, less overhang).

### 3.4.3 Sensor options

| Option | Sample rate | Range | Notes |
|---|---|---|---|
| Vernier Dual-Range Force Sensor (±10 N / ±50 N) with LabQuest 2/3 or Go!Link | up to 10,000/s on LabQuest | use ±50 N | Common in schools. ±10 N range would clip a 9-10 N peak. |
| Vernier Go Direct Force and Acceleration | 1,000/s+ | ±50 N | Check its max rate in the Graphical Analysis app. |
| PASCO Wireless Force Acceleration Sensor | 1,000/s | ±50 N | Fine. |
| Strain-gauge load cell (5 kg bar) + ADS1256 24-bit ADC + Arduino/ESP32/Raspberry Pi | 2,000-30,000/s | 49 N | Cheapest custom route. Do **not** use an HX711 board: it samples at 10 or 80 per second, far too slow. |
| Commercial model-rocket thrust stand | varies | varies | Fine if it records ≥ 1,000/s. |

Minimum acceptable: 1,000 samples per second. Preferred: 2,000 or more.

### 3.4.4 Calibration (before each session)

1. With the holder mounted and empty, record 5 s at rest: this is the zero.
2. Hang or place known masses so they load the sensor along the cartridge axis (use a pulley and string if the axis is horizontal): 0, 100, 200, 500, 1000 g (use a kitchen scale to verify each mass to 1 g). Record 5 s for each.
3. Save `calibration.csv` with columns `mass_g, mean_reading, sd_reading` (one row per mass). If the sensor already outputs newtons, still do this: it checks the sensor and the pulley friction.
4. The processing script fits force = slope × reading + intercept and reports the fit error. Accept if every point is within 1% of full scale used (about 0.1 N).

### 3.4.5 Firing procedure (per cartridge)

1. Weigh the full cartridge (M2) and write its mass and a number on it with a marker.
2. Insert it into the holder exactly as into a car.
3. Start recording. Record at least 0.5 s before firing (the baseline) and at least 2 s after.
4. Fire with the striker.
5. Stop recording. Save as `runNN.csv` with columns `t_s, reading` (time in seconds from the start of the recording, raw reading or newtons; say which in `notes.md`).
6. Remove the spent cartridge (gloves), weigh it empty (M2).
7. Note the room temperature. Cartridge pressure depends strongly on temperature; record it for every run.

Repeats: at least **5 cartridges**, ideally 8, from the **same type and batch** the team will race with. If cartridges are scarce, 5 is the minimum for a mean and a spread.

Also measure, if the striker can be triggered electrically or its motion is visible on video: the **delay** from trigger to the start of thrust. **ASK THE USER** how the official timing starts (at the trigger, or when the car breaks a start beam); if timing starts at the trigger, this delay is part of the race time.

### 3.4.6 Processing: `measure/thrust.py`

```python
"""measure/thrust.py -- raw force-sensor runs -> one mean thrust curve for the race model.

    python measure/thrust.py inputs/raw/M1_thrust/2026-11-12 --charge-g 7.95 --out inputs/thrust_measured.csv

Reads   <dir>/calibration.csv (mass_g, mean_reading, sd_reading), <dir>/run*.csv (t_s, reading)
Writes  --out: columns "time (s)", "force (N)", "mass (kg)" on a 0.5 ms grid from 0 to 1.5 s,
        where "mass (kg)" is the PROPELLANT still on board (charge x (1 - impulse so far / total)).
        <dir>/summary.json: per run peak, time to peak, impulse, duration, ringing frequency;
        ensemble mean and standard deviation of impulse and peak.
The race model (race_objective.py (retired in Part 4)) reads the three columns by name.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt

G = 9.80665
GRID_DT = 5e-4
GRID_END = 1.5


def calibration(path: Path) -> tuple[float, float, float]:
    d = np.genfromtxt(path, delimiter=",", names=True)
    force = d["mass_g"] * 1e-3 * G
    slope, intercept = np.polyfit(d["mean_reading"], force, 1)
    resid = force - (slope * d["mean_reading"] + intercept)
    return float(slope), float(intercept), float(np.abs(resid).max())


def uniform(t: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    dt = float(np.median(np.diff(t)))
    tu = np.arange(t[0], t[-1], dt)
    return tu, np.interp(tu, t, y), 1.0 / dt


def one_run(path: Path, slope: float, intercept: float, cutoff_hz: float) -> dict:
    d = np.genfromtxt(path, delimiter=",", names=True)
    t, f, fs = uniform(d["t_s"], slope * d["reading"] + intercept)
    if fs < 900:
        raise ValueError(f"{path.name}: {fs:.0f} samples/s, need >= 1000")
    n0 = int(0.3 * fs)                                   # first 0.3 s are baseline
    f = f - np.median(f[:n0])
    noise = float(np.std(f[:n0]))
    spec = np.abs(np.fft.rfft(f[:n0] - f[:n0].mean()))
    b, a = butter(4, cutoff_hz / (fs / 2))
    ff = filtfilt(b, a, f)
    thr = max(0.1, 5 * noise)
    on = int(np.argmax(ff > thr))
    if ff[on] <= thr:
        raise ValueError(f"{path.name}: no thrust found above {thr:.3f} N")
    # walk back to where the filtered signal left the noise band
    while on > 0 and ff[on - 1] > 2 * noise:
        on -= 1
    tt, F = t[on:] - t[on], np.clip(ff[on:], 0.0, None)
    peak = float(F.max())
    above = np.nonzero(F > 0.01 * peak)[0]
    end = int(above[-1]) + int(0.02 * fs)
    tt, F = tt[:end], F[:end]
    imp = float(np.trapezoid(F, tt))
    ring = np.abs(np.fft.rfft(f[on:on + int(0.5 * fs)] - ff[on:on + int(0.5 * fs)]))
    freqs = np.fft.rfftfreq(min(int(0.5 * fs), len(f) - on), 1 / fs)
    return {"file": path.name, "fs": fs, "noise_N": noise, "peak_N": peak,
            "t_peak_s": float(tt[np.argmax(F)]), "impulse_Ns": imp, "duration_s": float(tt[-1]),
            "ringing_hz": float(freqs[np.argmax(ring[1:]) + 1]) if len(ring) > 2 else None,
            "_t": tt, "_F": F}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--charge-g", type=float, required=True, help="mean propellant mass from M2")
    ap.add_argument("--cutoff-hz", type=float, default=300.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.folder)
    slope, intercept, cal_err = calibration(d / "calibration.csv")
    runs = [one_run(p, slope, intercept, a.cutoff_hz) for p in sorted(d.glob("run*.csv"))]
    if len(runs) < 3:
        raise SystemExit("need at least 3 runs (5 recommended)")
    grid = np.arange(0.0, GRID_END + GRID_DT / 2, GRID_DT)
    curves = np.array([np.interp(grid, r["_t"], r["_F"], right=0.0) for r in runs])
    mean = curves.mean(axis=0)
    imp_t = np.concatenate([[0.0], np.cumsum(0.5 * (mean[1:] + mean[:-1]) * GRID_DT)])
    prop_kg = a.charge_g * 1e-3 * (1.0 - imp_t / imp_t[-1])
    with open(a.out, "w") as fh:
        fh.write("time (s),force (N),mass (kg)\n")
        for t, F, m in zip(grid, mean, prop_kg):
            fh.write(f"{t:.6f},{F:.6f},{max(m, 0.0):.9f}\n")
    imps = np.array([r["impulse_Ns"] for r in runs])
    peaks = np.array([r["peak_N"] for r in runs])
    summary = {"calibration_max_error_N": cal_err, "n_runs": len(runs),
               "impulse_Ns_mean": float(imps.mean()), "impulse_Ns_sd": float(imps.std(ddof=1)),
               "peak_N_mean": float(peaks.mean()), "peak_N_sd": float(peaks.std(ddof=1)),
               "exhaust_velocity_ms": float(imps.mean() / (a.charge_g * 1e-3)),
               "runs": [{k: v for k, v in r.items() if not k.startswith("_")} for r in runs]}
    (d / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=1))


if __name__ == "__main__":
    main()
```

Notes on the method:

- **Filter:** 4th-order Butterworth applied forward and backward (`filtfilt`, zero phase) at 300 Hz. Zero phase matters: a one-way filter delays the curve and shifts thrust later in time, which the race model would read as a slower launch. If the rig rings below 600 Hz, lower the cutoff to half the ringing frequency and say so in `summary.json`.
- **Onset alignment:** each run is aligned to its own thrust onset, then averaged. Averaging un-aligned runs would smear the rise.
- **Propellant mass:** assumed to leave in proportion to impulse delivered (constant effective exhaust velocity). This is standard and its error is small because the propellant is about 10% of the car's mass and leaves within about 0.3 s. The summary reports the implied exhaust velocity; a value between about 150 and 300 m/s is plausible for CO2 from a small orifice. Outside that range, check the charge mass or calibration.
- **Thrust in the car versus on a fixed rig:** the car moves away from the striker during the first milliseconds, which can change how the seal tears. The fixed rig is the standard approach; M9 (timed runs) is the check that catches any difference.

Test (`measure/tests/test_measure.py`): generate synthetic runs (baseline noise, onset at 0.4 s, F(t) = 9.2 e^(−t/0.25)(1 − e^(−t/0.005)) for 0.5 s, i.e. a realistic 5 ms rise, sampled at 2 kHz, plus a 700 Hz ring), write calibration and run files to a temp folder, run the processing, and assert impulse within 2% and peak within 3% of the curve's own exact values. An instantaneous step from zero is not used: the zero-phase filter overshoots a true step by about 7%, and no cartridge produces one.

### 3.4.7 Acceptance

- Calibration error under 0.1 N.
- At least 5 runs (3 minimum if cartridges are short; say so).
- Impulse spread (sd / mean) under 10%. If larger, look at temperature notes: a cold cartridge gives less impulse.
- The agent writes into `measured.json`: `thrust_csv`, `impulse_Ns`, `peak_N`, `trigger_delay_ms` (if measured), each with sd, n, date, source.

---

## 3.5 M2 — Cartridge masses

For every cartridge used in M1 (and any spare):

| Column | Meaning |
|---|---|
| `cartridge` | the number written on it |
| `full_g` | mass before firing, to 0.01 g |
| `empty_g` | mass after firing |
| `temp_C` | room temperature |

Save as `inputs/raw/M2_cartridge_mass/<date>/masses.csv`.

Results:

- `charge_mass_g` = mean(full − empty), with sd.
- `cartridge_shell_g` = mean(empty). The code currently uses 21.15 g (`CO2_MASS_KG = 0.02115` in `geometry_contract.py`, derived from the regulation's full-mass range 28.9-29.4 g minus 8 g). Replace it with the measured mean.

Processing is a 10-line script (`measure/density.py` can host it as a subcommand). Acceptance: scale reads to 0.01 g; at least 5 cartridges.

---

## 3.6 M6 — Densities and glue

### 3.6.1 Model Block foam

1. Weigh an unused official Model Block (0.01 g).
2. Measure its outer dimensions with calipers (3 readings each of length, width, height; average).
3. Compute the pre-bored hole and underside slot volume from the drawing values in `geometry_contract.py` (bore 18.15 mm × 52 mm deep; slot 6 × 6 mm full length; check the block in hand matches and **ASK THE USER** if it differs).
4. Density = mass / (outer volume − bore − slot).
5. Repeat on 2-3 blocks if available (blocks vary). Also cut a cube (about 20 mm) from an offcut, measure and weigh it: a cut sample avoids the skin of the block, which may be denser.

Write `foam_density_gcm3` with sd. The code uses 0.163 g/cm³.

### 3.6.2 Foam compressive strength (for the 2 kg halo test, Part 5)

Place a 20 mm cube on the scale, press down with a flat 10 × 10 mm punch (a piece of metal bar), slowly, until the foam visibly crushes. Record the highest scale reading. Strength (MPa) = force (N) / 100 mm². Three cubes. Write `foam_compressive_strength_MPa`.

### 3.6.3 Printed materials

Print (or order with the team's next print) three 20 × 20 × 20 mm solid cubes in each material used: SLS PA12 (code uses 1.01 g/cm³) and PLA (code assumes about 1.24). Weigh, measure, compute. SLS parts are slightly porous; the measured value is what matters.

### 3.6.4 Glue

For one practice joint of each type (plug into pocket): weigh the parts, glue, wait for cure, weigh again. Glue mass per joint, in grams. The code has no glue mass today.

### 3.6.5 Bearings

Weigh 5 bearings of the type used (3 × 6 × 2.5 mm); the code assumes 0.30 g each.

### 3.6.6 Paint, decals

Weigh a decal sheet before and after cutting the decals used on one car. If the car is painted, weigh a painted and an unpainted test block of known area. The mass budget must include them.

---

## 3.7 M9 — Timed runs of a reference car (do early: it validates everything)

### 3.7.1 Why

The model has never been compared with a real run. This is the single test that tells the team whether the model can be trusted, and it needs no new car.

### 3.7.2 What is needed

- A reference car that exists and for which the team has (or can make) an STL of every part, so Part 6 can run CFD on it. **ASK THE USER** which car.
- Its mass (weigh it, 0.01 g, without cartridge), its wheel masses, its centre-of-mass position (balance it on a knife edge lengthways and note the x position; balance on its side for height if possible; see 3.7.4).
- The 20 m track with tether and timing. **ASK THE USER** what timing equipment, and whether it starts timing at the trigger or at a start beam.
- At least 5 cartridges from the M1 batch.

### 3.7.3 Procedure

For each run:

1. Weigh the cartridge full.
2. Record room temperature, air pressure (a phone barometer app is fine) and humidity.
3. Run. Record the time to 0.001 s.
4. Also film the start in slow motion (this is M8) and, if possible, the last 5 m from the side (for speed at the finish).
5. Note anything: wobble, tether slap, wheel lift.

Save `runs.csv`: `run, cartridge, full_g, time_s, temp_C, pressure_hPa, humidity_pct, notes`.

At least 5 runs. The spread of these times is the **track noise**: it sets the smallest difference the team can ever verify on the track.

### 3.7.4 Centre of mass of a real car

- **x (lengthways):** balance the car on a thin edge (a ruler on its side) perpendicular to its length; mark the balance point; measure from the nose tip.
- **z (height):** suspend the car from two different points with a thread; the plumb lines cross at the centre of mass (photograph against a grid). Or tilt-balance: place on a scale with one axle raised a known height h and use the change in axle load. The tilt method: with wheelbase W, axle loads N_f, N_r flat and N_f' when the front axle is raised by h (tilt angle θ = asin(h/W)), height above the axle line z = (W / tan θ) × (N_f − N_f') / (N_f + N_r) … the agent derives and checks the formula with the team's actual numbers before using it.

These two numbers feed the launch-pitch check in Part 4.

### 3.7.5 Processing: `measure/track.py`

Reads `runs.csv`, `car.json` (mass, geometry reference, CoM), computes mean time, sd, standard error, and the air density for each run (`measure/air.py`, below). Part 4 uses this to validate the race model.

`measure/air.py`:

```python
"""Air density from temperature, pressure and humidity (CIPM-2007 simplified, adequate to 0.1%)."""
import math


def air_density(temp_c: float, pressure_hpa: float, rh_pct: float) -> float:
    T = temp_c + 273.15
    p = pressure_hpa * 100.0
    es = 6.1078 * 10 ** (7.5 * temp_c / (temp_c + 237.3)) * 100.0     # Tetens, Pa
    pv = rh_pct / 100.0 * es
    Rd, Rv = 287.058, 461.495
    return (p - pv) / (Rd * T) + pv / (Rv * T)


assert abs(air_density(15.0, 1013.25, 0.0) - 1.2250) < 0.001
```

The CFD uses ρ = 1.225 kg/m³ (15 °C, sea level, dry). A hall in the UAE at 25-30 °C has ρ ≈ 1.16-1.18 kg/m³: about 4-5% less drag than the model assumes. Part 4 scales drag by ρ_venue/1.225.

---

## 3.8 M3 — Coast-down (rolling and constant resistance)

### 3.8.1 Why

The model uses μ = 0.010 for rolling and has nothing else. Real cars also lose energy to bearing friction, wheel scrub and the tether guides. At low speed these dominate; they are measured by letting the car coast and watching it slow down.

### 3.8.2 Method A: ramp start on the track (no cartridge needed)

1. Build a short ramp (about 0.5-1 m long, 10-15 cm high) at the start of the tethered track, so the car leaves it at 2-4 m/s along the tether line.
2. Mark the track every 0.5 m with tape visible to the camera.
3. Film from the side, far enough back to see 3-5 m, at 240 frames per second, camera perpendicular to the track.
4. Release the car from a fixed mark on the ramp. 5 runs.
5. Repeat with 20 g of mass taped over the car's centre of mass (5 runs). Two masses separate a mass-proportional term (rolling, μ m g) from a constant term (bearing drag torque, tether friction at low load).
6. Extract position against time with **Tracker** (free, https://physlets.org/tracker/): calibrate the scale using two tape marks, track a point on the car frame by frame, export `t, x` to CSV. Save as `run01.csv` etc. with columns `t_s, x_m`.

### 3.8.3 Method B: the last metres of a real run

During M9, film the second half of the track from the side. After the thrust ends (about 0.3-0.5 s), the car coasts. The deceleration there includes aerodynamic drag, which is significant at 15-20 m/s, so this method needs the car's CFD drag (Part 6) to subtract it. Use Method B as a cross-check of Method A, not instead of it.

### 3.8.4 The model fitted

```
m_eff dv/dt = −( R0 + μ m g + c v² )
x(t) = ∫ v dt
```

- `m_eff = m + Σ I_wheel / r²` (from M5 and the measured wheel radii),
- `c = 0.5 ρ C_D A` = D20 / 400 with D20 from the car's CFD, scaled by ρ_venue/1.225 (fixed, not fitted; at 2-4 m/s aero drag is 1-4% of the drag at 20 m/s),
- fitted: `R0` (N, constant) and `μ` (rolling), using the runs at both masses together.

`measure/coastdown.py`:

```python
"""measure/coastdown.py -- fit constant and rolling resistance to coast-down position data.

    python measure/coastdown.py inputs/raw/M3_coastdown/2026-11-14 --D20 0.41 --rho 1.17
Reads   <dir>/car.json: {"mass_g": ..., "added_mass_g_by_run": {"run06": 20.0, ...},
                         "wheel_I_total_kgm2": ..., "wheel_r_m": ...}
        <dir>/run*.csv: t_s, x_m
Writes  <dir>/fit.json: R0_N, mu, their standard errors, residual RMS (mm), per-run initial speed
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

G = 9.80665


def simulate(t, x0, v0, m, m_eff, R0, mu, c):
    def rhs(_t, s):
        v = max(s[1], 0.0)
        return [v, -(R0 + mu * m * G + c * v * v) / m_eff if v > 0 else 0.0]
    sol = solve_ivp(rhs, (t[0], t[-1]), [x0, v0], t_eval=t, rtol=1e-8, atol=1e-10)
    return sol.y[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--D20", type=float, required=True, help="car drag at 20 m/s, N (CFD)")
    ap.add_argument("--rho", type=float, default=1.225)
    a = ap.parse_args()
    d = Path(a.folder)
    car = json.loads((d / "car.json").read_text())
    c = a.D20 / 400.0 * a.rho / 1.225
    runs = []
    for p in sorted(d.glob("run*.csv")):
        arr = np.genfromtxt(p, delimiter=",", names=True)
        m = (car["mass_g"] + car.get("added_mass_g_by_run", {}).get(p.stem, 0.0)) * 1e-3
        m_eff = m + car["wheel_I_total_kgm2"] / car["wheel_r_m"] ** 2
        runs.append((p.stem, arr["t_s"] - arr["t_s"][0], arr["x_m"], m, m_eff))

    # parameters: R0, mu, then (x0, v0) per run
    def resid(q):
        R0, mu = q[0], q[1]
        out = []
        for k, (_n, t, x, m, m_eff) in enumerate(runs):
            x0, v0 = q[2 + 2 * k], q[3 + 2 * k]
            out.append(simulate(t, x0, v0, m, m_eff, R0, mu, c) - x)
        return np.concatenate(out)

    q0 = [0.005, 0.01]
    for _n, t, x, *_ in runs:
        q0 += [x[0], (x[min(10, len(x) - 1)] - x[0]) / (t[min(10, len(t) - 1)] - t[0])]
    fit = least_squares(resid, q0, bounds=([0, 0] + [-np.inf] * (len(q0) - 2), np.inf))
    J = fit.jac
    dof = max(len(fit.fun) - len(q0), 1)
    cov = np.linalg.pinv(J.T @ J) * (fit.fun @ fit.fun) / dof
    se = np.sqrt(np.diag(cov))
    out = {"R0_N": fit.x[0], "R0_se": se[0], "mu": fit.x[1], "mu_se": se[1],
           "rms_mm": float(np.sqrt(np.mean(fit.fun ** 2)) * 1e3),
           "v0_by_run": {n: float(fit.x[3 + 2 * k]) for k, (n, *_r) in enumerate(runs)},
           "c_fixed": c}
    (d / "fit.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
```

Acceptance: residual RMS under 5 mm; μ and R0 each with a standard error under 30% of the value. If the two-mass separation is poor (large correlation between R0 and μ), report the combined resistance at the race mass instead (R0 + μ m g) and say that only the sum is known.

Test: synthetic runs from known R0 = 0.004 N, μ = 0.008 with 2 mm position noise → fit recovers both within 20%.

---

## 3.9 M5 — Wheel inertia

### 3.9.1 Method A (always): scale the CAD inertia by measured mass

1. Weigh each wheel (with its bearing fitted, as raced) to 0.001 g if possible, else 0.01 g.
2. Weigh a bearing alone (M6).
3. The code computes each wheel's inertia from its STL and PA12 density (`components/wheel.py`, `design()`), plus 0.45 × bearing mass × (outer race radius)² for the bearing.
4. Scaled inertia = CAD inertia (wheel part only) × (measured wheel mass − bearing mass) / (CAD wheel mass) + bearing term. This assumes the printed density is uniform, which SLS PA12 nearly is.

### 3.9.2 Method B (optional, checks Method A): trifilar pendulum

A light disc platform hung from three equal threads of length L at radius R from its centre. Twist slightly, release, time 20 oscillations.

```
I = m g R² T² / (4 π² L)
```

Measure the platform alone (I_p, m_p), then platform plus wheel centred on it (I_t, m_t). Wheel inertia I_w = I_t − I_p. With wheels of about 1.4e-7 kg·m², the platform must be very light (a thin card disc) and the threads long (about 0.5 m) to get a measurable period. Use Method B only if Method A's scaling factor differs from 1 by more than 15%.

Write `wheel_I_front_kgm2`, `wheel_I_rear_kgm2`, `wheel_mass_front_g`, `wheel_mass_rear_g`, each with the method.

---

## 3.10 M4 — Bearing spin-down

### 3.10.1 Why

Bearing drag can rise with speed (grease, seals). At 20 m/s a 14 mm wheel turns at about 1,400 rad/s (13,500 rpm). The coast-down (M3) only reaches 2-4 m/s.

### 3.10.2 Method

1. Mount one wheel on its stub axle or support exactly as on the car, held in a vice, wheel free.
2. Put a small strip of reflective tape on the wheel's side.
3. Spin the wheel up (a rubber-tipped rotary tool touching the tread, or a jet of compressed air) to as fast as practical, at least 5,000 rpm.
4. Release and record speed against time with an optical tachometer (film its display with a phone at 30 fps) until it stops.
5. 3 runs per wheel type.

Fit `I dω/dt = −(τ0 + k ω)`: τ0 (N·m) constant torque, k (N·m·s) viscous. Equivalent force at the tread: `F = (τ0 + k v / r) / r`. `measure/spindown.py` does the fit by linear regression of dω/dt on ω (smooth ω(t) with a Savitzky-Golay filter first).

Write `bearing_tau0_Nm` and `bearing_k_Nms` per wheel. If the viscous term is negligible (its force at 20 m/s under 10% of the constant term), say so; Part 4 then folds τ0 into R0.

---

## 3.11 M7 — Tether guide friction

### 3.11.1 Why

The car runs on a line through two guides. When the car pitches or yaws, a guide presses on the line and rubs. Nothing in the model represents this.

### 3.11.2 Method

1. **Guide-line friction coefficient.** Clamp a printed guide (same material and hole size as the car's). Thread a 1 m piece of the competition tether line through it, at the angle it would have in a pitched car (try 0°, 3°, 6°). Hang a known weight on one end (100 g). Pull the other end slowly through a force sensor (the M1 sensor, or a spring scale). The extra force above the hanging weight's force, divided by the normal force (computed from the wrap angle), is the friction coefficient μ_g. 3 repeats per angle.
2. **Whole car, slow tow.** On the tethered track, pull the car with a thread and the force sensor at walking speed (or with a slow winch) for 2 m. The mean force is the low-speed resistance of the whole car (rolling + bearings + guides at rest attitude). It must agree with M3's R0 + μ m g within the uncertainties; if it is much larger, the guides are rubbing in the car's normal attitude.

Write `mu_guide` and `tow_force_N`.

---

## 3.12 M8 — Launch slow-motion video

Film the start from the side, camera at track level, perpendicular, 240 frames per second or faster, with a grid or ruler behind the car.

From the video, measure:

- whether the **rear** or **front** wheels leave the track at launch, for how many frames, and by how much (mm);
- the car's pitch angle at its maximum (degrees, from two marks on the body);
- whether the tether guides visibly touch the line.

Part 4 explains why the rear wheels are the ones at risk when the thrust line sits above the centre of mass. This video is the check of that calculation.

Write the observations in `notes.md` and the numbers in `measured.json` under `launch_observation`.

---

## 3.13 `inputs/measured.json` — schema

Every physical input the code uses comes from this file. Every entry has the same shape:

```json
{
  "value": 1.0,
  "sd": 0.0,
  "unit": "g/cm3",
  "measured": false,
  "source": "where the number came from: a raw folder, a datasheet URL, or 'code default at 9fe27ca'",
  "date": null,
  "n": 0
}
```

Initial file (the agent writes this at the start of Part 3, with the code's current values and `"measured": false`):

| Key | Initial value | Unit | Measured by |
|---|---|---|---|
| `thrust_csv` | `"race/co2_thrust_data.csv"` | path | M1 |
| `impulse_Ns` | 1.214 | N·s | M1 |
| `peak_N` | 8.52 | N | M1 |
| `trigger_delay_ms` | 0 | ms | M1 |
| `charge_mass_g` | 7.87 | g | M2 |
| `cartridge_shell_g` | 21.15 | g | M2 |
| `foam_density_gcm3` | 0.163 | g/cm³ | M6 |
| `foam_compressive_strength_MPa` | null | MPa | M6 |
| `pa12_density_gcm3` | 1.01 | g/cm³ | M6 |
| `pla_density_gcm3` | 1.24 | g/cm³ | M6 |
| `glue_g_per_joint` | 0.0 | g | M6 |
| `bearing_g` | 0.30 | g | M6 |
| `decal_paint_g` | 0.0 | g | M6 |
| `mu_roll` | 0.010 | — | M3 |
| `R0_N` | 0.0 | N | M3 |
| `bearing_tau0_Nm` | 0.0 | N·m | M4 |
| `bearing_k_Nms` | 0.0 | N·m·s | M4 |
| `wheel_I_front_kgm2` | 1.25e-7 (CAD, ABS) — replace with `wheel.design()` value | kg·m² | M5 |
| `wheel_I_rear_kgm2` | 1.53e-7 (CAD) | kg·m² | M5 |
| `wheel_mass_front_g` | from `wheel.design()` | g | M5 |
| `wheel_mass_rear_g` | from `wheel.design()` | g | M5 |
| `mu_guide` | null | — | M7 |
| `tow_force_N` | null | N | M7 |
| `air_density_kgm3` | 1.225 | kg/m³ | M9 conditions at the venue |
| `track_noise_s` | null | s (sd of repeat runs) | M9 |
| `launch_observation` | null | text + numbers | M8 |
| `sanding_loss_mm` | 0.0 | mm per surface | M10 |
| `glue_gap_mm` | 0.15 (unmeasured guess in `joints.py`) | mm | M11 |

Rules:

- Only `measure/*.py` scripts and the agent (on processing a raw folder) write to this file. Every write updates `source`, `date`, `n`, `sd` and sets `measured: true`.
- Part 4 makes the race model, mass rollup and builders read their inputs from this file. Every report prints the list of entries with `measured: false` at the top.

---

## 3.14 M10 — Machining test block

On the team's CNC mill with the 6.25 mm ball-end cutter:

1. Mill a test piece from a block offcut with: a pocket with a 3.125 mm internal radius, a 6.5 mm wide slot 10 mm deep, a 20 mm deep side feature reachable only from the side, a 1 mm wall, a 2 mm wall, and a flat area to sand.
2. Record: which features came out as designed, the tool's stick-out length from the holder and the holder's diameter (Part 5 needs these), surface finish.
3. Sand the flat area as the team would sand the car. Measure the thickness removed (calipers before and after, five points). Weigh before and after to get mass lost per cm².

Write `sanding_loss_mm`, `tool_stickout_mm`, `holder_diameter_mm`, and feature results in `notes.md`.

---

## 3.15 M11 — Print fit coupon

Print (SLS PA12, as for the real parts) a coupon with five plugs of the same nominal size and five pockets milled in foam with clearances 0.05, 0.10, 0.15, 0.20, 0.30 mm per side (the agent generates the STLs and the milling geometry from `components/joints.py` with `GLUE_GAP_MM` set to each value). Also print three stub axles at the code's diameter and test the bearing press fit.

Record which clearance gives a firm hand fit with room for glue, and whether the bearings press on without cracking the stub. Write `glue_gap_mm` and a note on stub sizing.

---

## 3.16 Exit gate for Part 3

- [ ] M1, M2, M6, M9 complete and processed; every entry they feed has `measured: true`.
- [ ] M3, M4, M5, M7, M8 complete, or explicitly deferred by the user with a reason recorded.
- [ ] `inputs/thrust_measured.csv` exists and passes the acceptance in 3.4.7.
- [ ] `measure/tests` pass.
- [ ] `STATUS.md` lists every measurement with its value, sd and n.

Now open `04_RACE_MODEL.md`.
