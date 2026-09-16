#!/usr/bin/env python3
"""RAM/VRAM budget guard for hunting-circuit N=5500.

Estimate peak RSS + VRAM with explicit reproducible arithmetic, compare
against caps, write out/budget.json, exit 0 (PASS) / 1 (FAIL).

CPU Brian2 priority: neural weights live in host RAM; VRAM holds only the
MuJoCo EGL framebuffer. torch 2.3.1+cu121 GPU path allowed only if
peak_vram_gb < vram_cap.

Chunked guard: if projected RSS > 12 GB, synaptic load must be chunked in
100k-synapse chunks (see docs/budget.md).
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

# --- Circuit definition (plan Task 5 breakdown, N=5500 seed 0) ---
POPULATIONS = {
    "LC4": 104,
    "LPLC2": 210,
    "T2/T3-vis": 800,
    "ORN": 500,
    "PN": 300,
    "KC": 2000,
    "MBON": 96,
    "DAN": 100,
    "DN": 150,
    "SEZ-GRN": 700,
    "JO": 540,
}
N_NEURONS = sum(POPULATIONS.values())
assert N_NEURONS == 5500, N_NEURONS

MEAN_FANOUT = 40  # documented assumption: sparse fly-like fan-out avg
N_SYNAPSES = N_NEURONS * MEAN_FANOUT  # 220_000

BYTES_F64 = 8  # Brian2 default weight dtype
BYTES_F32 = 4  # optional compact dtype
NEURON_STATE_VARS = 10  # v, w-adapt, g-exc/inh, refractory, spike-queue, etc.
NEURON_STATE_BYTES = N_NEURONS * NEURON_STATE_VARS * BYTES_F64

FRAME_W, FRAME_H, FRAME_C = 640, 480, 3
N_FRAMES = 90  # 3 s @ 30 fps
FRAME_BUFFER_BYTES = FRAME_W * FRAME_H * FRAME_C * N_FRAMES
SPIKE_PNG_BYTES_EACH = 100 * 1024  # ~100 KB per 640x480 magma PNG
SPIKE_PNG_BYTES = SPIKE_PNG_BYTES_EACH * N_FRAMES
VIDEO_BYTES_CAP = 50 * 1024 * 1024  # <50 MB deliverable

BASE_OVERHEAD_GB = 1.5  # python + brian2 + mujoco + EGL runtime
SPIKE_RASTER_GB = (N_NEURONS * 300 * 1) / 1e9  # 300 bins x uint8-ish ~1.65MB
EGL_FB_BYTES = FRAME_W * FRAME_H * 4 * 2  # RGBA double-buffered

CHUNK_SYNAPSES = 100_000
CHUNK_RSS_TRIGGER_GB = 12.0


def read_host_actual():
    host = {}
    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                k, _, v = line.partition(":")
                mem[k.strip()] = int(v.split()[0])  # kB
        host["ram_total_gb"] = round(mem.get("MemTotal", 0) / 1024 / 1024, 2)
        host["ram_available_gb"] = round(mem.get("MemAvailable", 0) / 1024 / 1024, 2)
    except OSError:
        host["ram_total_gb"] = None
        host["ram_available_gb"] = None
    # nvidia-smi: record cleanly when GPU/host tool missing
    if shutil.which("nvidia-smi") is None:
        host["vram_host_missing"] = True
        host["vram_total_mb"] = None
        host["vram_used_mb"] = None
    else:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,memory.used",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode == 0 and out.stdout.strip():
                total, used = out.stdout.strip().splitlines()[0].split(",")
                host["vram_host_missing"] = False
                host["vram_total_mb"] = float(total.strip())
                host["vram_used_mb"] = float(used.strip())
            else:
                host["vram_host_missing"] = True
                host["vram_total_mb"] = None
                host["vram_used_mb"] = None
        except (subprocess.SubprocessError, ValueError, OSError):
            host["vram_host_missing"] = True
            host["vram_total_mb"] = None
            host["vram_used_mb"] = None
    return host


def estimate():
    syn_f64_gb = N_SYNAPSES * BYTES_F64 / 1e9
    syn_f32_gb = N_SYNAPSES * BYTES_F32 / 1e9
    neuron_gb = NEURON_STATE_BYTES / 1e9
    frames_gb = FRAME_BUFFER_BYTES / 1e9
    spikes_png_gb = SPIKE_PNG_BYTES / 1e9
    video_gb = VIDEO_BYTES_CAP / 1e9
    peak_rss_gb = (BASE_OVERHEAD_GB + syn_f64_gb + neuron_gb
                   + frames_gb + spikes_png_gb + video_gb + SPIKE_RASTER_GB)
    # CPU Brian2 priority -> VRAM is EGL framebuffer + headroom only
    peak_vram_gb = EGL_FB_BYTES / 1e9 + 0.15
    return {
        "n_neurons": N_NEURONS,
        "n_synapses": N_SYNAPSES,
        "mean_fanout": MEAN_FANOUT,
        "syn_f64_gb": round(syn_f64_gb, 6),
        "syn_f32_gb": round(syn_f32_gb, 6),
        "neuron_state_gb": round(neuron_gb, 6),
        "frames_gb": round(frames_gb, 6),
        "spikes_png_gb": round(spikes_png_gb, 6),
        "video_cap_gb": round(video_gb, 6),
        "base_overhead_gb": BASE_OVERHEAD_GB,
        "peak_rss_gb": round(peak_rss_gb, 4),
        "peak_vram_gb": round(peak_vram_gb, 4),
    }


def main():
    ap = argparse.ArgumentParser(description="RAM/VRAM budget guard N=5500")
    ap.add_argument("--vram-cap", type=float, required=True)
    ap.add_argument("--ram-cap", type=float, required=True)
    args = ap.parse_args()

    est = estimate()
    host = read_host_actual()
    chunked_triggered = est["peak_rss_gb"] > CHUNK_RSS_TRIGGER_GB
    ok_ram = est["peak_rss_gb"] < args.ram_cap
    ok_vram = est["peak_vram_gb"] < args.vram_cap
    verdict = "PASS" if (ok_ram and ok_vram) else "FAIL"

    out_dir = Path(__file__).resolve().parent.parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    budget = {
        "peak_rss_gb": est["peak_rss_gb"],
        "peak_vram_gb": est["peak_vram_gb"],
        "vram_cap": args.vram_cap,
        "ram_cap": args.ram_cap,
        "verdict": verdict,
        "chunked_guard": {
            "chunk_synapses": CHUNK_SYNAPSES,
            "rss_trigger_gb": CHUNK_RSS_TRIGGER_GB,
            "triggered": chunked_triggered,
            "note": ("RSS>12GB -> load synapses in 100k chunks; "
                     "CPU Brian2 priority; torch GPU only if peak<3.5GB"),
        },
        "estimate": est,
        "populations": POPULATIONS,
        "host_actual": host,
    }
    with open(out_dir / "budget.json", "w") as f:
        json.dump(budget, f, indent=2)

    fail_log = out_dir / "fail_oom.log"
    if verdict == "FAIL":
        with open(fail_log, "w") as f:
            f.write(f"FAIL fini: peak_rss_gb={est['peak_rss_gb']} "
                    f"(cap {args.ram_cap}), "
                    f"peak_vram_gb={est['peak_vram_gb']} "
                    f"(cap {args.vram_cap})\n")
            f.write("Remediation:\n")
            f.write("1. Chunked load: build/connect synapses in 100k-synapse "
                    "chunks when RSS>12GB.\n")
            f.write("2. CPU Brian2 priority: keep SNN on CPU, no GPU arrays.\n")
            f.write("3. torch 2.3.1+cu121 fallback ONLY if peak_vram_gb<3.5GB.\n")
            f.write("4. Reduce N_FRAMES or PNG size; re-run check_budget.py.\n")
        print(f"FAIL rss={est['peak_rss_gb']}GB vram={est['peak_vram_gb']}GB")
        return 1
    else:
        with open(fail_log, "w") as f:
            f.write("not-triggered: budget PASS, no OOM. "
                    "Chunked 100k guard armed for RSS>12GB.\n")
        print(f"PASS rss={est['peak_rss_gb']}GB vram={est['peak_vram_gb']}GB")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
