# Red-MOT Optimizer — how it works (internals)

A code-level walkthrough of the closed-loop optimizer that maximizes atom transfer
into the **813 nm lattice** after the **blue → red MOT** sequence. This is the
"how the machinery actually works" companion to
[OPTIMIZER_README.md](OPTIMIZER_README.md) (which is the usage / bring-up guide).
If you just want to *run* a campaign, read that one first; read this when you need
to understand, debug, or modify the loop.

---

## 1. The 10,000-foot view

The optimizer is a **two-process feedback loop** joined by a **JSON file
handshake**:

```
  ┌─────────────────────────────┐   request_<seq>.json    ┌──────────────────────────────┐
  │  mloop_optimize.py          │  ─────────────────────▶ │  TransferOptimizer.py        │
  │  (plain Python, a terminal) │                         │  (ARTIQ experiment, master)  │
  │                             │   response_<seq>.json   │                              │
  │  owns the OPTIMIZER         │  ◀───────────────────── │  owns the HARDWARE           │
  │  (M-LOOP GP learner)        │                         │  (one warm kernel)           │
  └─────────────────────────────┘                         └──────────────────────────────┘
                    │                                                   │
                    └──────── both point at the same handshake dir ─────┘
```

- **`mloop_optimize.py`** (the file open in your editor) is a *plain* Python
  script — **not** an ARTIQ experiment. It runs M-LOOP's Gaussian-process learner,
  which proposes candidate parameter sets and consumes measured costs.
- **`TransferOptimizer.py`** runs *inside* the ARTIQ master/dashboard as one
  long-lived experiment. It holds the compiled kernel and DMA traces resident,
  applies a candidate, fires **one** red-MOT-into-lattice shot, images, counts the
  surviving atoms, and reports a cost.

**Why two processes?** M-LOOP's learners spawn their own worker subprocesses.
Running that inside `artiq_run` causes multiprocessing friction. Keeping the
learner in a separate plain-Python process — and the ARTIQ side as a *single*
experiment — means the kernel compiles **once** and the DMA stays resident. No
per-candidate resubmit, no recompile per candidate.

There is also a **hardware-free stub**, `mloop_stub_server.py`, that speaks the
identical protocol but returns a synthetic analytic cost. It lets you dry-run the
entire driver + handshake + resume machinery with zero hardware.

---

## 2. The objective — what "cost" means

The physical objective is **number of atoms retained in a fixed, shallow lattice**
after the red-MOT pulse plus a fixed hold. Because the trap depth is fixed and
shallow, only atoms *below* the trap depth survive the `hold_time` — so this single
scalar rewards **cold *and* numerous** atoms simultaneously. `hold_time` acts as a
temperature proxy: hotter clouds leak out during the hold.

The count is turned into a cost the optimizer minimizes:

```
cost = -(candidate_counts / reference_counts)
```

- **M-LOOP minimizes**, so *more atoms → more-negative cost → better.*
- A candidate as good as the reference scores ≈ `-1`.
- `reference_counts` is a slowly-tracked baseline (see §6) that divides out drift.

The driver passes this cost straight through — it does **not** re-derive it. The
sign convention lives entirely on the ARTIQ side.

---

## 3. The handshake protocol (the contract between the two processes)

All communication is files in one shared `handshake_dir`. No sockets, no shared
memory — deliberately, because it is robust on Windows and survives either process
restarting.

| File | Written by | Payload |
|---|---|---|
| `request_<seq>.json` | driver | `{"seq": k, "params": {name: value, …}, "stop": false}` |
| `response_<seq>.json` | ARTIQ | `{"seq": k, "cost": .., "uncer": .., "bad": ..}` |
| `STOP` | driver / you | empty file; touch to end the ARTIQ run cleanly |
| `REBASELINE` | you | empty file; touch to accept a drifted baseline and resume |

### Why per-`seq` filenames + temp-file + `os.replace`

A single shared filename (e.g. always `request.json`) causes a classic Windows
race: the writer tries to rename over a name the reader currently has open, and
Windows raises `PermissionError` ("Access is denied"). The design avoids this on
**both** sides:

1. **Unique name per sequence number** — the reader never has `request_<k>.json`
   open before it exists, and each file is opened *exactly once* after it is fully
   written.
