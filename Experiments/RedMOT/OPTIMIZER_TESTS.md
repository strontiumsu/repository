# Transfer Optimizer — test & bring-up guide

Ordered checklist to bring up the blue→red MOT→813 lattice optimizer. Do the
non-hardware steps (0–2) first; they need no ARTIQ and no atoms. Steps 3–6 are
run by **you** on the real machine — nothing here runs hardware automatically.

Everything lives on the `transfer-optimizer` branch (off `merge_branches`).

## Files
| File | What it is |
|---|---|
| `TransferOptimizer.py` | ARTIQ "server": `DEFAULTS` + `shot(**overrides)`; M-LOOP loop runs one shot, counts lattice ROI, interleaves reference, checkpoints. |
| `mloop_optimize.py` | External M-LOOP driver (owns the optimization loop). |
| `mloop_stub_server.py` | Hardware-free stand-in for the ARTIQ server (synthetic cost) for dry-runs. |
| `opt_stages/red_mot.json` | The single red-MOT stage: param names / bounds / first_params (names = `DEFAULTS` keys). |
| `../Classes/CoolingClass.py` | `rmot_pulse()` reads per-shot values from `self.*`; `_dma_record()` records `rmot_ramp`/`rmot_sf`/field ramps from `self.*` (`record_sf_stage_arg` builds `rmot_sf`). |
| `../Classes/rois.json` | +`lattice_load` ROI scheme. |

## FILL these before hardware runs
- `CONFIG` block in `TransferOptimizer.py`: **HANDSHAKE_DIR**, **CHECKPOINT_DIR**
  (must match what you pass to `mloop_optimize.py`/stub), plus `CAMERA_REARM_CHUNK`
  etc.
- `DEFAULTS` block: sane baselines for every variable, including **hold_time**.
- Camera **ROI_Scheme = `lattice_load`** (Detection group), and the
  `lattice_load` box in `../Classes/rois.json` (x,y,w,h) tight on the lattice cloud.
- `opt_stages/red_mot.json`: tighten `min_boundary`/`max_boundary`/`first_params`
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
python mloop_stub_server.py --stage opt_stages/red_mot.json \
  --handshake ./_dry/handshake --checkpoint ./_dry/checkpoint
```
Terminal B (real driver):
```
python mloop_optimize.py --stage opt_stages/red_mot.json \
  --handshake ./_dry/handshake --checkpoint ./_dry/checkpoint
```
**Pass:** driver runs ~120 evals; best cost approaches **−1**; `mloop_best_red_mot.json`
lists params near each bound's midpoint (the stub's known optimum). JSON files
appear/disappear in `_dry/handshake`.

## Step 1 — Checkpoint / resume dry-run
Re-run Step 0 but **kill Terminal B (Ctrl-C) after ~30 evals**, then re-launch the
same Terminal B command.
**Pass:** on relaunch it prints `Seeding first_params from …best_params…` and/or
`Warm-starting learner from …learner_archive…`, and continues rather than
restarting cold. Confirm `_dry/checkpoint/progress_red_mot.jsonl`
kept growing across the restart.

Cleanup: `rm -r _dry` (or delete the folder).

## Step 2 — ARTIQ import / compile check (no atoms)
In the ARTIQ env, confirm the experiment builds and the kernel compiles. Easiest:
open **`TransferOptimizer`** in the ARTIQ dashboard — if `build`/`prepare` raise
(e.g. a typo'd `DEFAULTS` key trips the validation `KeyError`), you'll see it
immediately. (Do NOT submit yet.)

If you prefer a CLI compile check of just the pulse, run any existing rmot
experiment that calls `rmot_pulse()` — it reads every per-shot value from `self.*`;
the single-frequency stage plays the `rmot_sf` DMA trace built from those values.

---
## HARDWARE steps (run by you)

## Step 3 — Single-iteration smoke test
1. Set `CONFIG` (handshake/checkpoint dirs, camera chunk) + `DEFAULTS` (hold_time,
   ...), Camera `ROI_Scheme = lattice_load`, and put a *shallow* lattice up by hand.
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

## Step 5 — Live red-MOT campaign (~50–200 runs)
1. Submit `TransferOptimizer` (`CONFIG.STAGE_NAME = "red_mot"`).
2. In a terminal:
   ```
   python mloop_optimize.py --stage opt_stages/red_mot.json \
     --handshake "<FILL>" --checkpoint "<FILL>"
   ```
   (add `--plots` to see M-LOOP's landscape/correlation plots at the end; it's off
   by default because `plt.show()` blocks until the windows are closed.)
**Pass:** normalized cost trends downward (counts up); `opt.best_counts` climbs;
`best_params_red_mot.json` holds the winner. With `--plots`, the M-LOOP
landscape plot looks sensible.

## Step 6 — Apply the winners
Copy the `best_params_red_mot.json` winners into the `DEFAULTS` block (they become
the new baseline). This is a single red-MOT stage — no blue/transfer chaining. To
also tune blue-MOT / capture knobs later, add their names + bounds to
`red_mot.json` (they are already `DEFAULTS` keys); 17 params is already
high-dimensional, so consider trimming rather than growing.

## Optional — verify the atoms are actually colder
The shallow-lattice count is a *proxy* for "cold + numerous". Once you have a
winner, confirm temperature dropped with your own time-of-flight measurement
(hold in the shallow lattice, release, image vs drop time). This validation is
separate from this optimizer.

---
## DMA re-record & the LLVM "column too large" trap
This ARTIQ recompiles every top-level kernel call (`Core.run` always calls
`compile()`), so nothing is "compile-once" — don't design around avoiding
recompiles. What DOES matter: the per-shot ramp arrays must NOT be passed as
**kernel arguments**. ARTIQ's compiler serializes a `list` argument
element-by-element onto a single synthesized source line; the thousands of ramp
points push LLVM's 16-bit debug-info column past 65535 → `RuntimeError: LLVM IR
parsing error / value for 'column' too large`. So `shot()` sets the arrays as
`self.MOTs.*` attributes and `_shot_kernel` calls `_Cooling._dma_record()`, which
reads them as **attributes** (embedded by object reference, not enumerated) — the
same path `init_cooling` uses. Only scalars ride as kernel arguments. **Rule: never
pass a large list to a `@kernel`; read it from `self.*`.**

## Troubleshooting
- **`KeyError: DEFAULTS key '...'` at prepare:** a `DEFAULTS` key isn't a real
  `_Cooling`/optimizer attribute (typo). Fix the key.
- **Driver `TimeoutError` waiting for response:** the experiment isn't running,
  points at a different handshake dir (`CONFIG.HANDSHAKE_DIR` ≠ driver flag), or is
  drift-paused — check the ARTIQ log.
- **Counts always ~0 / bad=True:** wrong `lattice_load` ROI box, wrong Camera
  `ROI_Scheme`, lattice off, or `hold_time` so long everything left.
- **`value for 'column' too large` on compile:** a large list was passed to a
  `@kernel` — read it from `self.*` instead.
- **Camera buffer errors on long runs:** lower `CAMERA_REARM_CHUNK`.
