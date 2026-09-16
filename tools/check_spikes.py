#!/usr/bin/env python3
"""Spikes npz checker — Task 13.

Validates out/spikes.npz (read-only): keys spike_times/spike_ids/bin10ms_rate,
bin10ms_rate.shape == (300,), non-empty raster, finite non-negative rates,
rate mean in [5,200]Hz. Cross-checks mean vs out/run_meta.json spike_rate_hz.mean
(tolerance ±5Hz, recorded not gated). Stdlib+numpy only.

Usage: python tools/check_spikes.py [--input out/spikes.npz]
Prints: shape=(300,) n_spikes=N rate_mean=R
Exit 0 pass / 1 fail (+ writes out/fail_spikes.log on fail).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

N_BINS = 300
BIN_MS = 10
DURATION_S = 3.0
RATE_TOL_HZ = 5.0


def fail(msg, fail_log, extra=""):
    with open(fail_log, "w") as f:
        f.write(f"FAIL: {msg}\n")
        if extra:
            f.write(extra if extra.endswith("\n") else extra + "\n")
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description="Spikes npz checker (Task 13)")
    ap.add_argument("--input", default="out/spikes.npz",
                    help="input npz path (default out/spikes.npz)")
    args = ap.parse_args()

    inp = Path(args.input)
    outdir = Path("out")
    outdir.mkdir(exist_ok=True)
    fail_log = outdir / "fail_spikes.log"

    if not inp.exists():
        fail(f"missing input {inp}", fail_log, f"path={inp} exists=False\n")

    try:
        d = np.load(str(inp), allow_pickle=False)
        _files = list(d.files)
    except Exception as e:
        with open(fail_log, "w") as f:
            f.write(f"FAIL: npz load failed: {e}\npath={inp} error={e}\n")
        print(f"FAIL: npz load failed: {e}", file=sys.stderr)
        raise SystemExit(1)

    # 1. keys present
    files = set(_files)
    for k in ("spike_times", "spike_ids", "bin10ms_rate"):
        if k not in files:
            fail(f"missing key '{k}' (have {sorted(files)})", fail_log,
                 f"keys={sorted(files)}\n")

    st = d["spike_times"]
    si = d["spike_ids"]
    rate = d["bin10ms_rate"]

    # 2. shape (300,)
    if rate.shape != (N_BINS,):
        fail(f"bin10ms_rate.shape={rate.shape} != ({N_BINS},)", fail_log,
             f"shape={rate.shape} expected=({N_BINS},)\n")

    # 3. non-empty raster, ids match
    n = int(len(st))
    if not (n == len(si) > 0):
        extra = (f"n_spike_times={len(st)} n_spike_ids={len(si)}\n"
                 f"raster_empty={n == 0}\n")
        fail("empty raster or times/ids length mismatch", fail_log, extra)

    # 4. rate sane: finite non-negative, mean in [5,200]
    if not bool(np.all(np.isfinite(rate))):
        fail("rate contains non-finite values", fail_log,
             f"finite=False min={float(np.nanmin(rate))} max={float(np.nanmax(rate))}\n")
    if not bool(np.all(rate >= 0)):
        fail("rate contains negative values", fail_log,
             f"min={float(rate.min())}\n")
    rmin, rmax, rmean = float(rate.min()), float(rate.max()), float(rate.mean())
    if not (5.0 <= rmean <= 200.0):
        fail(f"rate_mean={rmean:.2f}Hz outside [5,200]Hz", fail_log,
             f"min={rmin} max={rmax} mean={rmean}\n")

    # 5. cross-check vs run_meta.json mean (recorded, tolerance ±5Hz, not gated)
    meta_note = "run_meta.json not found"
    meta_mean = None
    mp = Path("out/run_meta.json")
    if mp.exists():
        try:
            meta = json.loads(mp.read_text())
            meta_mean = float(meta["spike_rate_hz"]["mean"])
            diff = abs(rmean - meta_mean)
            meta_note = (f"meta_mean={meta_mean}Hz npz_mean={rmean:.2f}Hz "
                         f"diff={diff:.2f}Hz tol={RATE_TOL_HZ}Hz "
                         f"{'OK' if diff <= RATE_TOL_HZ else 'MISMATCH(allowed)'}")
        except Exception as e:
            meta_note = f"run_meta parse failed: {e}"

    print(f"shape=({N_BINS},) n_spikes={n} rate_mean={rmean:.2f}")
    print(f"rate min/max/mean: {rmin:.1f}/{rmax:.1f}/{rmean:.2f} Hz")
    print(f"cross-check: {meta_note}")
    print("PASS: spikes.npz valid")


if __name__ == "__main__":
    main()
