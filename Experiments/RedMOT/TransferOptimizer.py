# -*- coding: utf-8 -*-
"""
TransferOptimizer.py

ARTIQ "optimizer server" for closed-loop optimization of the
blue MOT -> red MOT -> 813 lattice transfer.

Role in the system
-------------------
This experiment does NOT contain an optimizer. It is a long-lived ARTIQ
experiment that:
  1. keeps the kernel warm and the DMA traces resident (no per-iteration
     resubmit/recompile),
  2. receives a candidate parameter set from an external M-LOOP process through
     a small JSON file handshake,
  3. applies those parameters (re-recording the affected DMA traces from
     *arguments* so the kernel does not recompile),
  4. runs one `rmot_pulse` shot, holds, images, and counts the atoms retained in
     the (fixed, already-on) shallow 813 lattice ROI,
  5. interleaves a fixed "reference" shot to normalize slow drift, auto-pausing
     if the reference drifts too far,
  6. checkpoints every shot so a restabilize-and-restart warms up from prior data,
  7. writes the (normalized) cost back for M-LOOP.

The optimizer loop is owned by the external process; see `mloop_optimize.py`.

Handshake protocol (files in `handshake_dir`)
--------------------------------------------
  request_<seq>.json     {"seq": int, "params": {name: value}, "stop": bool}
  response_<seq>.json    {"seq": int, "cost": float, "uncer": float, "bad": bool}
  STOP                   (touch to end the run cleanly)
  REBASELINE             (touch to accept a drifted baseline and resume)
Both requests and responses use PER-SEQ filenames (never a single shared name):
the reader finds the newest via a directory listing and opens each file exactly
once, after it is fully written, so the writer never renames over a file the
reader holds open — this avoids the Windows rename/open ("Access is denied")
collision that a single reused name causes. Writes are temp-file + os.replace.

Cost convention: M-LOOP MINIMIZES, so cost = -(candidate_counts / reference).

NOTE: values marked <FILL ...> (paths, ROI, hold time, camera chunk, bounds) are
placeholders for you to set. See OPTIMIZER_TESTS.md.
"""

import os
import json
import time
from pathlib import Path

import numpy as np

from artiq.experiment import (  # pyright: ignore[reportMissingImports]
    EnvExperiment, kernel, delay, ms, now_mu, at_mu,
    NumberValue, StringValue, TInt32,
)

# Reuse the MOT-side constants so the inlined blue-capture re-record matches the
# original recording exactly. to_bb_time / blue_transfer_time are now tunable
# (passed as arguments); only the fixed sf-down duration is imported here.
from CoolingClass import (  # pyright: ignore[reportMissingImports]
    _Cooling, BFIELD_DAC, SF_DOWN_TIME,
)
from CameraClass import _Camera  # pyright: ignore[reportMissingImports]
from BraggClass import _Bragg    # pyright: ignore[reportMissingImports]