2. **Atomic write** — write to `.request_<k>.tmp`, then `os.replace()` onto the
   final name so a reader never sees a half-written file. `os.replace` is atomic
   on the same volume.
3. **Retry the rename anyway** — `_atomic_write_json` (driver) and
   `_atomic_replace` (ARTIQ) retry the `os.replace` up to 100× with a 20 ms delay,
   as belt-and-suspenders against a transient lock from antivirus or the file
   indexer briefly holding the destination.

```python
# mloop_optimize.py — the atomic-write primitive
def _atomic_write_json(tmp, dst, obj, retries=100, delay=0.02):
    with open(tmp, "w") as f:
        json.dump(obj, f)
    for _ in range(retries):
        try:
            os.replace(tmp, dst)   # atomic on same volume; may briefly be denied on Windows
            return
        except OSError as e:
            last = e; time.sleep(delay)
    raise last
```

### Reader discipline

The ARTIQ side (`_poll_request`) and the stub both **scan the directory**, pick
the file with the **largest** `seq`, and open it once. They ignore older `seq`
values (`self._last_seq`), so a duplicate re-send of an already-processed seq is
harmless.

---

## 4. Start-order independence (a subtle but important detail)

You can launch the driver and the experiment in **either order**. Both sides wipe
stale handshake files on startup. So consider: the driver starts first, writes
`request_0.json`, then the experiment starts and *deletes* it as part of its
cleanup. Without a fix, the driver would wait forever for a response to a request
that no longer exists.

The fix is in the driver's `_wait_response`: while waiting, if the request file
has vanished **and** no response has arrived within `resend_interval` (3 s), it
**re-sends** the request:

```python
# mloop_optimize.py :: ArtiqFileInterface._wait_response
if (not reqpath.exists()) and (time.time() - last_send > resend_interval):
    self._write_request(seq, pdict, stop=False)   # safe: duplicate seq is ignored
    last_send = time.time()
```

Because the reader ignores a `seq` it already handled, re-sending is always safe.
This is what makes "start them in either order" work.

If nothing ever answers, the driver raises a `TimeoutError` after
`response_timeout_s` (default 3600 s, from the stage JSON) with a message that
reminds you to check that the experiment is running, pointed at the same
handshake dir, and not drift-paused.

---

## 5. One iteration, end to end

Trace a single optimizer step through both processes:

**Driver side** (`ArtiqFileInterface.get_next_cost_dict`), called by M-LOOP once
per candidate:

1. M-LOOP hands in `params_dict['params']` — an **ordered array** in
   `param_names` order.
2. The driver zips it back into a **named** dict `{name: value}` and writes
   `request_<seq>.json`.
3. It **blocks** in `_wait_response`, polling every 50 ms (re-sending as in §4).
4. It returns `{'cost', 'uncer'?, 'bad'?}` to M-LOOP, which folds the result into
   the GP and proposes the next candidate.

**ARTIQ side** (`TransferOptimizer_exp.run`), the server loop:

1. `_wait_for_request()` — polls the dir; also watches for `STOP` and an idle
   timeout.
2. Coerce every param to `float`; call `self.shot(**overrides)`.
3. `shot()` (host): merge `{**DEFAULTS, **overrides}`, `setattr` each onto EVERY
   owner that has it (the experiment, `self.MOTs`, and `self.MOTs.dds` — the DDS
   instance is the source of truth for `scale_/atten_/freq_*`), recompute all ramp
   arrays with `prepare_cooling()`, ensure the camera is armed, then run `_rerecord`
   and `_shot_kernel`.
4. `_rerecord` (kernel): erase all six DMA traces (reverse of record order) and
   re-record them via `_dma_record()` from the freshly-computed `self.*` arrays.
   Erase-first frees the core-device SDRAM top-down before re-allocating — the same
   method `rmot_pulse_sweep._rerecord` uses.
5. `_shot_kernel` (kernel): run `rmot_pulse()`, `delay(hold_time)`, image, and
   return the `lattice` ROI count.
6. Form `cost` and `uncer`, checkpoint, and write `response_<seq>.json`.

