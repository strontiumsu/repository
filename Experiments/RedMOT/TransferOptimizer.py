# -*- coding: utf-8 -*-
"""
TransferOptimizer.py

ARTIQ "optimizer server" for closed-loop optimization of the red MOT (broadband
-> compression -> single-frequency) load into the 813 lattice.

The whole experiment is driven through ONE clean entry point:

    counts = self.shot(**overrides)

`shot()` takes any subset of the experiment variables (everything else falls back
to DEFAULTS), pushes them into the hardware, runs a single rmot_pulse shot, images,
and returns the lattice-ROI counts. All the attribute / DMA / ramp plumbing is
hidden inside it. To try something by hand:

    self.shot(freq_high_i=180.0e6, rmot_sf_duration=0.03)

Two editable blocks live at the top of this file:
  * CONFIG   — operational settings (handshake dirs, drift, camera, ...).
  * DEFAULTS — every experiment variable and its default value.

The M-LOOP server loop below is a thin wrapper: it receives a candidate parameter
set from an external M-LOOP process over a JSON file handshake, calls
`shot(**candidate)`, normalizes against an interleaved reference shot, and writes
the cost back. The optimizer loop itself is owned by `mloop_optimize.py`.

Handshake protocol (files in HANDSHAKE_DIR)
-------------------------------------------
  request_<seq>.json     {"seq": int, "params": {name: value}, "stop": bool}
  response_<seq>.json    {"seq": int, "cost": float, "uncer": float, "bad": bool}
  STOP                   (touch to end the run cleanly)
  REBASELINE             (touch to accept a drifted baseline and resume)
Per-seq filenames + temp-file/os.replace avoid the Windows rename/open collision a
single shared name causes.

Cost convention: M-LOOP MINIMIZES, so cost = -(candidate_counts / reference).
"""

import os
import json
import time
from pathlib import Path

import numpy as np

from artiq.experiment import (  # pyright: ignore[reportMissingImports]
    EnvExperiment, kernel, delay, ms, now_mu, TInt32,
)

from CoolingClass import _Cooling  # pyright: ignore[reportMissingImports]
from CameraClass import _Camera    # pyright: ignore[reportMissingImports]
from BraggClass import _Bragg      # pyright: ignore[reportMissingImports]


# =========================================================================
# CONFIG — operational settings (edit here; not optimized)
# =========================================================================
# Dirs MUST match the --handshake / --checkpoint flags passed to mloop_optimize.py.
HANDSHAKE_DIR   = r"C:\Users\sr\Documents\Artiq\ARTIQ_opt"
CHECKPOINT_DIR  = r"C:\Users\sr\Documents\Artiq\ARTIQ_opt"
STAGE_NAME      = "red_mot"     # names the checkpoint / progress files
BRAGG_SWITCHES  = 0x9           # dipole (bit0) + lattice (bit3) on for the shot

REFERENCE_EVERY_N   = 5         # take an interleaved reference shot every N candidates
DRIFT_THRESHOLD_PCT = 15.0      # pause if the reference EMA drifts beyond this
REF_SETTLE_SHOTS    = 3         # baseline reference shots at start
CAMERA_REARM_CHUNK  = 50        # re-arm the camera every this many frames
IDLE_TIMEOUT_S      = 600.0     # stop if no request arrives for this long
POLL_S              = 0.05      # request-poll interval
PAUSE_POLL_S        = 2.0       # reference-poll interval while paused on drift


