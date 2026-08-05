# Transfer Optimizer — test & bring-up guide

Ordered checklist to bring up the blue→red MOT→813 lattice optimizer. Do the
non-hardware steps (0–2) first; they need no ARTIQ and no atoms. Steps 3–6 are
run by **you** on the real machine — nothing here runs hardware automatically.

Everything lives on the `transfer-optimizer` branch (off `merge_branches`).

## Files
| File | What it is |
|---|---|
| `TransferOptimizer.py` | ARTIQ "server": warm kernel, applies params, runs one shot, counts lattice ROI, interleaves reference, checkpoints. |
| `mloop_optimize.py` | External M-LOOP driver (owns the optimization loop). |
| `mloop_stub_server.py` | Hardware-free stand-in for the ARTIQ server (synthetic cost) for dry-runs. |
| `opt_stages/*.json` | Per-stage param names / bounds / first_params. |
| `../Classes/CoolingClass.py` | +`record_rmot_ramp_arg`; +`rmot_pulse(bb_dur, sf_dur, att_blue, att_red)`; capture knobs `binc`/`blue_transfer_time`/`to_bb_time`/`blue_att_i`/`blue_att_f` promoted from constants to GUI args (additive, defaults unchanged). |
| `../Classes/rois.json` | +`lattice_load` ROI scheme. |

## FILL these before hardware runs
- `TransferOptimizer` GUI args: **handshake_dir**, **checkpoint_dir** (must match
  what you pass to `mloop_optimize.py`/stub), **hold_time**, **camera_rearm_chunk**.
- Camera **ROI_Scheme = `lattice_load`** (Detection group), and the
  `lattice_load` box in `../Classes/rois.json` (x,y,w,h) tight on the lattice cloud.
- Each `opt_stages/*.json`: tighten `min_boundary`/`max_boundary`/`first_params`
  to SAFE hardware ranges (currents < 7 A). Units: freq Hz, current A/volts,
  durations seconds.
- The fixed shallow **lattice depth** is set by you outside this experiment (the
  optimizer never touches the lattice).

---

## Prerequisite: install M-LOOP
In your **ARTIQ** Python env:
```
pip install M-LOOP
python -c "import mloop; print('M-LOOP', mloop.__version__)"
```

## Step 0 — Handshake + M-LOOP convergence dry-run (no ARTIQ, no atoms)
Two terminals in `Experiments/RedMOT/`, same `--handshake` dir. Start them in
**either order** — the driver re-sends its request if the server comes up later.

Terminal A (fake experiment):
```
python mloop_stub_server.py --stage opt_stages/stage1.json \
  --handshake ./_dry/handshake --checkpoint ./_dry/checkpoint
```
Terminal B (real driver):
```
python mloop_optimize.py --stage opt_stages/stage1.json \
  --handshake ./_dry/handshake --checkpoint ./_dry/checkpoint
```
**Pass:** driver runs ~120 evals; best cost approaches **−1**; `mloop_best_stage1.json`
lists params near each bound's midpoint (the stub's known optimum). JSON files
appear/disappear in `_dry/handshake`.

## Step 1 — Checkpoint / resume dry-run
Re-run Step 0 but **kill Terminal B (Ctrl-C) after ~30 evals**, then re-launch the
same Terminal B command.
**Pass:** on relaunch it prints `Seeding first_params from …best_params…` and/or
`Warm-starting learner from …learner_archive…`, and continues rather than
restarting cold. Confirm `_dry/checkpoint/progress_stage1.jsonl`
kept growing across the restart.

Cleanup: `rm -r _dry` (or delete the folder).

## Step 2 — ARTIQ import / compile check (no atoms)
In the ARTIQ env, confirm the experiment builds and the kernel compiles. Easiest:
open **`TransferOptimizer`** in the ARTIQ dashboard — if `build`/`prepare` raise,
you'll see it immediately. (Do NOT submit yet.) Sanity-check that the new
`Optimizer` argument group shows handshake/checkpoint/hold_time/etc.

If you prefer a CLI compile check of just the additive kernel hooks, run any
existing rmot experiment that calls `rmot_pulse` — defaults reproduce old behavior
(new `bb_dur`/`sf_dur` default to −1 → fall back to the GUI attributes).

---
## HARDWARE steps (run by you)

