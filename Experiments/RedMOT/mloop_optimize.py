# -*- coding: utf-8 -*-
"""
mloop_optimize.py

External M-LOOP driver for the blue->red MOT->813 lattice transfer optimization.
This is a PLAIN Python script (NOT an ARTIQ experiment) — run it from a terminal
in the ARTIQ Python environment while the `TransferOptimizer` experiment is
running in the ARTIQ dashboard/master.

It owns the optimization loop: M-LOOP proposes a candidate parameter set, this
script ships it to the ARTIQ side through a JSON file handshake, waits for the
measured (normalized) cost, and feeds it back to M-LOOP. On finish it writes the
best parameters and signals the ARTIQ experiment to stop.

Usage:
    python mloop_optimize.py --stage opt_stages/red_mot.json \
        --handshake "<FILL: same handshake dir as the experiment>" \
        --checkpoint "<FILL: same checkpoint dir as the experiment>"

Resume / warm-start (a rerun continues, never starts cold):
    * first_params is seeded from the best of a previous run — mloop_best_<stage>
      .json (this driver), best_params_<stage>.json (the ARTIQ experiment), or the
      best row of progress_<stage>.jsonl — all in the checkpoint dir.
    * If a prior M-LOOP *learner* archive is found (searching the checkpoint dir
      AND ./M-LOOP_archives/, M-LOOP's default), it is passed as `training_filename`
      so the GP starts informed by ALL prior (param, cost) data. If it can't be
      loaded, the run still starts (seeded first_params) — resume degrades to at
      least restarting from the best point.

Requires: pip install M-LOOP   (numpy is already present; matplotlib optional).
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

import numpy as np

try:
    import mloop.interfaces as mli
    import mloop.controllers as mlc
except ImportError:
    sys.exit("M-LOOP is not installed in this environment.\n"
             "Install it into your ARTIQ Python env with:  pip install M-LOOP")


def _atomic_write_json(tmp, dst, obj, retries=100, delay=0.02):
    """Write `obj` to `dst` atomically (temp file + rename), retrying the rename.

    Per-seq filenames already avoid the main Windows collision (the reader never
    holds `dst` open before it exists); this retry is belt-and-suspenders against
    a transient lock (antivirus / indexer) briefly holding the destination.
    """
    with open(tmp, "w") as f:
        json.dump(obj, f)
    last = None
    for _ in range(retries):
        try:
            os.replace(tmp, dst)
            return
        except OSError as e:          # PermissionError/sharing violation on Windows
            last = e
            time.sleep(delay)
    raise last


class ArtiqFileInterface(mli.Interface):
    """Bridges M-LOOP <-> the ARTIQ TransferOptimizer via request/response JSON.

    M-LOOP calls get_next_cost_dict(params_dict) for each candidate; we translate
    the ordered parameter array into named values, write request_<seq>.json, block
    on response_<seq>.json, and return the cost. M-LOOP MINIMIZES, and the ARTIQ
    side already returns cost = -(counts/reference), so we pass it straight through.
    """

    def __init__(self, hs_dir, param_names, response_timeout_s=3600.0, poll_s=0.05):
        super().__init__()
        self.hs = Path(hs_dir)
        self.hs.mkdir(parents=True, exist_ok=True)
        self.param_names = list(param_names)
        self.response_timeout_s = float(response_timeout_s)
        self.poll_s = float(poll_s)
        self.seq = 0

    def get_next_cost_dict(self, params_dict):
        params = np.asarray(params_dict['params'], dtype=float).ravel()
        pdict = {name: float(v) for name, v in zip(self.param_names, params)}

        seq = self.seq
        self.seq += 1
        self._write_request(seq, pdict, stop=False)
        resp = self._wait_response(seq, pdict)

        out = {'cost': float(resp['cost'])}
        if 'uncer' in resp:
            out['uncer'] = float(resp['uncer'])
        if 'bad' in resp:
            out['bad'] = bool(resp['bad'])
        return out

    # --- file handshake ---
    def _write_request(self, seq, pdict, stop):
        # per-seq filename (never reuse a name the reader may hold open)
        tmp = self.hs / ".request_{0}.tmp".format(seq)
        dst = self.hs / "request_{0}.json".format(seq)
        _atomic_write_json(tmp, dst, {"seq": seq, "params": pdict, "stop": stop})

    def _wait_response(self, seq, pdict, resend_interval=3.0):
        path = self.hs / "response_{0}.json".format(seq)
        reqpath = self.hs / "request_{0}.json".format(seq)
        deadline = time.time() + self.response_timeout_s
        last_send = time.time()
        while time.time() < deadline:
            if path.exists():
                try:
                    with open(path) as f:
                        resp = json.load(f)
                except (json.JSONDecodeError, OSError):
                    time.sleep(0.02)
                    continue
                for pp in (path, reqpath):        # consume response + any stray re-send
                    try:
                        pp.unlink()
                    except OSError:
                        pass
                return resp
            # Startup-order independence: the experiment/stub wipes the handshake
            # dir when IT starts. If we (the driver) started first, our request gets
            # deleted; if it vanishes with no response yet, re-send it. A duplicate
            # seq is ignored by the reader, so re-sending is always safe. This lets
            # you start the driver and the experiment in EITHER order.
            if (not reqpath.exists()) and (time.time() - last_send > resend_interval):
                self._write_request(seq, pdict, stop=False)
                last_send = time.time()
            time.sleep(self.poll_s)
        raise TimeoutError(
            "No response for seq {0} within {1:.0f}s. Is TransferOptimizer "
            "running and pointed at the same handshake dir? (It may also be "
            "drift-paused — check the ARTIQ log.)".format(seq, self.response_timeout_s))

    def send_stop(self):
        # touch STOP so the experiment's run loop exits cleanly
        (self.hs / "STOP").touch()


def _max_index(progress_path, key, default):
    """Largest integer `key` across a progress_*.jsonl, for continuing counters
    across resumes. Returns `default` if the file is missing/empty/unreadable."""
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


def load_stage(path):
    with open(path) as f:
        cfg = json.load(f)
    names = cfg["param_names"]
    n = len(names)
    for key in ("min_boundary", "max_boundary", "first_params"):
        if len(cfg[key]) != n:
            raise ValueError("{0} length {1} != num params {2}".format(
                key, len(cfg[key]), n))
    return cfg


def maybe_seed_first_params(cfg, checkpoint_dir):
    """Seed first_params from the best result of a previous run, so a resume
    restarts from the best known point instead of cold.

    Priority (all in checkpoint_dir):
      1. mloop_best_<stage>.json  (this driver's own output; {"best_params": ...})
      2. best_params_<stage>.json (the ARTIQ experiment's output; {"params": ...})
      3. best-cost row of progress_<stage>.jsonl (written by either side)
    Falls back to the config's first_params.
    """
    ck = Path(checkpoint_dir)
    stage = cfg["stage_name"]
    names = cfg["param_names"]

    # 1 & 2: a saved best-params file (accept either schema)
    for fname in ("mloop_best_{0}.json".format(stage),
                  "best_params_{0}.json".format(stage)):
        p = ck / fname
        if not p.exists():
            continue
        try:
            data = json.load(open(p))
            d = data.get("best_params") or data.get("params") or {}
            fp = [float(d[n]) for n in names]
            print("Seeding first_params from", p)
            return fp
        except (KeyError, ValueError, OSError) as e:
            print("Could not seed from", p, "->", e)

    # 3: best-cost row of the progress log
    prog = ck / "progress_{0}.jsonl".format(stage)
    if prog.exists():
        try:
            best = None
            with open(prog) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    r = json.loads(line)
                    if best is None or r["cost"] < best["cost"]:
                        best = r
            if best is not None and all(n in best.get("params", {}) for n in names):
                fp = [float(best["params"][n]) for n in names]
                print("Seeding first_params from best row of {0} (cost {1:.4g})"
                      .format(prog, best["cost"]))
                return fp
        except (KeyError, ValueError, OSError) as e:
            print("Could not seed from", prog, "->", e)

    print("No prior results found; starting from config first_params.")
    return cfg["first_params"]


def find_training_archive(checkpoint_dir, stage_name):
    """Newest M-LOOP LEARNER archive for this stage, for GP warm-start.

    M-LOOP writes archives to ./M-LOOP_archives/ (its default) unless it honors
    archive_dir, so search the likely locations rather than only checkpoint_dir.
    Learner archives hold the (params, cost) training data; controller archives
    don't reliably load as training data, so we only return learner archives.
    """
    roots = [Path(checkpoint_dir),
             Path(checkpoint_dir) / "M-LOOP_archives",
             Path("M-LOOP_archives"),
             Path(".")]
    cands = []
    for root in roots:
        if root.exists():
            cands += list(root.glob("*learner_archive*{0}*".format(stage_name)))
    cands = list(dict.fromkeys(cands))                 # dedupe, keep order
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime)
    return str(cands[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, help="path to opt_stages/<stage>.json")
    ap.add_argument("--handshake", default=r"<FILL: handshake dir>")
    ap.add_argument("--checkpoint", default=r"<FILL: checkpoint dir>")
    ap.add_argument("--no-stop", action="store_true",
                    help="do not signal the experiment to stop when finished")
    ap.add_argument("--plots", default=False, action="store_true",
                    help="show M-LOOP visualizations at the end (blocks until you "
                         "close the windows). Off by default so the run never hangs.")
    args = ap.parse_args()

    # Resolve to absolute paths BEFORE we chdir below (so relative --handshake /
    # --checkpoint keep working). Load the stage file before chdir too.
    args.handshake = os.path.abspath(args.handshake)
    args.checkpoint = os.path.abspath(args.checkpoint)

    cfg = load_stage(args.stage)
    stage = cfg["stage_name"]
    Path(args.checkpoint).mkdir(parents=True, exist_ok=True)
    # Run from the checkpoint dir so M-LOOP's ./M-LOOP_archives/ is created THERE
    # deterministically (M-LOOP 3.3.4 ignores archive_dir). This makes warm-start
    # on a later run independent of where you launch the driver from.
    os.chdir(args.checkpoint)

    # start clean: remove stale request/response/control files from a previous or
    # crashed run so seq 0 isn't answered by an old response (checkpoints kept).
    hsdir = Path(args.handshake)
    hsdir.mkdir(parents=True, exist_ok=True)
    for p in (list(hsdir.glob("response_*.json"))
              + list(hsdir.glob("request_*.json"))
              + list(hsdir.glob(".request_*.tmp"))
              + [hsdir / "STOP", hsdir / "REBASELINE"]):
        try:
            p.unlink()
        except OSError:
            pass

    interface = ArtiqFileInterface(args.handshake, cfg["param_names"],
                                   response_timeout_s=cfg.get("response_timeout_s", 3600.0))
    # continue the handshake seq across resumes so request/response ids and the
    # progress-log 'seq' keep counting up instead of restarting at 0
    interface.seq = _max_index(Path(args.checkpoint) / "progress_{0}.jsonl".format(stage),
                               "seq", -1) + 1
    if interface.seq:
        print("Continuing from seq", interface.seq)

    first_params = maybe_seed_first_params(cfg, args.checkpoint)
    training = find_training_archive(args.checkpoint, stage)
    if training:
        print("Warm-starting learner from", training)

    controller_kwargs = dict(
        max_num_runs=int(cfg.get("max_num_runs", 100)),
        num_params=len(cfg["param_names"]),
        min_boundary=cfg["min_boundary"],
        max_boundary=cfg["max_boundary"],
        first_params=first_params,
        cost_has_noise=bool(cfg.get("cost_has_noise", True)),
        # keep all archives with this stage's name in the shared checkpoint dir so
        # a later run can warm-start (training_filename below)
        archive_dir=args.checkpoint,
        controller_archive_filename="controller_archive_{0}".format(stage),
        learner_archive_filename="learner_archive_{0}".format(stage),
        controller_archive_file_type="txt",
        learner_archive_file_type="txt",
    )
    if "target_cost" in cfg:
        controller_kwargs["target_cost"] = float(cfg["target_cost"])
    if training:
        controller_kwargs["training_filename"] = training

    ctype = cfg.get("controller_type", "gaussian_process")

    def _make(kwargs):
        return mlc.create_controller(interface, controller_type=ctype, **kwargs)

    try:
        controller = _make(controller_kwargs)
    except TypeError as e:
        # M-LOOP versions differ on the archive-naming kwargs; retry with only
        # the essential, universally-supported ones (still functional, just no
        # custom archive filenames).
        print("create_controller rejected a kwarg ({0}); retrying minimal.".format(e))
        keep = ("max_num_runs", "num_params", "min_boundary", "max_boundary",
                "first_params", "cost_has_noise", "target_cost", "training_filename")
        controller_kwargs = {k: controller_kwargs[k] for k in keep if k in controller_kwargs}
        try:
            controller = _make(controller_kwargs)
        except Exception as e2:
            # most likely the training archive is incompatible -> drop it and go
            if "training_filename" not in controller_kwargs:
                raise
            print("retrying without training_filename ({0})".format(e2))
            controller_kwargs.pop("training_filename", None)
            controller = _make(controller_kwargs)
    except Exception as e:
        # a bad/incompatible training archive must not prevent starting fresh
        if "training_filename" not in controller_kwargs:
            raise
        print("create_controller failed ({0}); retrying without training_filename."
              .format(e))
        controller_kwargs.pop("training_filename", None)
        controller = _make(controller_kwargs)

    print("Starting M-LOOP stage '{0}' ({1} params, {2} runs max)".format(
        stage, len(cfg["param_names"]), controller_kwargs["max_num_runs"]))
    controller.optimize()

    # write best params (names) for this stage
    best = {name: float(v) for name, v in
            zip(cfg["param_names"], np.asarray(controller.best_params).ravel())}
    out = Path(args.checkpoint) / "mloop_best_{0}.json".format(stage)
    with open(out, "w") as f:
        json.dump({"stage": stage, "best_cost": float(controller.best_cost),
                   "best_params": best}, f, indent=2)
    print("Best cost {0:.4g}; wrote {1}".format(float(controller.best_cost), out))

    # optional M-LOOP visualizations (correlations / landscape). Off by default:
    # show_all_default_visualizations() calls plt.show(), which BLOCKS until you
    # close the windows and would otherwise stall sending STOP. Pass --plots to see
    # them; the archives are saved either way so you can plot later.
    if args.plots:
        print('showing')
        try:
            import mloop.visualizations as mlv
            mlv.show_all_default_visualizations(controller)
        except Exception as e:  # matplotlib missing or headless
            print("Visualizations skipped:", e)

    if not args.no_stop:
        interface.send_stop()
        print("Signalled TransferOptimizer to stop.")


if __name__ == "__main__":
    main()
