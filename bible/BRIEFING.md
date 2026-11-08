# Briefing: the STEM Racing car rebuild, Part by Part

Date: 2026-11-08. Branch: `rebuild/bible` in `shawshanker18/stem-racing-car`.

## The goal

Find the fastest car over 20 m that is legal under the STEM Racing UAE Professional Class
Technical Regulations 2025-26. Measure the real inputs, build a race model that matches a
real run, and run a search whose gains are larger than its noise. Then build and race the car.

## Why the project was rebuilt

An architecture review (`bible/REVIEW.md`) found six things that mattered most:

1. **The thrust curve is synthetic.** It holds about 60% of a real cartridge's impulse, so every
   predicted time was about 0.5 s too slow and every millisecond figure about 1.8 times too large.
2. **The body is a small lever.** Wheels make about two-thirds of the drag and the body about an
   eighth. The whole body's drag is worth roughly 13 ms at realistic thrust.
3. **The CFD noise came from remeshing.** A 0.01 mm change in shape moved drag by about 0.5%. The
   old search accepted the best of about 10 candidates at twice the noise, so roughly half of its
   16 "gains" could be noise.
4. **The adjoint failed its own test**, and the carving method built on it was broken as wired.
5. **Several legality checks were weaker than the rules**, and the 0.2 g mass margin was smaller
   than the unmeasured mass uncertainty (about ±1 g).
6. **Nothing had been compared with a real run.**

The rebuild also found one new first-order effect:

- **Launch pitch.** When the thrust line sits above the centre of mass, the car tips nose-down at
  launch and the rear wheels lift onto the tether line.
- **Its cost.** With the centre of mass 10 mm below the thrust line, this costs about 5 ms. That is
  as much as the best body-shape gains.

## How the work is organised

The code now sits in one repository, one folder per job: `body`, `components`, `cfd`, `race`,
`car`, `compute`, `measure`, `search`. The five old `partN-simulation` repositories are superseded.

The plan is eight Parts. Each has a file in `bible/` that an agent can follow alone. The work is
split across Claude chats that own different folders:

| Part | What | Status today | Chat |
|---|---|---|---|
| 1 | Compute on GitHub Actions across team accounts | code written and tested; not yet run | A |
| 2 | Cleanup of retired methods | **done** | — |
| 3 | Physical measurements | scripts and inputs file done; lab work not started | A (with the team) |
| 4 | Race model | **model done**; validation waits for lab data | A |
| 5 | Rules, legality, mass | regulation answers read from the PDF; checks not started | B |
| 6 | Low-noise CFD | morphing solver exists; rest not started | C |
| 7 | Search | GP module exists; machinery not started | D builds, E runs |
| 8 | Confirm, build, race | not started | E |

**Run chats A, B, C and D now, in parallel. Start chat E when those four have finished.**
The prompts are in `agents/`; `agents/README.md` says how to start them.

## Part by Part

### Part 1: Compute (chat A)

**What it is:**
- CFD runs on free GitHub Actions machines across the team's accounts, driven by the GitHub CLI.
- Each account gets a small public `stem-compute` repository that runs its share of the jobs.
- A container image replaces installing OpenFOAM on every job.

**Done:** the image definition, the worker, splitting a batch across accounts, collecting
results, and a test of the split.

**Left:**
- build the image and make it public;
- create the compute repositories;
- run one self-test job per account.

**You will be asked:**
- how many team members confirm their accounts, and which ones;
- to make the image package public (one click on GitHub).

**Load:** about 10 short jobs per account.

### Part 2: Cleanup (done)

**What happened:**
- The carving loop, the adjoint solver, the old pattern search and the lab workflows were retired.
- What they measured is recorded in `docs/HISTORY.md`.
- The live pieces moved to `car/pipeline.py` and `car/space.py`.

**Proof nothing broke:** a reference car was fingerprinted first and rebuilt after every step,
including the folder restructure. It came out identical every time.

### Part 3: Physical measurements (chat A with the team)

**What it is:** eleven lab experiments that replace every guessed input. The most important are:
- the thrust curve on a force sensor (at least 1,000 samples per second, 5 cartridges);
- cartridge masses;
- Model Block foam density;
- timed runs of a car the team already has.

**Done:** processing scripts for every experiment, tested on synthetic data with known answers,
and `inputs/measured.json`, where every input is marked "not measured" until it is.