# =========================================================================
# DEFAULTS — every experiment variable + default value (edit / override here)
# =========================================================================
# Override any subset per shot:  self.shot(freq_high_i=180e6, rmot_sf_duration=0.03)
# Keys are _Cooling attribute names (plus hold_time). Set winners here to lock them
# in as the new baseline. Units: frequencies Hz, currents/fields A (DAC volts),
# durations seconds, VVA atten DAC volts (0-9.99), Urukul atten dB.
DEFAULTS = {
    # --- Blue MOT + blue->red capture ---
    "bmot_current":        5.0,
    "bmot_ramp_duration":  50e-3,
    "bmot_load_duration":  0.5,
    "binc":                1.0,
    "blue_transfer_time":  50e-3,
    "blue_att_i":          6.0,
    "blue_att_f":          30.0,
    # --- Broadband red MOT + ramp-to-broadband ---
    "rmot_bb_current":     0.4,
    "rmot_bb_duration":    50e-3,
    "to_bb_time":          15e-3,
    # --- Compression sweep ---
    "freq_high_i":         180.5e6,   # swept top of the modulation-depth sweep, start
    "freq_high_f":         180.0e6,   # swept top, end
    "span_i":              6.0e6,     # modulation depth below the top, start
    "span_f":              1.1e6,     # modulation depth, end
    "atten_ramp_i":        9.99,      # VVA (external) atten ramp, start (DAC V)
    "atten_ramp_f":        0.10,      # VVA atten ramp, end
    "ramp_tau":            0.5,       # shape time-constant for exp/expinv shapes
    "rmot_scan_frequency": 30e3,      # DRG modulation frequency
    "rmot_ramp_duration":  85e-3,
    "rmot_sf_current":     2.0,
    "shape_freq":          "lin",     # freq-span shape (categorical; set by hand)
    "shape_atten":         "exp",     # VVA-atten shape (categorical; set by hand)
    # --- Single-frequency stage (Urukul RF atten stepped) ---
    "rmot_sf_freq_i":      180.0e6,
    "rmot_sf_freq_f":      180.0e6,
    "rmot_sf_atten_i":     9.0,       # dB
    "rmot_sf_atten_f":     9.0,       # dB
    "rmot_sf_duration":    25e-3,
    # --- Beam power + imaging ---
    "atten_3D":            6.0,       # 3D blue AOM atten (dB)
    "atten_3D_red":        9.0,       # 3D red AOM atten (dB)
    "freq_3D":             180.0e6,   # 3D blue MOT-loading frequency
    "f_MOT3D_detect":      180.0e6,   # 3D blue imaging frequency
    "Detection_pulse_time": 0.02e-3,  # imaging pulse length
    # --- Optimizer shot ---
    "hold_time":           30e-3,     # shallow-lattice hold: hot atoms escape (the T proxy)
}


def _atomic_replace(tmp, dst, retries=100, delay=0.02):
    """os.replace() with retry. On Windows the rename raises PermissionError/
    OSError if another process (the M-LOOP driver polling response files) has
    `dst` open at that instant; retry until its short-lived handle is released."""
    last = None
    for _ in range(retries):
        try:
            os.replace(tmp, dst)
            return
        except OSError as e:
            last = e
            time.sleep(delay)
    raise last


