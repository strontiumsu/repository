# Transfer Optimizer — how it works & how to use it

Closed-loop optimizer for the **blue MOT → red MOT → 813 lattice** transfer. It
maximizes the number of atoms retained in a fixed **shallow** trap after the red
MOT pulse — a single cheap number per shot that rewards *cold + numerous* atoms
at once (only atoms below the trap depth survive the hold).

This is the conceptual + usage reference. For the ordered bring-up/test checklist
see [OPTIMIZER_TESTS.md](OPTIMIZER_TESTS.md).

---

## Contents
1. [The idea in one paragraph](#the-idea)
2. [Architecture](#architecture)
3. [File map](#file-map)
4. [One shot: what actually happens](#one-shot)
5. [Parameters](#parameters)
6. [Stages & how to chain them](#stages)
7. [Running a campaign](#running)
8. [Reading the output](#output)
9. [Drift handling & pausing](#drift)
10. [Checkpointing & resuming](#resume)
11. [Customizing](#customizing)
12. [Control files & cheat sheet](#cheatsheet)

---

<a name="the-idea"></a>
## 1. The idea in one paragraph

An external **M-LOOP** process proposes a set of transfer parameters. A
long-lived **ARTIQ experiment** applies them, runs one red-MOT pulse, holds the
atoms in the (already-on, fixed-depth) trap so hot atoms escape, images the
survivors, and reports the count back as a **cost**. M-LOOP's Gaussian-process
learner uses the cost to propose the next, better set. A fixed "reference" shot
is interleaved to divide out slow drift, and everything is checkpointed so you
can stop and resume without losing progress.

<a name="architecture"></a>
## 2. Architecture

Two processes talk through a tiny **JSON file handshake** — no sockets, no shared
memory, robust on Windows.

```
  M-LOOP process (owns the loop)            ARTIQ experiment (owns the hardware)
  python mloop_optimize.py                  TransferOptimizer, submitted in dashboard
  ┌───────────────────────────┐             ┌──────────────────────────────────────┐
  │ GP/DE learner              │  request    │ host run() loop (kernel stays WARM):  │
  │ get_next_cost_dict(params):│ ──────────▶ │   read request → apply params →       │
  │   write request_<seq>.json  │   .json     │   re-record DMA → run 1 shot →        │
  │   wait  response_<seq>.json │ ◀────────── │   count → interleave reference →      │
  │   return {cost, uncer, bad}│  response   │   normalize → checkpoint → respond    │
  └───────────────────────────┘   .json      └──────────────────────────────────────┘
             ▲                                              │
             └────────── both point at the same handshake dir ─────────┘
```

Why split into two processes: M-LOOP's learners spawn their own worker
subprocesses; keeping them out of `artiq_run` avoids multiprocessing friction.
The ARTIQ side runs as **one** experiment so the kernel compiles once and the DMA
traces stay resident — no per-candidate resubmit or recompile.

**Cost convention:** M-LOOP *minimizes*, and the ARTIQ side returns
`cost = -(candidate_counts / reference_counts)`. So "more atoms" → "more
negative cost" → better. A perfect-relative-to-reference shot is about `-1`.

**Handshake files** (all in `handshake_dir`):

| File | Written by | Meaning |
|---|---|---|
| `request_<seq>.json` | driver | `{"seq": k, "params": {name: value}, "stop": false}` |
| `response_<seq>.json` | ARTIQ | `{"seq": k, "cost": .., "uncer": .., "bad": ..}` |
| `STOP` | driver / you | touch to end the ARTIQ run cleanly |
| `REBASELINE` | you | touch to accept a drifted baseline and resume |

Both requests and responses use **per-seq filenames** (temp-file + `os.replace`).
The reader finds the newest via a directory listing and opens each file exactly
once, after it's fully written — so the writer never renames over a file the
reader holds open (which on Windows raises "Access is denied"). Each side clears
stale handshake files at startup, so a restart begins fresh at seq 0.

<a name="file-map"></a>
## 3. File map

| File | Runs where | Purpose |
|---|---|---|
| [TransferOptimizer.py](TransferOptimizer.py) | ARTIQ dashboard/master | The server: warm kernel, applies params, runs a shot, counts, interleaves reference, checkpoints, responds. |
| [mloop_optimize.py](mloop_optimize.py) | terminal (ARTIQ env) | The driver: owns the M-LOOP loop; file-handshake `Interface`. |
| [mloop_stub_server.py](mloop_stub_server.py) | terminal | Hardware-free stand-in for the ARTIQ side (synthetic cost) for dry-runs. |
| [opt_stages/](opt_stages/)`*.json` | — | Per-stage param names, bounds, first values, controller settings. |
| [OPTIMIZER_TESTS.md](OPTIMIZER_TESTS.md) | — | Ordered bring-up / test checklist. |
| [../Classes/CoolingClass.py](../Classes/CoolingClass.py) | — | Additive hooks: `record_rmot_ramp_arg`, `record_sf_stage_arg`; `rmot_pulse(bb_dur, att_blue, att_red)`; single-frequency stage as the re-recordable `rmot_sf` DMA trace; capture knobs promoted to GUI args. |
| [../Classes/rois.json](../Classes/rois.json) | — | `lattice_load` ROI scheme (the count region). |

<a name="one-shot"></a>
## 4. One shot: what actually happens

`do_shot` (kernel), driven from the host loop for every candidate and every
reference shot:

```
rmot_pulse(bb_dur, att_blue, att_red)           # lattice/dipole already ON; loads atoms
delay(hold_time)                                # shallow trap: hot atoms leave
take_MOT_image(Camera)                          # existing fluorescence imaging
process_image(return_ports=["lattice"]) -> counts   # sum of the lattice_load ROI
```

`hold_time`, the trap depth, and which traps are on (`bragg_switches`, default
`0x9` = dipole+lattice) are **fixed configuration you set** — the optimizer does
not touch them. The returned `counts` is the raw objective; the host divides it
by the current reference to form the cost.

<a name="parameters"></a>
## 5. Parameters

The ARTIQ side knows how to apply any parameter listed in the `PARAM_ATTR`
registry in [TransferOptimizer.py](TransferOptimizer.py). *Which* of them are
actually varied is decided by each stage JSON's `param_names`; anything not named
stays at its GUI/base value.

**How each is applied:**

- **DMA-baked** (compression sweep: `freq_high_i`, `freq_high_f`, `span_i`,
  `span_f`, `ramp_tau`, `rmot_scan_frequency`, `atten_ramp_i`, `atten_ramp_f`,
  `rmot_bb_current`, `rmot_sf_current`, `rmot_ramp_duration`; single-frequency
  stage: `rmot_sf_freq_i`, `rmot_sf_freq_f`, `rmot_sf_atten_i`, `rmot_sf_atten_f`,
  `rmot_sf_duration`; capture/field: `bmot_current`, `bmot_ramp_duration`, `binc`,
  `blue_transfer_time`, `to_bb_time`, `blue_att_i`, `blue_att_f`): set on the host,
  the arrays are recomputed by `_prepare_rmot_ramp` / `_prepare_sf_stage` /
  `_prepare_coils`, and `_rerecord_dma` re-records the DMA traces (`rmot_ramp`,
  `rmot_sf`, field ramps) by calling `_Cooling._dma_record()`, which reads those
  `self.MOTs.*` arrays. They are read as **attributes, not kernel arguments** —
  ARTIQ's compiler serializes a list *argument* element-by-element into one
  synthesized source line, and thousands of ramp points overflow LLVM's 16-bit
  debug-info column (`value for 'column' too large`). Reading them as attributes
  (embedded by object reference) avoids that. Note: this ARTIQ recompiles every
  top-level kernel call regardless, so attribute vs argument is purely about the
  column-overflow, not compile count.
- **Kernel-arg** (`NO_SETATTR`: `rmot_bb_duration`→`bb_dur`,
  `atten_3D`→`att_blue`, `atten_3D_red`→`att_red`): forwarded straight to
  `rmot_pulse` as arguments (never written to `self`, which would recompile).

**Fixed, not optimized:**
- `bmot_load_duration` — pinned once at run start to `bmot_load_duration_fixed`
  (default 0.5 s).
- `shape_freq`, `shape_atten` — categorical; M-LOOP is continuous-only, so these
  stay on their GUI value.
- Blue-MOT / blue→red capture knobs (`bmot_current`, `binc`, `blue_att_i/f`,
  `blue_transfer_time`, `to_bb_time`, `atten_3D`, …) remain in the registry but are
  **not** in `red_mot.json`, so they stay on their GUI value. Add them to
  `param_names` if you want to optimize them later.

**Units** (must match the stage JSON): frequencies **Hz**, currents/fields **A**
(coil setpoint is DAC volts, ≈A), VVA attenuations **DAC volts** (0–9.99), AOM
attenuations **dB** (1–30), durations **seconds**.

<a name="stages"></a>
## 6. Stage config

The optimizer is scoped to a **single red-MOT stage** — one file,
`opt_stages/red_mot.json`, is the one place to edit which red-MOT params are varied
and their bounds. It covers the broadband red MOT, the compression sweep, and the
single-frequency stage (17 params):

| Stage file | Params (active) |
|---|---|
| `red_mot.json` | `rmot_bb_current, rmot_bb_duration, freq_high_i, freq_high_f, span_i, span_f, atten_ramp_i, atten_ramp_f, ramp_tau, rmot_scan_frequency, rmot_ramp_duration, rmot_sf_current, rmot_sf_freq_i, rmot_sf_freq_f, rmot_sf_atten_i, rmot_sf_atten_f, rmot_sf_duration` |

17 dimensions is a lot for a GP — trim `param_names` (and the aligned
`first/min/max` arrays) to a subset for faster convergence; the driver accepts any
length. The old three-stage blue/red/transfer workflow was removed.

**Chaining is manual** (by design): after a stage finishes, take its winners from
`best_params_<stage>.json` and set them as the corresponding **CoolingClass GUI
defaults** before launching the next stage. Those winners then form the fixed
base + reference for the next block. Re-run stage 1 at the end if later stages
moved the optimum.

<a name="running"></a>
## 7. Running a campaign

**Prerequisite (once):** `pip install M-LOOP` in your ARTIQ Python env.

**Per campaign:**
1. In the ARTIQ dashboard, open **`TransferOptimizer`** and set the `Optimizer`
   argument group:
   - `stage_name` = `red_mot` (names the checkpoint files),
   - `handshake_dir` and `checkpoint_dir` (must match the driver's flags),
   - `hold_time`, `camera_rearm_chunk`, `reference_every_N`,
     `drift_threshold_pct`, `bmot_load_duration_fixed`, `bragg_switches`.
   - In the `Detection` group set **`ROI_Scheme = lattice_load`**, and make sure
     the `lattice_load` box in [../Classes/rois.json](../Classes/rois.json) is
     tight on the trapped cloud.
   - Put up your fixed **shallow** trap by hand.
2. **Submit** `TransferOptimizer` and **start the driver** — in either order (the
   driver re-sends its request if the experiment comes up later). The experiment
   takes a background image, runs `ref_settle_shots` baseline shots, then serves
   requests; the driver:
   ```
   python mloop_optimize.py --stage opt_stages/red_mot.json \
       --handshake "<handshake_dir>" --checkpoint "<checkpoint_dir>"
   ```
4. Watch the ARTIQ terminal and the `opt.*` datasets. When M-LOOP hits
   `max_num_runs` (or `target_cost`), it writes the winner and touches `STOP`;
   the experiment restores the lasers and exits.
5. Set the winners (`best_params_red_mot.json`) as the CoolingClass GUI defaults.

To stop early: touch a file named `STOP` in the handshake dir (or Terminate the
experiment in the dashboard — `scheduler.check_pause()` handles it).

<a name="output"></a>
## 8. Reading the output

**ARTIQ terminal** (plain prints from the host loop):
```
[baseline] reference baseline = 1180.0
[iter 7 | seq 6] shot params: span_f=1.1e+06, atten_ramp_f=0.42, rmot_sf_current=2.3, ...
[iter 7 | seq 6] counts=1523 ref=1185.0 cost=-1.2852 bad=False
[reference] counts=1190 ref_ema=1185.0 drift=+0.4%
```

**Datasets** (broadcast, watch in the dashboard / an applet):

| Dataset | Meaning |
|---|---|
| `opt.iteration` | successful-shot counter |
| `opt.last_counts` | counts from the most recent candidate |
| `opt.best_cost` / `opt.best_counts` | best so far |
| `opt.reference` / `opt.reference_baseline` | drift-normalization reference (EMA / initial) |
| `opt.drift` | fractional reference drift vs baseline |
| `opt.alert` | 1 while drift-paused, else 0 |
| `opt.last_bad` | 1 if the last candidate was flagged bad |

**Checkpoint files** (in `checkpoint_dir`):

| File | Written by | Contents |
|---|---|---|
| `progress_<stage>.jsonl` | ARTIQ | one line per shot: seq, params, counts, reference, cost, timestamp |
| `best_params_<stage>.json` | ARTIQ | best cost + full param set so far |
| `mloop_best_<stage>.json` | driver | M-LOOP's final best params for the stage |
| `controller_archive_<stage>*`, `learner_archive_<stage>*` | driver | M-LOOP archives (used for warm-start) |

M-LOOP archives are written to `<checkpoint_dir>/M-LOOP_archives/` (the driver
runs from the checkpoint dir), so warm-start finds them no matter where you launch
from. Pass `--plots` to `mloop_optimize.py` to pop up M-LOOP's landscape/correlation
plots at the end — off by default because `plt.show()` blocks until you close the
windows (which would stall the driver from sending STOP).

<a name="drift"></a>
## 9. Drift handling & pausing

Every `reference_every_N` candidates, one shot is run with the **base**
(standard) parameters. The cost is `-(candidate / reference_ema)`, so slow drift
in atom source flux or laser power divides out.

If the reference drifts beyond `drift_threshold_pct` from its baseline, the
experiment:
- sets `opt.alert = 1` and prints a `DRIFT ALERT`,
- **pauses** — stops taking candidate data and keeps re-measuring the reference
  (M-LOOP simply waits for the pending response),
- **resumes** automatically once the reference recovers to within half the
  threshold, or immediately if you touch a `REBASELINE` file (which accepts the
  current level as the new baseline).

The candidate that triggered the pause is returned as `bad` so M-LOOP discards it.

<a name="resume"></a>
## 10. Checkpointing & resuming

Nothing is lost if a process dies or you stop to restabilize:
- Every shot is appended to `progress_<stage>.jsonl` **before** the response is
  written.
- `best_params_<stage>.json` is rewritten whenever a new best appears.
- The driver keeps M-LOOP archives with a stable, stage-named filename.

**To resume a stage**, just relaunch the driver with the same `--stage` /
`--checkpoint`. It will:
- seed `first_params` from `best_params_<stage>.json` if present (restart from the
  best known point), and
- pass the newest `learner_archive_<stage>*` as `training_filename` so the GP
  starts informed by all prior (param, cost) data.

Re-measure a fresh baseline first (the drift may have moved while you were away) —
just resubmit `TransferOptimizer`, which always re-runs the baseline shots.

<a name="customizing"></a>
## 11. Customizing

**Change bounds / first values / run count:** edit `red_mot.json`. `param_names`
order MUST match `min_boundary` / `max_boundary` / `first_params`. Keep
`rmot_bb_current` and `rmot_sf_current` ≤ 7 (MAX_CURRENT). The compressed sweep
bottom is `(freq_high - span)`; keep `span` ≤ the top so the sweep does not invert.
Infeasible candidates are auto-flagged `bad`, not fatal — but tight bounds waste
fewer shots.

**Add a parameter to a stage:** if it's already in `PARAM_ATTR`, just add its
name + bounds to the stage JSON. If it's a brand-new knob, add it to `PARAM_ATTR`
(and to `NO_SETATTR` if it should be forwarded to `rmot_pulse` as a kernel arg
rather than baked into DMA).

**Change the objective:** the cost is formed in `run()` from the `lattice` ROI
count. To use a different signal (e.g. a ratio of two ROIs, or a Gaussian-fit
amplitude), change what `do_shot` returns / how `cost` is computed there.

**Controller choice:** in the stage JSON, `controller_type` can be
`gaussian_process` (sample-efficient, default), `differential_evolution`
(robust, no model), `neural_net`, or `random`. Keep `cost_has_noise: true`.

**Dry-run any change with no hardware:** run `mloop_stub_server.py` against the
same stage config in one terminal and `mloop_optimize.py` in another (see
[OPTIMIZER_TESTS.md](OPTIMIZER_TESTS.md) step 0) — it round-trips the exact file
protocol with a synthetic cost.

<a name="cheatsheet"></a>
## 12. Control files & cheat sheet

In the **handshake dir**:
- `STOP` — touch to end the ARTIQ run.
- `REBASELINE` — touch during a drift pause to accept the new baseline and resume.

**Start a stage:**
```
# 1) submit TransferOptimizer in the dashboard (stage_name + dirs + ROI set)
# 2) then:
python mloop_optimize.py --stage opt_stages/red_mot.json \
    --handshake "<dir>" --checkpoint "<dir>"
```

**Stop early:** `touch <handshake_dir>/STOP`  (or Terminate in the dashboard)

**Resume:** rerun the same driver command; submit the experiment again first.

**Common gotchas:** driver `TimeoutError` → experiment not running / wrong
handshake dir / drift-paused. Counts always ~0 → wrong `lattice_load` ROI or
`ROI_Scheme`, trap off, or `hold_time` too long. Loop feels slow → a tunable is
being written to `self.*` and read in a kernel (should be in `PARAM_ATTR` /
`NO_SETATTR`). See [OPTIMIZER_TESTS.md](OPTIMIZER_TESTS.md) for the full
troubleshooting list.