**Left:**
- the lab work itself, with an adult supervising every cartridge firing;
- printable lab sheets;
- processing the files the team sends.

**You will be asked:** what equipment the school has, who does the lab work, whether a reference
car with STL files exists, and the competition date.

### Part 4: Race model (done; validation with chat A)

**What it is:** the 20 m race model. It now includes:
- the measured thrust curve;
- the speed dependence of drag and the venue's air density;
- rolling, bearing and constant resistance;
- tether-guide rub;
- launch pitch;
- each axle's own wheels.

The old penalty curves made from invented points are gone.

**Proof:** it reproduces the old model to 0.01 ms on the same inputs, and it passes analytic tests.

**Left:**
- drag at several speeds (chat C supplies this);
- comparison with real timed runs, which must land within 5% under thresholds set beforehand.

### Part 5: Rules, legality, mass (chat B)

**What it is:**
- every regulation number in one file;
- legality checks at least as strict as the rules, measured on the files that get made;
- new checks for rules that were never checked;
- a mass margin that survives real-world uncertainty;
- strength margins for the scrutineering load tests.

**Already settled:** I read the regulations PDF for the questions the bible left open. These are
now answered in section 5.1.1:
- keep-clear zone sizes;
- notch height (10 mm above the halo bottom, 34 ± 1 mm);
- decal size (30 × 15 mm, 100% visible);
- the allowed components list;
- where ballast may go;
- the halo load test (2 kg at the notch);
- the chamber wall (3 mm over the minimum depth);
- the hand-finishing limit (machining marks only).

**You will be asked:**
- **ballast or no ballast** (a team decision);
- your team number and font width;
- which accounts to use for about 100 build-only jobs.

### Part 6: Low-noise CFD (chat C)

**What it is:**
- **Fixed frame.** Every car is meshed inside one fixed frame.
- **Mesh choice.** The search mesh is chosen by a written-down experiment.
- **Morphing.** Nearby designs are compared on a deformed copy of one base mesh instead of a new
  mesh, which should cut the noise about tenfold.
- **Checks.** A mesh study checks that car-to-car differences keep their sign on finer meshes.

**Left:** everything except the morphing solver.

**Load:** about 150-250 jobs of 0.5-6 hours.

**You will be asked:** which accounts to use, and whether to rent a bigger machine if the finest
runs would take more than about three days on the free machines.

### Part 7: Search (chat D builds, chat E runs)

**What it is:**
- **Stage A: screening.** Measure every setting's effect precisely by morphing.
- **Stage B: global search.** A statistical model (a Gaussian process) of the 15-25 settings that
  matter handles the noise without repeat runs.
- **Stage C: polish.** Small morphed steps around the best car.
- **Stage D: robustness.** Check the winner against manufacturing tolerances.

The settings now include centre-of-mass and thrust-line levers (ballast, chamber height), because
of the launch-pitch finding.

**Load:** the largest Part, about 700-1,100 CFD jobs.

**You will be asked:** the budget and the design-freeze date.

### Part 8: Confirm, build, race (chat E)

**What it is:**
- the best cars run on fine, wall-resolved and unsteady CFD;
- production files at 0.3 mm;
- help with milling, printing and drawings;
- build checks and a scrutineering self-check;
- track tests, comparing predicted and measured times.

**What the track can and cannot show:** about 10 runs settle the absolute time. Proving a
few-millisecond ranking between two good cars would take dozens of cartridges, so that ranking
rests on the model.

## What only you can provide

- **Accounts:** which accounts each chat may use (asked per Part).
- **People and materials:** lab equipment and people, a reference car with its STL files, and the
  competition date.
- **Team decisions:** ballast policy; which cars to build.
- **Money:** anything that costs money; the chats never pay for anything.
- **Merging:** merging `rebuild/bible` into `main`.

## Risks to watch

- **Throttling.** GitHub may slow heavy use of free runners. Keep a paid fallback in mind for
  Part 8 (bible 01 section 1.12).
- **Lab delays.** If the lab work slips, every race time stays a model estimate on the synthetic
  thrust curve. Each report says so at the top.
- **Wheel width.** The team's wheels may fail the true contact-width rule once fillets are
  excluded (13.25 and 17.25 mm overall against 13 and 17 mm minimum). Chat B checks this first.