```
DEFAULTS ⊕ candidate  →  _push (setattr on self/MOTs/dds)  →  prepare_cooling()  ──host──┐
                                                                                          ▼
   erase all traces → _dma_record() → rmot_pulse() → delay(hold_time) → image → lattice count   (kernel)
                                                                                          │
                        cost = -count / reference_ema  ──────────────────────────────────┘
```

### The kernel-argument gotcha (why ramps are attributes, not arguments)

The ramp arrays (thousands of points) are read inside the kernel as `self.*`
**attributes**, never passed as kernel **arguments**. ARTIQ's compiler serializes
a *list argument* element-by-element into one synthesized source line; thousands of
points overflow LLVM's 16-bit debug-info column counter (`value for 'column' too
large`). Reading them as attributes sidesteps the synthesized line entirely. ARTIQ
recompiles every top-level kernel call regardless, so there is no
attribute-vs-argument performance cost — only the overflow to avoid. (This was the
fix in commit `a6179a8`.)

### Failure isolation

A candidate can be physically infeasible — e.g. a coil setpoint above
`MAX_CURRENT` trips an assertion in `_build_field_ramp`. The server wraps the shot
in `try/except`: **any** exception is reported as `bad=True` with cost `0.0`
instead of crashing the campaign. M-LOOP then learns that region is infeasible and
steers away.

---

## 6. Drift handling — interleaved reference + auto-pause

Atom flux and laser power drift over a multi-hour campaign. To keep costs
comparable, every `REFERENCE_EVERY_N` (default 5) successful candidates the server
runs **one reference shot** with the pure `DEFAULTS` parameters and updates an
exponential moving average:

```python
self._current_ref = 0.5 * self._current_ref + 0.5 * max(1.0, float(ref))
drift = (self._current_ref - self._ref_baseline) / self._ref_baseline
```

Because cost divides by `self._current_ref`, slow common-mode drift cancels.

If `|drift|` exceeds `DRIFT_THRESHOLD_PCT` (default 15%), the server:

- sets `opt.alert = 1`, prints a **DRIFT ALERT**,
- flags the triggering candidate `bad` so M-LOOP discards it,
- **pauses** in `_pause_until_recovered()` — it stops serving candidates and keeps
  re-measuring the reference. M-LOOP simply blocks on the pending response, so no
  candidate data is taken during a drift excursion.

It resumes automatically when drift recovers to **half** the threshold, or
immediately if you touch a `REBASELINE` file (which accepts the current level as
the new baseline). This is the one place the two-process design pays off doubly:
the learner is oblivious to the pause; it just experiences a slow response.

---

## 7. Checkpointing, seeding, and warm-start (the resume story)

The system is designed so **a rerun continues, never starts cold.** Three separate
artifacts feed a resume, and the driver's `main()` wires them up before creating
the controller.

### What gets written (all in `checkpoint_dir`)

| File | Written by | Contents |
|---|---|---|
| `progress_<stage>.jsonl` | ARTIQ | one JSON line per shot: `seq, it, ts, params, counts, reference, cost` (appended **before** the response is sent) |
| `best_params_<stage>.json` | ARTIQ | best cost + **full** param set (`DEFAULTS ⊕ overrides`) → reproducible winner |
| `mloop_best_<stage>.json` | driver | M-LOOP's final `best_params` / `best_cost` for the stage |
| `M-LOOP_archives/…learner_archive_<stage>*` | driver (M-LOOP) | the (params, cost) training data — the warm-start fuel |
| `M-LOOP_archives/…controller_archive_<stage>*` | driver (M-LOOP) | controller state (not reliably re-loadable as training data) |

### Three resume mechanisms

1. **Continue the counters.** `_max_index()` scans `progress_<stage>.jsonl` for the
   largest `seq` (driver) and largest `it` (server) so request IDs and the
   iteration index keep climbing across restarts rather than colliding with old
   rows.

2. **Seed `first_params` from the best known point.** `maybe_seed_first_params()`
   tries, in priority order: `mloop_best_<stage>.json` → `best_params_<stage>.json`
   → the best-cost row of `progress_<stage>.jsonl` → finally the config's
   `first_params`. So a resumed run's very first candidate is the previous best.

3. **Warm-start the GP with all prior data.** `find_training_archive()` finds the
   newest **learner** archive for this stage (it searches `checkpoint_dir`,
   `checkpoint_dir/M-LOOP_archives/`, `./M-LOOP_archives/`, and `.`, because
   M-LOOP 3.3.4 ignores `archive_dir` for the default output location). It is
   passed as `training_filename` so the Gaussian process starts informed by every
   past (param, cost) pair, not just the seed point.

   > This is why the driver `os.chdir(checkpoint_dir)` before starting M-LOOP —
   > it forces M-LOOP's default `./M-LOOP_archives/` to be created *there*
   > deterministically, so a later run can always find it.

### Defensive controller construction

M-LOOP versions disagree on which kwargs `create_controller` accepts, and a stale
training archive can be incompatible. `main()` degrades gracefully in layers:

```
try full kwargs
  └─ TypeError (unknown kwarg)  → retry with only the universally-supported kwargs
       └─ still fails           → drop training_filename, retry
  └─ other Exception           → drop training_filename, retry
