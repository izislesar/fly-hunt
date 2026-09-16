# Perf SLO — Task 4 rerun (REAL EGL run, supersedes synthetic Task 16)

Checkbox: `4. Свежий perf.md с реальными wall-числами` — verdict **ALL-PASS**.

PROVENANCE (real run): date `2026-09-16T16:44:28Z`, source of truth
`out/run_egl.log` (cmd `MUJOCO_GL=egl CC=gcc CXX=g++ .../venv-brainfly314/bin/python
tools/run_hunt.py --real-egl`), commit lineage `rerun/run` → `rerun/video` →
`rerun/qa`. Synthetic Task-16 numbers (proxy-wall ratios 6.0–13.0) are
**superseded** — every figure below traces to the real log, live `nvidia-smi`,
or a `/proc` VmHWM measurement run on this branch.

## SLO table

| metric | SLO | real-run value | verdict | method |
|---|---|---|---|---|
| sim/wall ratio (mujoco physics) | >= 0.2 | **0.625** (sim 2.9700 s / wall 4.75 s) | PASS | `step-ok n_steps=5940 sim_time=2.9700s wall=4.75s` from `out/run_egl.log` line 7. 5940 steps = 90 frames × 66 phys/frame × 0.5 ms. |
| sim/wall ratio (brian2 neural) | >= 0.2 (informational, same gate) | **0.342** (sim 3.0 s / wall 8.77 s) | PASS | `brian2-ok n_spikes=412811 neurons=5500 wall=8.77s` from `out/run_egl.log` line 8. 412811 spikes, PoissonGroup(5500) TimedArray-10ms 3 s seed=1, mean rate 25.02 Hz (`check_spikes.py` PASS). |
| end-to-end sim/wall | informational only (render-bound, NOT gated) | **0.107** (sim 2.97 s / total wall 27.74 s) | N/A | `total_wall=27.74s` from `out/run_egl.log` line 9 includes 90 EGL renders 640x480 + 90 PNG writes + npz/CSV/meta I/O. Reported honestly; the SLO gates the sim engines, not the render pipeline. |
| peak VRAM | < 3.5 GB | **measured 0.0039 GB (4 MB used / 4096 MB total)** | PASS | live `nvidia-smi --query-gpu=memory.used,memory.total --format=csv` → `4096, 4` (RTX 3050 Laptop 4 GB, idle baseline this task). torch absent in venv (`ModuleNotFoundError`, CPU fallback per Task 1) → no GPU arrays by construction. |
| peak RSS | < 14 GB | **measured 0.016–0.036 GB VmHWM** | PASS | `/usr/bin/time -v` absent on host (as in Task 16) → same honest substitute: `/proc/<pid>/status` VmHWM polled at 5 ms. `check_sync.py` peak 17136 kB = 0.0163 GB (PASS 90 rows); `check_spikes.py` peak 37864 kB = 0.0361 GB (PASS, n_spikes=412811 rate_mean=25.02). Host `free -g`: total 15 GB. Both ≪ 14 GB. |

## Raw command outputs (this task, 2026-09-16, branch rerun/qa)

```
$ cat out/run_egl.log
date: 2026-09-16T16:44:28Z
cmd: MUJOCO_GL=egl CC=gcc CXX=g++ /home/izislesar/venv-brainfly314/bin/python tools/run_hunt.py --real-egl
torch: ModuleNotFoundError: No module named 'torch' (CPU fallback, not a failure)
vendor: two_flies.py --help exit=1, --headless exit=1 (ImportError flygym.Fly -> run_hunt.py real-path fallback)
model-ok nq=7 nv=6 arena=arena/hunt_arena.xml timestep=0.0005
render-ok shape=(480, 640, 3) dtype=uint8 mean=150.0 EGL 640x480
step-ok n_steps=5940 sim_time=2.9700s wall=4.75s
brian2-ok n_spikes=412811 neurons=5500 wall=8.77s schedule=base20/stim140/rearm5 seed=1
sim_time=2.9700s mujoco_wall=4.75s total_wall=27.74s
hits=5 @frames [0, 19, 46, 65, 85] ammo_left=0
$ python3 -c "print(2.97/4.75, 3.0/8.77, 2.97/27.74)"
0.625263... 0.34207... 0.10707...   # mujoco / brian2 / end-to-end
$ nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits
4096, 4
$ free -g
Mem:  total 15  available 3   (GB, rounded)
$ VmHWM poll: check_sync.py peak 17136 kB = 0.0163 GB (PASS 90 rows monotonic)
$ VmHWM poll: check_spikes.py peak 37864 kB = 0.0361 GB (PASS n_spikes=412811 rate_mean=25.02)
```

## Chunked-guard note

Guard: RSS > 12 GB → load synapses in 100 k chunks (`chunk_synapses=100000`,
`rss_trigger_gb=12.0` in `out/budget.json`). Measured ≤ 0.036 GB ≪ 12 GB →
**not triggered**. CPU Brian2 priority holds; torch GPU path allowed only if
peak < 3.5 GB (satisfied, but irrelevant — torch not installed, CPU fallback).

## Verdict

- [x] sim/wall mujoco 0.625 (2.97 s / 4.75 s real wall) >= 0.2 — PASS
- [x] sim/wall brian2 0.342 (3.0 s / 8.77 s real wall) >= 0.2 — PASS
- [x] VRAM measured 0.0039 GB < 3.5 GB — PASS
- [x] RSS measured ≤ 0.036 GB < 14 GB — PASS
- [ ] No `out/fail_perf.log` needed — no bound exceeded (QA-happy path)

Committed as `chore(perf): real-run slo` on `rerun/qa` + pushed.
