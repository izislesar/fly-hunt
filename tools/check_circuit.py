#!/usr/bin/env python3
"""Hunting-circuit checker (Task 5).

Validates data/hunting_circuit_6k.npz:
  1. required keys present (neuron_ids, neuron_types, edges and/or adjacency,
     weights_init, meta)
  2. N = len(neuron_ids) within [--min-neurons, --max-neurons]
  3. prints N + synapse count + RSS estimate (<8GB required)
  4. stdlib + numpy only; np.load with allow_pickle=False

Exit 0 + PASS on success; exit 1 + FAIL + out/fail_circuit.log otherwise.
On PASS, out/fail_circuit.log is (re)written as a not-triggered note.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {"neuron_ids", "neuron_types", "weights_init"}
EDGE_KEYS = ("edges", "adjacency")
RSS_CAP_GB = 8.0
OVERHEAD_GB = 1.5  # python runtime base (matches docs/budget.md convention)


def fail(log_path, reason):
    msg = f"FAIL: {reason}"
    print(msg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        f.write(msg + "\n")
    return 1


def main():
    ap = argparse.ArgumentParser(description="Check hunting circuit npz.")
    ap.add_argument("--input", required=True, help="path to circuit npz")
    ap.add_argument("--max-neurons", type=int, required=True)
    ap.add_argument("--min-neurons", type=int, required=True)
    args = ap.parse_args()

    log_path = REPO_ROOT / "out" / "fail_circuit.log"
    npz_path = Path(args.input)
    if not npz_path.exists():
        return fail(log_path, f"input not found: {npz_path}")

    try:
        data = np.load(npz_path, allow_pickle=False)
    except Exception as e:  # noqa: BLE001 - report any load failure
        return fail(log_path, f"np.load failed for {npz_path}: {e}")
    keys = set(data.files)

    missing = REQUIRED - keys
    if missing:
        return fail(log_path, f"missing keys {sorted(missing)}; have {sorted(keys)}")
    if not (EDGE_KEYS[0] in keys or EDGE_KEYS[1] in keys):
        return fail(log_path,
                    f"need one of {EDGE_KEYS}; have {sorted(keys)}")
    if "meta_json" not in keys and "meta" not in keys:
        return fail(log_path, f"missing meta/meta_json; have {sorted(keys)}")

    neuron_ids = data["neuron_ids"]
    neuron_types = data["neuron_types"]
    weights = data["weights_init"]
    edge_key = EDGE_KEYS[0] if EDGE_KEYS[0] in keys else EDGE_KEYS[1]
    edges = data[edge_key]

    n = int(len(neuron_ids))
    n_syn = int(edges.shape[0]) if edges.ndim == 2 else int(edges.size)
    rss_gb = (n * 10 * 8 + n_syn * 8 + OVERHEAD_GB * 1e9) / 1e9

    print(f"keys: {sorted(keys)}")
    print(f"N = {n} (bounds [{args.min_neurons},{args.max_neurons}])")
    print(f"synapses ({edge_key}) = {n_syn}")
    print(f"RSS_est = {rss_gb:.4f} GB (cap {RSS_CAP_GB} GB)")
    try:
        types, counts = np.unique(neuron_types, return_counts=True)
        for t, c in zip(types.tolist(), counts.tolist()):
            print(f"  {t}: {c}")
    except Exception as e:  # noqa: BLE001
        print(f"  (per-type counts unavailable: {e})")

    if "meta_json" in keys:
        try:
            meta = json.loads(str(data["meta_json"]))
            print(f"meta: seed={meta.get('seed')} target={meta.get('target')} "
                  f"N={meta.get('N')} edges_synthetic={meta.get('edges_synthetic')}")
        except Exception as e:  # noqa: BLE001
            print(f"  (meta_json parse note: {e})")

    if not (args.min_neurons <= n <= args.max_neurons):
        return fail(log_path,
                    f"N={n} outside [{args.min_neurons},{args.max_neurons}]")
    if rss_gb >= RSS_CAP_GB:
        return fail(log_path, f"RSS_est={rss_gb:.4f}GB >= cap {RSS_CAP_GB}GB")

    ok = (f"PASS: N={n} in [{args.min_neurons},{args.max_neurons}], "
          f"syn={n_syn}, RSS_est={rss_gb:.4f}GB < {RSS_CAP_GB}GB")
    print(ok)
    with open(log_path, "w") as f:
        f.write("not-triggered: check_circuit PASS, no circuit failure\n")
        f.write(ok + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