def _max_index(progress_path, key, default):
    """Largest integer `key` across a progress_*.jsonl (to continue the iteration
    index across resumes). Returns `default` if missing/empty/unreadable."""
    mx = default
    try:
        with open(progress_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    mx = max(mx, int(json.loads(line).get(key, default)))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
    except OSError:
        pass
    return mx


class TransferOptimizer_exp(EnvExperiment):

    # ------------------------------------------------------------------
    # build — devices + child controllers + operational config
    # ------------------------------------------------------------------
    def build(self):
        self.setattr_device("core")
        self.setattr_device("core_dma")
        self.setattr_device("scheduler")

        # composed hardware controllers
        self.MOTs = _Cooling(self)
        self.Bragg = _Bragg(self)     # only to init the lattice/dipole AOMs on
        self.Camera = _Camera(self)

        # operational config (edit the CONFIG block above). Kept as plain
        # attributes so the M-LOOP server helpers can read self.<name>.
        self.stage_name = STAGE_NAME
        self.handshake_dir = HANDSHAKE_DIR
        self.checkpoint_dir = CHECKPOINT_DIR
        self.reference_every_N = REFERENCE_EVERY_N
        self.drift_threshold_pct = DRIFT_THRESHOLD_PCT
        self.ref_settle_shots = REF_SETTLE_SHOTS
        self.camera_rearm_chunk = CAMERA_REARM_CHUNK
        self.idle_timeout_s = IDLE_TIMEOUT_S
        self.poll_s = POLL_S
        self.pause_poll_s = PAUSE_POLL_S

    # ------------------------------------------------------------------
    # prepare (host)
    # ------------------------------------------------------------------
    def prepare(self):
        # push DEFAULTS so init_all() below records DMA consistent with them
        self._push(DEFAULTS)

        # fail fast on a typo'd DEFAULTS key (must be a real settable variable)
        for k in DEFAULTS:
            if not (hasattr(self.MOTs, k) or hasattr(self, k)):
                raise KeyError(
                    "DEFAULTS key '{0}' is not a _Cooling or optimizer attribute".format(k))

        self.MOTs.prepare_cooling()
        self.Bragg.prepare_aoms()

        # camera: ROI_Scheme (Detection group) MUST be set to "lattice_load".
        self.Camera.camera_init(N=self.camera_rearm_chunk + 2)

        # host-side loop state
        self._best_cost = None
        self._last_seq = -1
        self._frames_since_arm = 0
        self._current_ref = 1.0
        self._ref_baseline = 1.0

    # ==================================================================
    # SHOT ENGINE — the one clean entry point
    # ==================================================================
    def _push(self, params):
        """Set every variable in `params` onto its owner: a _Cooling attribute if
        one exists by that name, else an optimizer attribute (e.g. hold_time)."""
        for k, v in params.items():
            tgt = self.MOTs if hasattr(self.MOTs, k) else self
            setattr(tgt, k, v)

    def shot(self, **overrides):
        """Run ONE shot: DEFAULTS overridden by `overrides`, return lattice counts.

        e.g.  self.shot(freq_high_i=180.0e6, rmot_sf_duration=0.03)
              self.shot(**candidate)          # M-LOOP candidate dict
        """
        self._push({**DEFAULTS, **overrides})
        self.MOTs.prepare_cooling()          # host: recompute every ramp array
        self._ensure_camera()
        counts = int(self._shot_kernel())    # kernel: re-record DMA + pulse + image
        self._frames_since_arm += 1
        return counts

    @kernel
    def _shot_kernel(self) -> TInt32:
        # lattice/dipole are already on (from init_all); rmot_pulse loads into them.
        # _dma_record re-records every trace from the self.MOTs.* arrays just
        # recomputed by prepare_cooling(). The arrays are read as attributes, NOT
        # passed as kernel args (a large list argument overflows ARTIQ's debug-info
        # column limit). This ARTIQ recompiles every kernel call regardless.
        self.MOTs._dma_record()
        self.MOTs.rmot_pulse()
        delay(self.hold_time)                          # shallow lattice: hot atoms escape
        self.MOTs.take_MOT_image(self.Camera)          # fluorescence imaging
        delay(10 * ms)
        self.core.wait_until_mu(now_mu())
        ports = self.Camera.process_image(save=False, bg_sub=True,
                                          return_ports=["lattice"])
        self.core.break_realtime()
        delay(10 * ms)
        return ports[0]

    # ------------------------------------------------------------------
    # kernel: one-time init
    # ------------------------------------------------------------------
    @kernel
    def init_all(self):
        self.core.reset()
        self.MOTs.init_cooling()                       # ttls, coils, aoms, DMA record
        self.Bragg.init_aoms(switches=BRAGG_SWITCHES)  # lattice + dipole ON
        delay(10 * ms)
        self.MOTs.take_background_image_exp(self.Camera)
        self.core.break_realtime()

    @kernel
    def _finish_k(self):
        # leave lasers on / atom source open (matches the other experiments)
        self.MOTs.AOMs_on_all()
        self.MOTs.atom_source_on()
        self.core.break_realtime()

    # ==================================================================
    # M-LOOP SERVER — thin loop around shot()
    # ==================================================================
    def run(self):
        self._init_paths()
        self.init_all()

        # establish the drift-normalization baseline (a DEFAULTS shot)
        print("[baseline] measuring reference over {0} shot(s)...".format(self.ref_settle_shots))
        vals = []
        for j in range(self.ref_settle_shots):
            c = self.shot()
            vals.append(c)
            print("[baseline] shot {0}/{1}: counts={2}".format(j + 1, self.ref_settle_shots, c))
        self._ref_baseline = max(1.0, float(np.mean(vals)))
        self._current_ref = self._ref_baseline
        print("[baseline] reference baseline = {0:.1f}".format(self._ref_baseline))
        self.set_dataset("opt.reference_baseline", self._ref_baseline,
                         broadcast=True, persist=True)
        self.set_dataset("opt.alert", 0, broadcast=True)

        # continue the iteration index across resumes (progress log is appended)
        it = _max_index(self._ckpt / "progress_{0}.jsonl".format(self.stage_name), "it", 0)
        try:
            while True:
                # let the ARTIQ dashboard pause/terminate this long-running exp
                if self.scheduler.check_pause():
                    print("TransferOptimizer: pause/terminate requested, stopping.")
                    break

                req = self._wait_for_request()
                if req is None:                    # idle timeout -> stop
                    print("TransferOptimizer: idle timeout, stopping.")
                    break
                if req.get("stop", False):
                    print("TransferOptimizer: stop requested, stopping.")
                    break

                overrides = {k: float(v) for k, v in req["params"].items()}
                print("\n[iter {0} | seq {1}] shot params: {2}".format(
                    it + 1, int(req["seq"]), self._fmt_params(overrides)))

                # Guard the candidate: an out-of-range combination (e.g. a coil
                # setpoint > MAX_CURRENT trips _build_field_ramp's assertion) or
                # any transient error must NOT crash the campaign — report a bad
                # run so M-LOOP learns the region is infeasible and moves on.
                try:
                    counts = self.shot(**overrides)
                except Exception as e:
                    print("[iter {0} | seq {1}] INVALID/failed shot: {2} -> bad".format(
                        it + 1, int(req["seq"]), e))
                    self.set_dataset("opt.last_bad", 1, broadcast=True)
                    self._write_response(int(req["seq"]), 0.0, 1.0, True)
                    continue
                it += 1
                bad = counts <= 0

                # interleaved reference + drift monitor
                if it % self.reference_every_N == 0:
                    ref = self.shot()
                    self._current_ref = 0.5 * self._current_ref + 0.5 * max(1.0, float(ref))
                    drift = (self._current_ref - self._ref_baseline) / self._ref_baseline
                    self.set_dataset("opt.reference", self._current_ref, broadcast=True)
                    self.set_dataset("opt.drift", drift, broadcast=True)
                    print("[reference] counts={0} ref_ema={1:.1f} drift={2:+.1%}".format(
                        int(ref), self._current_ref, drift))
                    if abs(drift) > self.drift_threshold_pct / 100.0:
                        bad = True
                        self._pause_until_recovered()

                cost = -float(counts) / self._current_ref
                uncer = (float(counts) ** 0.5) / self._current_ref if counts > 0 else 1.0
                print("[iter {0} | seq {1}] counts={2} ref={3:.1f} cost={4:+.4f} bad={5}".format(
                    it, int(req["seq"]), int(counts), self._current_ref, cost, bad))
                self._checkpoint(int(req["seq"]), overrides, int(counts),
                                 self._current_ref, cost, it)
                self._write_response(int(req["seq"]), cost, uncer, bad)
        finally:
            # always try to leave the lasers on / atom source open
            try:
                self._finish_k()
            except Exception as e:
                print("TransferOptimizer: finish cleanup skipped:", e)

    # ------------------------------------------------------------------
    # host helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_params(d):
        # compact one-line summary of a {name: value} dict for the ARTIQ terminal
        def f(v):
            try:
                return "{0:.6g}".format(float(v))
            except (TypeError, ValueError):
                return str(v)
        return ", ".join("{0}={1}".format(k, f(v)) for k, v in d.items())

    def _ensure_camera(self):
        # re-arm in chunks; the camera disarms itself after N frames.
        if (not self.Camera.get_is_armed()) or \
           (self._frames_since_arm >= self.camera_rearm_chunk - 1):
            if self.Camera.get_is_armed():
                self.Camera.disarm()
            self.Camera.arm(N=self.camera_rearm_chunk)
            self._frames_since_arm = 0

    def _pause_until_recovered(self):
        self.set_dataset("opt.alert", 1, broadcast=True)
        print("TransferOptimizer: DRIFT ALERT — reference beyond threshold; "
              "pausing. Touch REBASELINE to accept new baseline, or STOP to end.")
        while True:
            if self._stop_requested():
                break
            if self._rebaseline_requested():
                self._ref_baseline = self._current_ref
                self.set_dataset("opt.reference_baseline", self._ref_baseline,
                                 broadcast=True, persist=True)
                self._clear_flag("REBASELINE")
                print("TransferOptimizer: baseline accepted, resuming.")
                break
            time.sleep(self.pause_poll_s)
            ref = self.shot()
            self._current_ref = 0.5 * self._current_ref + 0.5 * max(1.0, float(ref))
            drift = (self._current_ref - self._ref_baseline) / self._ref_baseline
            self.set_dataset("opt.reference", self._current_ref, broadcast=True)
            self.set_dataset("opt.drift", drift, broadcast=True)
            if abs(drift) <= self.drift_threshold_pct / 200.0:   # recovered to 1/2
                print("TransferOptimizer: drift recovered, resuming.")
                break
        self.set_dataset("opt.alert", 0, broadcast=True)

    # ------------------------------------------------------------------
    # host helpers: file handshake + checkpointing
    # ------------------------------------------------------------------
    def _init_paths(self):
        self._hs = Path(self.handshake_dir)
        self._ckpt = Path(self.checkpoint_dir)
        self._hs.mkdir(parents=True, exist_ok=True)
        self._ckpt.mkdir(parents=True, exist_ok=True)
        self._last_seq = -1
        # start each submission from a clean handshake: drop stale request/
        # response/control files from a previous or crashed run.
        stale = (list(self._hs.glob("response_*.json"))
                 + list(self._hs.glob("request_*.json"))
                 + list(self._hs.glob(".request_*.tmp"))
                 + [self._hs / "STOP", self._hs / "REBASELINE"])
        for p in stale:
            try:
                p.unlink()
            except OSError:
                pass

    def _stop_requested(self):
        return (self._hs / "STOP").exists()

    def _rebaseline_requested(self):
        return (self._hs / "REBASELINE").exists()

    def _clear_flag(self, name):
        try:
            (self._hs / name).unlink()
        except OSError:
            pass

    def _wait_for_request(self):
        deadline = time.time() + self.idle_timeout_s
        while time.time() < deadline:
            if self._stop_requested():
                return {"stop": True}
            req = self._poll_request()
            if req is not None:
                return req
            time.sleep(self.poll_s)
        return None

    def _poll_request(self):
        # Requests are per-seq files (request_<seq>.json). Locate the newest via a
        # directory listing and open it EXACTLY ONCE, after it is fully written.
        newest_p = None
        newest_seq = self._last_seq
        for p in self._hs.glob("request_*.json"):
            try:
                s = int(p.stem.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            if s > newest_seq:
                newest_seq = s
                newest_p = p
        if newest_p is None:
            return None
        try:
            with open(newest_p) as f:
                req = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None                      # not fully written yet; retry next poll
        self._last_seq = int(req.get("seq", newest_seq))
        try:
            newest_p.unlink()                # consume it
        except OSError:
            pass
        return req

    def _write_response(self, seq, cost, uncer, bad):
        tmp = self._hs / ".response_{0}.tmp".format(seq)
        dst = self._hs / "response_{0}.json".format(seq)
        with open(tmp, "w") as f:
            json.dump({"seq": seq, "cost": float(cost),
                       "uncer": float(uncer), "bad": bool(bad)}, f)
        _atomic_replace(tmp, dst)

    def _checkpoint(self, seq, overrides, counts, ref, cost, it):
        rec = {"seq": seq, "it": it, "ts": time.time(), "params": overrides,
               "counts": int(counts), "reference": float(ref), "cost": float(cost)}
        with open(self._ckpt / "progress_{0}.jsonl".format(self.stage_name), "a") as f:
            f.write(json.dumps(rec) + "\n")

        # cost is negative; a smaller (more negative) cost is better. Save the FULL
        # param set (DEFAULTS + this shot's overrides) so the winner is reproducible.
        if self._best_cost is None or cost < self._best_cost:
            self._best_cost = cost
            full = {**DEFAULTS, **overrides}
            with open(self._ckpt / "best_params_{0}.json".format(self.stage_name), "w") as f:
                json.dump({"cost": float(cost), "counts": int(counts), "params": full},
                          f, indent=2)
            self.set_dataset("opt.best_cost", float(cost), broadcast=True, persist=True)
            self.set_dataset("opt.best_counts", int(counts), broadcast=True, persist=True)

        self.set_dataset("opt.iteration", it, broadcast=True)
        self.set_dataset("opt.last_counts", int(counts), broadcast=True)
