# -*- coding: utf-8 -*-
"""
mloop_stub_server.py

Hardware-free stand-in for the ARTIQ `TransferOptimizer` side of the handshake.
It speaks the EXACT same request/response JSON protocol but, instead of running a
real shot, returns a synthetic cost = a known analytic function of the params
(a noisy Gaussian bump whose peak sits at the midpoint of each parameter's
bounds). Use it to validate the M-LOOP driver, the file handshake, and the
checkpoint/resume flow WITHOUT any hardware.

Run it and mloop_optimize.py in two terminals pointed at the same --handshake dir,
in EITHER order (the driver re-sends its request if the server starts later).
M-LOOP should converge toward the bounds-midpoint of every parameter (cost -> ~-1).

Usage:
    python mloop_stub_server.py --stage opt_stages/red_mot.json \
        --handshake ./_stub_handshake --checkpoint ./_stub_checkpoint
"""

import os
import json
import time
import argparse
from pathlib import Path

import numpy as np


def _atomic_replace(tmp, dst, retries=100, delay=0.02):
    """os.replace() with retry (Windows can deny the rename if the reader has the
    destination briefly open); retry until it succeeds."""
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
    """Largest integer `key` across a progress_*.jsonl (to continue counters on
    resume). Returns `default` if missing/empty/unreadable."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--handshake", default="./_stub_handshake")
    ap.add_argument("--checkpoint", default="./_stub_checkpoint")
    ap.add_argument("--noise", type=float, default=0.02, help="fractional cost noise")
    ap.add_argument("--idle-timeout", type=float, default=300.0)
    args = ap.parse_args()

    with open(args.stage) as f:
        cfg = json.load(f)
    names = cfg["param_names"]
    lo = np.asarray(cfg["min_boundary"], dtype=float)
    hi = np.asarray(cfg["max_boundary"], dtype=float)
    opt = 0.5 * (lo + hi)              # synthetic optimum = midpoint
    width = 0.30 * (hi - lo)           # bump width
    A = 10000.0                        # peak "counts"

    hs = Path(args.handshake); hs.mkdir(parents=True, exist_ok=True)
    ck = Path(args.checkpoint); ck.mkdir(parents=True, exist_ok=True)
    # start clean: drop stale request/response/control files (e.g. a STOP left by
    # the previous stage's driver) so the stub doesn't immediately exit or replay
    # old requests. Mirrors the cleanup in TransferOptimizer / mloop_optimize.
    for p in (list(hs.glob("request_*.json")) + list(hs.glob("response_*.json"))
              + list(hs.glob(".request_*.tmp"))
              + [hs / "STOP", hs / "REBASELINE"]):
        try:
            p.unlink()
        except OSError:
            pass
    stage = cfg["stage_name"]
    prog = ck / "progress_{0}.jsonl".format(stage)

    print("stub server up. optimum (bounds midpoint):")
    for n, o in zip(names, opt):
        print("   {0} = {1:g}".format(n, o))

    last_seq = -1
    deadline = time.time() + args.idle_timeout
    it = _max_index(prog, "it", 0)     # continue the iteration index across resumes
    while time.time() < deadline:
        if (hs / "STOP").exists():
            print("STOP seen, exiting.")
            break
        # find the newest per-seq request file (dir stat only; open once, after
        # it is fully written -> no Windows rename/open collision)
        newest_p = None
        newest_seq = last_seq
        for p in hs.glob("request_*.json"):
            try:
                s = int(p.stem.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            if s > newest_seq:
                newest_seq = s
                newest_p = p
        if newest_p is None:
            time.sleep(0.03)
            continue
        try:
            with open(newest_p) as f:
                req = json.load(f)
        except (json.JSONDecodeError, OSError):
            time.sleep(0.02)
            continue
        if req.get("stop", False):
            break
        seq = int(req.get("seq", newest_seq))
        last_seq = seq
        try:
            newest_p.unlink()
        except OSError:
            pass

        p = np.array([float(req["params"].get(n, opt[i])) for i, n in enumerate(names)])
        z = ((p - opt) / width) ** 2
        counts = A * float(np.exp(-0.5 * np.sum(z)))
        counts *= (1.0 + args.noise * np.random.randn())     # multiplicative noise
        counts = max(0.0, counts)
        ref = A
        cost = -counts / ref
        uncer = (counts ** 0.5) / ref if counts > 0 else 1.0

        # checkpoint (mirrors the real server so resume tests exercise the same file)
        it += 1
        with open(prog, "a") as f:
            f.write(json.dumps({"seq": seq, "it": it, "ts": time.time(),
                                "params": req["params"], "counts": int(counts),
                                "reference": ref, "cost": cost}) + "\n")

        tmp = hs / ".response_{0}.tmp".format(seq)
        dst = hs / "response_{0}.json".format(seq)
        with open(tmp, "w") as f:
            json.dump({"seq": seq, "cost": cost, "uncer": uncer, "bad": False}, f)
        _atomic_replace(tmp, dst)

        deadline = time.time() + args.idle_timeout   # reset idle timer
        print("seq {0:4d}  counts {1:8.1f}  cost {2:+.4f}".format(seq, counts, cost))

    print("stub server done ({0} evaluations).".format(it))


if __name__ == "__main__":
    main()