def _atomic_replace(tmp, dst, retries=100, delay=0.02):
    """os.replace() with retry. On Windows the rename raises PermissionError/
    OSError if another process (the M-LOOP driver polling response files) has
    `dst` open at that instant; retry until its short-lived handle is released
    (up to retries*delay seconds)."""
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
    # parameter registry: optimizer-name -> _Cooling attribute
    # ------------------------------------------------------------------
    # Every name M-LOOP might optimize must appear here so apply() knows how to
    # set it. Units are SI and match the _Cooling attributes: frequencies in Hz,
    # currents/fields in A (DAC volts), durations in seconds. Categorical knobs
    # (shape_freq / shape_atten) are intentionally excluded — M-LOOP optimizes
    # continuous parameters only; leave those on their GUI value.
    PARAM_ATTR = {
        # --- compression sweep (DMA-baked: re-precompute + re-record) ---
        "freq_high":           "freq_high",
        "freq_low_i":          "freq_low_i",
        "freq_low_f":          "freq_low_f",
        "ramp_tau":            "ramp_tau",
        "rmot_scan_frequency": "rmot_scan_frequency",
        "atten_ramp_i":        "atten_ramp_i",
        "atten_ramp_f":        "atten_ramp_f",
        "rmot_bb_current":     "rmot_bb_current",
        "rmot_sf_current":     "rmot_sf_current",
        "rmot_ramp_duration":  "rmot_ramp_duration",
        # --- field ramps + blue->red capture handoff (DMA-baked) ---
        "bmot_current":        "bmot_current",
        "bmot_ramp_duration":  "bmot_ramp_duration",
        "binc":                "binc",                # extra capture coil boost
        "blue_transfer_time":  "blue_transfer_time",  # blue capture ramp duration
        "to_bb_time":          "to_bb_time",          # ramp-to-broadband duration
        "blue_att_i":          "blue_att_i",          # blue capture atten start (dB)
        "blue_att_f":          "blue_att_f",          # blue capture atten end (dB)
        # --- cheap: forwarded to rmot_pulse as kernel args (see NO_SETATTR) ---
        "rmot_bb_duration":    "rmot_bb_duration",    # -> bb_dur
        "rmot_sf_duration":    "rmot_sf_duration",    # -> sf_dur
        "atten_3D":            "atten_3D",            # -> att_blue (3D blue power)
        "atten_3D_red":        "atten_3D_red",        # -> att_red  (3D red power)
    }

    # Names NOT written onto self.MOTs — instead forwarded to rmot_pulse as
    # kernel *arguments* (writing them would recompile rmot_pulse each iteration).
    # bmot_load_duration is intentionally absent: it is held fixed (see build /
    # run) at bmot_load_duration_fixed, not optimized.
    NO_SETATTR = ("rmot_bb_duration", "rmot_sf_duration", "atten_3D", "atten_3D_red")

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------
    def build(self):
        self.setattr_device("core")
        self.setattr_device("core_dma")
        self.setattr_device("scheduler")

        # composed hardware controllers (reused unchanged)
        self.MOTs = _Cooling(self)
        self.Bragg = _Bragg(self)     # only to init the lattice/dipole AOMs on
        self.Camera = _Camera(self)

        g = "Optimizer"
        self.setattr_argument("stage_name", StringValue("stage1"), g)
        self.setattr_argument("handshake_dir",
                              StringValue(r"C:\Users\sr\Documents\Artiq\ARTIQ_opt"), g)
        self.setattr_argument("checkpoint_dir",
                              StringValue(r"C:\Users\sr\Documents\Artiq\ARTIQ_opt"), g)
        self.setattr_argument("reference_every_N",
                              NumberValue(5, min=1, max=1000, ndecimals=0, step=1), g)
        self.setattr_argument("drift_threshold_pct",
                              NumberValue(15.0, min=1.0, max=100.0, ndecimals=1), g)
        self.setattr_argument("ref_settle_shots",
                              NumberValue(3, min=1, max=50, ndecimals=0, step=1), g)
        self.setattr_argument("hold_time",
                              NumberValue(30e-3, min=0.0, max=2.0, scale=1e-3, unit="ms"), g)
        # bmot_load_duration is held FIXED (not optimized) at this value.
        self.setattr_argument("bmot_load_duration_fixed",
                              NumberValue(0.5, min=0.01, max=9.0, scale=1e-3, unit="ms"), g)
        self.setattr_argument("camera_rearm_chunk",
                              NumberValue(50, min=2, max=5000, ndecimals=0, step=1), g)
        self.setattr_argument("idle_timeout_s",
                              NumberValue(600.0, min=10.0, max=1e6, unit="s"), g)
        self.setattr_argument("poll_s",
                              NumberValue(0.05, min=0.005, max=1.0, ndecimals=3), g)
        self.setattr_argument("pause_poll_s",
                              NumberValue(2.0, min=0.1, max=60.0, ndecimals=1), g)

    # ------------------------------------------------------------------
    # prepare (host)
    # ------------------------------------------------------------------
    def prepare(self):
        self.MOTs.prepare_cooling()
        self.Bragg.prepare_aoms()

        # coerce the integer-valued GUI floats
        self.reference_every_N = int(self.reference_every_N)
        self.ref_settle_shots = int(self.ref_settle_shots)
        self.camera_rearm_chunk = int(self.camera_rearm_chunk)


        # camera: ROI_Scheme (Detection group) MUST be set to "lattice_load".
        # Arm in chunks; the host loop re-arms as needed.
        self.Camera.camera_init(N=self.camera_rearm_chunk + 2)

        # host-side loop state (created here so kernel type-inference is stable)
        self._blue_down_mu = [np.int32(0)]
        self._best_cost = None
        self._last_seq = -1
        self._frames_since_arm = 0
        self._current_ref = 1.0
        self._ref_baseline = 1.0

    # ------------------------------------------------------------------
    # kernel: one-time init
    # ------------------------------------------------------------------
    @kernel
    def init_all(self):
        self.core.reset()
        self.MOTs.init_cooling()                      # ttls, coils, aoms, DMA record
        self.Bragg.init_aoms()  # lattice + dipole ON
        delay(10 * ms)
        self.MOTs.take_background_image_exp(self.Camera)
        self.core.break_realtime()

    # ------------------------------------------------------------------
    # kernel: re-record every DMA trace this pulse plays back, from ARGUMENTS.
    # Reading these from self.* would bake them in as compile-time constants and
    # force a recompile every iteration; passing them in keeps the loop
    # compile-once. record_rmot_ramp_arg / _record_field_ramp are _Cooling
    # methods (the latter already argument-fed); the blue-capture trace is
    # inlined here because it also ramps the blue AOM attenuation.
    # ------------------------------------------------------------------
    @kernel
    def _rerecord_dma(self, upper, lower, step_up, step_dn, atten_mu, field_mu,
                      rmot_n, rmot_dt_mu,
                      blue_up, blue_down, to_bb, sf_down, blue_load, blue_att,
                      bmot_ramp_dur, to_bb_time, blue_transfer_time):
        # compression sweep (attenuation VVA + coil field + DRG frequency sweep)
        self.MOTs.record_rmot_ramp_arg(upper, lower, step_up, step_dn,
                                       atten_mu, field_mu, rmot_n, rmot_dt_mu)
        # single-channel coil-field ramps
        self.MOTs._record_field_ramp("field_blue_up",   blue_up,   bmot_ramp_dur)
        self.MOTs._record_field_ramp("field_blue_down", blue_down, bmot_ramp_dur)
        self.MOTs._record_field_ramp("field_to_bb",     to_bb,     to_bb_time)
        self.MOTs._record_field_ramp("field_sf_down",   sf_down,   SF_DOWN_TIME)
        # blue capture ramp: coil current + blue AOM attenuation in one trace
        n = len(blue_load)
        dt_mu = self.core.seconds_to_mu(blue_transfer_time / n)
        with self.MOTs.core_dma.record("field_blue_load"):
            t = now_mu()
            for i in range(n):
                at_mu(t)
                self.MOTs.zotino0.write_dac_mu(BFIELD_DAC, blue_load[i])
                self.MOTs.zotino0.load()
                self.MOTs.aom_3D_blue.set_att(blue_att[i])
                t += dt_mu
            at_mu(t)
        self.core.break_realtime()

    # ------------------------------------------------------------------
    # kernel: one measurement shot -> lattice-ROI counts
    # All per-shot tunables arrive as arguments -> no recompile between shots.
    # ------------------------------------------------------------------
    @kernel
    def do_shot(self, bb_dur, sf_dur, att_blue, att_red, hold_time) -> TInt32:
        # lattice/dipole are already on (from init); rmot_pulse loads into them.
        self.MOTs.rmot_pulse(bb_dur=bb_dur, sf_dur=sf_dur,
                             att_blue=att_blue, att_red=att_red)
        delay(hold_time)                      # shallow lattice: hot atoms escape
        self.MOTs.take_MOT_image(self.Camera)  # existing fluorescence imaging
        delay(10 * ms)
        self.core.wait_until_mu(now_mu())
        ports = self.Camera.process_image(save=False, bg_sub=True,
                                          return_ports=["lattice"])
        self.core.break_realtime()
        delay(10 * ms)
        return ports[0]

    @kernel
    def _finish_k(self):
        # leave lasers on / atom source open (matches the other experiments)
        self.MOTs.AOMs_on_all()
        self.MOTs.atom_source_on()
        self.core.break_realtime()

    # ==================================================================
    # HOST control loop
    # ==================================================================
    def run(self):
        self._init_paths()
        # hold bmot_load_duration fixed (not optimized). Set once, before any
        # kernel compiles, so rmot_pulse bakes in this constant and never
        # recompiles for it.
        self.MOTs.bmot_load_duration = float(self.bmot_load_duration_fixed)
        self.init_all()

        # baseline / reference parameter set = current GUI values
        self._base_params = self._snapshot_base()
        self._current_full = dict(self._base_params)

        # establish the drift-normalization baseline
        print("[baseline] measuring reference over {0} shot(s)...".format(self.ref_settle_shots))
        vals = []
        for j in range(self.ref_settle_shots):
            c = self._shoot(self._base_params)
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

                # merge active params onto the running full set, then measure
                for k, v in req["params"].items():
                    self._current_full[k] = float(v)
                print("\n[iter {0} | seq {1}] shot params: {2}".format(
                    it + 1, int(req["seq"]), self._fmt_params(req["params"])))

                # Guard the candidate: an out-of-range combination (e.g. a coil
                # setpoint > MAX_CURRENT trips _build_field_ramp's assertion) or
                # any transient error must NOT crash the campaign — report a bad
                # run so M-LOOP learns the region is infeasible and moves on.
                try:
                    counts = self._shoot(self._current_full)
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
                    ref = self._shoot(self._base_params)
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
                self._checkpoint(int(req["seq"]), req["params"], int(counts),
                                 self._current_ref, cost, it)
                self._write_response(int(req["seq"]), cost, uncer, bad)
        finally:
            # always try to leave the lasers on / atom source open
            try:
                self._finish_k()
            except Exception as e:
                print("TransferOptimizer: finish cleanup skipped:", e)

    # ------------------------------------------------------------------
    # host helpers: apply + shoot
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_params(d):
        # compact one-line summary of a {name: value} dict for the ARTIQ terminal
        return ", ".join("{0}={1:.6g}".format(k, float(v)) for k, v in d.items())

    def _shoot(self, full):
        """Apply `full`, re-record DMA, run one shot, return lattice counts."""
        bb, sf, ab, ar = self._apply(full)
        self._ensure_camera()
        counts = int(self.do_shot(bb, sf, ab, ar, float(self.hold_time)))
        self._frames_since_arm += 1
        return counts

    def _apply(self, full):
        """Host: set attributes + recompute ramps; kernel: re-record DMA.
        Returns (bb_dur, sf_dur, att_blue, att_red) to pass to do_shot."""
        for name, val in full.items():
            if name in self.NO_SETATTR:
                continue                      # forwarded as kernel arg, not attr
            setattr(self.MOTs, self.PARAM_ATTR[name], float(val))

        # host numpy precompute (fills self.MOTs.* ramp arrays)
        self.MOTs._prepare_rmot_ramp()
        self.MOTs._prepare_coils()
        m = self.MOTs
        self._blue_down_mu = [m.blue_up_mu[len(m.blue_up_mu) - 1 - i]
                              for i in range(len(m.blue_up_mu))]

        # kernel re-record (all arrays + tunable durations passed as arguments)
        self._rerecord_dma(m.upper, m.lower, m.step_up, m.step_dn,
                           m.atten_dac_mu, m.field_dac_mu, m.rmot_n, m.rmot_dt_mu,
                           m.blue_up_mu, self._blue_down_mu, m.to_bb_mu, m.sf_down_mu,
                           m.blue_load_mu, m.blue_att_db, m.bmot_ramp_duration,
                           m.to_bb_time, m.blue_transfer_time)

        return (float(full["rmot_bb_duration"]), float(full["rmot_sf_duration"]),
                float(full["atten_3D"]), float(full["atten_3D_red"]))

    def _snapshot_base(self):
        return {name: float(getattr(self.MOTs, attr))
                for name, attr in self.PARAM_ATTR.items()}

    def _ensure_camera(self):
        # re-arm in chunks; the camera disarms itself after N frames.
        if (not self.Camera.get_is_armed()) or \
           (self._frames_since_arm >= self.camera_rearm_chunk - 1):
            if self.Camera.get_is_armed():
                self.Camera.disarm()
            self.Camera.arm(N=self.camera_rearm_chunk)
            self._frames_since_arm = 0

    # ------------------------------------------------------------------
    # host helpers: drift pause
    # ------------------------------------------------------------------
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
            ref = self._shoot(self._base_params)
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
        # response/control files from a previous or crashed run so we don't act
        # on an old request or the driver read an old response. (Checkpoints in
        # checkpoint_dir are preserved for warm-start.)
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
        # Requests are per-seq files (request_<seq>.json). We locate the newest via
        # a directory listing (stat only) and open it EXACTLY ONCE, after it is
        # fully written — the writer never renames over a file we hold open, so
        # there is no Windows rename/open collision (unlike a single shared name).
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
        # retry the rename: on Windows os.replace fails if the driver has the
        # destination open at that instant (see _atomic_replace docstring).
        _atomic_replace(tmp, dst)

    def _checkpoint(self, seq, params, counts, ref, cost, it):
        rec = {"seq": seq, "it": it, "ts": time.time(), "params": params,
               "counts": int(counts), "reference": float(ref), "cost": float(cost)}
        with open(self._ckpt / "progress_{0}.jsonl".format(self.stage_name), "a") as f:
            f.write(json.dumps(rec) + "\n")

        # cost is negative; a smaller (more negative) cost is better
        if self._best_cost is None or cost < self._best_cost:
            self._best_cost = cost
            with open(self._ckpt / "best_params_{0}.json".format(self.stage_name), "w") as f:
                json.dump({"cost": float(cost), "counts": int(counts),
                           "params": dict(self._current_full)}, f, indent=2)
            self.set_dataset("opt.best_cost", float(cost), broadcast=True, persist=True)
            self.set_dataset("opt.best_counts", int(counts), broadcast=True, persist=True)

        self.set_dataset("opt.iteration", it, broadcast=True)
        self.set_dataset("opt.last_counts", int(counts), broadcast=True)
