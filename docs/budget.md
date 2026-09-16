# RAM/VRAM budget — hunting-circuit N=5500

Caps: **3.5 GB VRAM** / **14 GB RAM** (4 GB host VRAM minus headroom).
Engine priority: **CPU Brian2**; torch 2.3.1+cu121 GPU only if peak VRAM < 3.5 GB.

## Circuit

N=5500 seed 0: LC4 104 + LPLC2 210 + T2/T3-vis 800 + ORN 500 + PN 300 +
KC 2000 + MBON 96 + DAN 100 + DN 150 + SEZ-GRN 700 + JO 540 = 5500.

## Estimate table

| Component | Formula | Bytes / GB |
|---|---|---|
| Synapses count | 5500 neurons × mean fan-out 40 | 220 000 synapses |
| Weights float64 (Brian2 default) | 220 000 × 8 B | 1.76 MB (0.00176 GB) |
| Weights float32 (compact option) | 220 000 × 4 B | 0.88 MB (0.00088 GB) |
| Neuron state | 5500 × 10 vars × 8 B | 0.44 MB (0.00044 GB) |
| MuJoCo frame buffer | 640×480×3 B × 90 frames | 82.94 MB (0.0829 GB) |
| Spike PNGs (magma) | 90 × ~100 KB | 9.0 MB (0.009 GB) |
| Spike raster (300 bins of 10 ms) | 5500 × 300 × 1 B | ~1.65 MB (0.00165 GB) |
| Video deliverable | cap | <50 MB (0.05 GB) |
| Runtime base (python+brian2+mujoco+EGL) | measured allowance | 1.5 GB |
| **Peak RSS** | sum above (float64 path) | **~1.65 GB < 14 GB ✓** |
| **Peak VRAM** (EGL framebuffer only: 640×480×4 B×2 + 0.15 headroom) | CPU Brian2 priority, no GPU arrays | **~0.152 GB < 3.5 GB ✓** |

Reproduce: `python tools/check_budget.py --vram-cap 3.5 --ram-cap 14`
→ writes `out/budget.json`, prints PASS/FAIL.

## Chunked guard

**If projected RSS > 12 GB, load/connect synapses in chunks of 100k
synapses per chunk** (`chunk_synapses=100_000`, `rss_trigger_gb=12.0` in
`out/budget.json:chunked_guard`). Same threshold is encoded in
`tools/check_budget.py` logic. On FAIL the checker writes
`out/fail_oom.log` with remediation (chunked 100k, CPU priority, torch
fallback only if peak < 3.5 GB). On PASS `out/fail_oom.log` holds a
not-triggered note so failure-gate Task 17 can reference it.