## Step 3 — Single-iteration smoke test
1. Set the GUI args (handshake/checkpoint dirs, hold_time, camera chunk),
   Camera `ROI_Scheme = lattice_load`, and put a *shallow* lattice up by hand.
2. Submit `TransferOptimizer` in the dashboard. It takes a background image, runs
   `ref_settle_shots` baseline shots, then blocks waiting for a request.
3. Hand it exactly one request (no M-LOOP needed):
   ```
   python - <<'PY'
   import json, os
   hs = r"<FILL: handshake dir>"
   os.makedirs(hs, exist_ok=True)
   req = {"seq": 0, "params": {"rmot_sf_duration": 0.025}, "stop": False}
   open(os.path.join(hs, ".t"),"w").write(json.dumps(req)); os.replace(os.path.join(hs,".t"), os.path.join(hs,"request_0.json"))
   PY
   ```
   Then touch STOP to end: create an empty file `STOP` in the handshake dir.
**Pass:** `rmot_pulse` runs, the fluorescence image lands inside the
`lattice_load` ROI (check `detection.images.current_image` applet), and
`opt.last_counts` is a sane, positive number. Adjust the ROI box if the cloud
isn't centered.

## Step 4 — Reference / drift auto-pause
Temporarily set `drift_threshold_pct` low (e.g. 3) and, mid-run, spoil the
reference (e.g. block the atom source briefly or detune by hand).
**Pass:** `opt.alert` flips to 1, the log prints the DRIFT ALERT, the loop stops
taking candidate data and keeps measuring the reference. Restore conditions →
`opt.alert` returns to 0 and it resumes. To accept a permanently shifted baseline,
touch `REBASELINE` in the handshake dir.

## Step 5 — Live Stage-1 campaign (~50–100 runs)
1. Submit `TransferOptimizer` with `stage_name = stage1`.
2. In a terminal:
   ```
   python mloop_optimize.py --stage opt_stages/stage1.json \
     --handshake "<FILL>" --checkpoint "<FILL>"
   ```
   (add `--plots` to see M-LOOP's landscape/correlation plots at the end; it's off
   by default because `plt.show()` blocks until the windows are closed.)
**Pass:** normalized cost trends downward (counts up); `opt.best_counts` climbs;
`best_params_stage1.json` holds the winner. With `--plots`, the M-LOOP
landscape plot looks sensible.

## Step 6 — Chain stages 2 → 3
Set the Stage-1 winners as the `TransferOptimizer` GUI defaults (so they become
the fixed base + reference), then repeat Step 5 with
`opt_stages/stage2.json`, then `stage3.json`.
Note: Stage 3 tunes `bmot_load_duration`, which recompiles the kernel once per
iteration (accepted, slower). Re-rotate stage 1 afterward if the optimum moved.

## Optional — verify the atoms are actually colder
The shallow-lattice count is a *proxy* for "cold + numerous". Once you have a
winner, confirm temperature dropped with your own time-of-flight measurement
(hold in the shallow lattice, release, image vs drop time). This validation is
separate from this optimizer.

---
## How it stays compile-stable (why the loop is fast)
Per-shot scalars (`bb_dur`, `sf_dur`, `hold_time`) are **kernel arguments**, and
every re-recorded DMA trace is fed **arrays as arguments** via
`record_rmot_ramp_arg` + `_record_field_ramp` — so ARTIQ compiles `do_shot` and
`_rerecord_dma` once and reuses them. The only intentional exception is
`bmot_load_duration` (Stage 3), read as `self.*` inside `rmot_pulse`.

## Troubleshooting
- **Driver `TimeoutError` waiting for response:** the experiment isn't running,
  points at a different handshake dir, or is drift-paused — check the ARTIQ log.
- **Counts always ~0 / bad=True:** wrong `lattice_load` ROI box, wrong Camera
  `ROI_Scheme`, lattice off, or `hold_time` so long everything left.
- **Loop feels slow / recompiles every shot:** a tuned param is being written as
  `self.*` and read in a kernel — keep tunables in `PARAM_ATTR`/`NO_SETATTR` as
  set up. `bmot_load_duration` is pinned once at run start (not optimized), so
  nothing should recompile per shot.
- **Camera buffer errors on long runs:** lower `camera_rearm_chunk`.