```

So a bad archive **never** prevents starting — resume degrades to at worst
"restart from the best point without GP history."

---

## 8. The stage config file

`opt_stages/red_mot.json` is the single place that decides **which** variables are
optimized and their bounds. It is read by the driver, the stub, and is echoed to
the server through `param_names`. Key fields:

- `param_names` / `first_params` / `min_boundary` / `max_boundary` — four
  **index-aligned, equal-length** arrays. Every name must be a key in
  `TransferOptimizer.DEFAULTS`.
- `controller_type` — `gaussian_process` (default, sample-efficient),
  `differential_evolution`, `neural_net`, or `random`.
- `cost_has_noise: true` — tells the GP the objective is stochastic.
- `max_num_runs`, `response_timeout_s`, optional `target_cost`.

The current `red_mot.json` optimizes **15 parameters** spanning the broadband red
MOT, the compression sweep, and the single-frequency stage. 15 is high-dimensional
for a GP — trimming `param_names` (and the aligned arrays) to a subset converges
faster; the driver accepts any length.

Categorical knobs (`shape_freq`, `shape_atten`) can't be optimized by
continuous-only M-LOOP, so they live only in `DEFAULTS` and are set by hand.

---

## 9. Dry-running with no hardware

`mloop_stub_server.py` replaces the entire ARTIQ side. For each request it computes
a synthetic count as a noisy Gaussian bump peaked at the **midpoint** of every
parameter's bounds:

```python
z = ((p - opt) / width) ** 2                 # opt = 0.5*(lo+hi), width = 0.30*(hi-lo)
counts = A * exp(-0.5 * sum(z)) * (1 + noise*randn())
cost   = -counts / A
```

Run the stub and the driver in two terminals pointed at the same `--handshake`
dir; M-LOOP should converge toward the bounds-midpoint of every parameter (cost
→ ≈ −1). Because the stub mirrors the real server's file protocol *and*
checkpoint writes, it exercises the exact handshake, drift-free cost path, and
resume/warm-start flow. This is the fastest way to validate a change to the driver.

---

## 10. Quick reference — who owns what

| Concern | Lives in | Notes |
|---|---|---|
| Optimization algorithm (GP, DE, …) | `mloop_optimize.py` → M-LOOP | The learner and its worker subprocesses. |
| Candidate → hardware, one shot, count | `TransferOptimizer.py` `shot()` / `_shot_kernel` | The only place hardware is touched. |
| Cost sign + drift normalization | `TransferOptimizer.py` `run()` | `cost = -counts / reference_ema`. |
| Ramp math | `CoolingClass.prepare_cooling()` / `_dma_record()` | Recomputed every shot from `self.*`. |
| Which params vary + bounds | `opt_stages/red_mot.json` | Index-aligned arrays. |
| Baselines for every variable | `TransferOptimizer.DEFAULTS` | Set winners here to lock them in. |
| Handshake dirs, drift %, camera re-arm | `TransferOptimizer.CONFIG` block | Must match the driver's `--handshake` flag. |

**Control files** (in the handshake dir): `STOP` to end the run; `REBASELINE` to
accept a drifted baseline during a pause.

---

*See [OPTIMIZER_README.md](OPTIMIZER_README.md) for the usage guide and
[OPTIMIZER_TESTS.md](OPTIMIZER_TESTS.md) for the ordered bring-up checklist.*
