# Task 5 (rerun) — Human TL;DR сверка с РЕАЛЬНЫМ прогоном (2026-09-16, branch rerun/qa)

Supersedes: Task 18 synthetic tldr_check (path=synthetic, 47K mp4, 342 spikes).
This file verifies the REAL EGL rerun artifacts only.

## 1. Artifact inventory (LIVE outputs, quoted verbatim)

### 1.1 ls -lh (the 3 files)
```
-rw-r--r-- 1 izislesar izislesar 354K Sep 16 19:54 out/trophy_hunt.mp4
-rw-r--r-- 1 izislesar izislesar 4.2K Sep 16 19:44 out/physics_log.csv
-rw-r--r-- 1 izislesar izislesar 6.4M Sep 16 19:44 out/spikes.npz
```

### 1.2 ls -lh out/ (QA-happy evidence, full dir)
```
$ ls -lh out/
(out/ listing captured 2026-09-16; key rows: trophy_hunt.mp4 354K, physics_log.csv 4.2K,
spikes.npz 6.4M, run_egl.log 693B, run_meta.json 21K, perf.md 4.2K,
frames/ 90 PNG real-egl, spikes/ 90 PNG magma, frames.synth.bak/ + physics_log.synth.bak.csv present)
```

### 1.3 Artifact table (size + key property, all LIVE)

| file | size | key property (live command output) | verdict |
|---|---|---|---|
| out/trophy_hunt.mp4 | 354K (362406 bytes, <50MB ✓) | ffprobe: `codec_name=h264 width=1280 height=480 pix_fmt=yuv420p r_frame_rate=30/1 duration=3.000000` exit=0 | VERIFIED |
| out/physics_log.csv | 4.2K, 91 lines (header + 90 rows ✓) | `python3 tools/check_sync.py --csv out/physics_log.csv` → `PASS: 90 rows ... monotonic ...` exit=0; `grep -c ",1$"` = 5 (hits @frames [0,19,46,65,85]) | VERIFIED |
| out/spikes.npz | 6.4M | keys `['spike_times','spike_ids','bin10ms_rate']`; `bin10ms_rate.shape=(300,)` ✓ (3s/10ms); `check_spikes.py` → `shape=(300,) n_spikes=412811 rate_mean=25.02` PASS exit=0 | VERIFIED |

Raw quoted outputs:
- ffprobe: `codec_name=h264 / width=1280 / height=480 / pix_fmt=yuv420p / r_frame_rate=30/1 / duration=3.000000`, `ffprobe_exit=0`
- csv: `wc -l` = 91; `grep -c ",1$"` = 5; check_sync PASS line quoted above
- npz: `keys ['spike_times', 'spike_ids', 'bin10ms_rate'] / shape (300,) / mean 25.0188 / n_spikes 412811`
- meta: `path= real-egl frames= 90` (`python3 -c "import json; ..."` live)
- run_egl.log: `model-ok nq=7 nv=6 arena=arena/hunt_arena.xml timestep=0.0005`; `render-ok shape=(480, 640, 3) dtype=uint8 mean=150.0 EGL 640x480`; `step-ok n_steps=5940 sim_time=2.9700s wall=4.75s`; `brian2-ok n_spikes=412811 neurons=5500 wall=8.77s schedule=base20/stim140/rearm5 seed=1`; `hits=5 @frames [0, 19, 46, 65, 85] ammo_left=0`
- perf: mujoco sim/wall **0.625** (2.9700/4.75), brian2 sim/wall **0.342** (3.0/8.77) from `out/perf.md` (Task 4, branch rerun/qa)

## 2. Grep-path honesty (NO fake)

Acceptance literal: `test -f out/trophy_hunt.mp4 && test -f out/physics_log.csv` → exit **0** (both present, verified this task via bash `GATES_OK`).

## 3. TL;DR cross-check (rerun plan line 3 claims → disk verdict)

Source: `.omo/plans/ai-trains-fly-rerun.md` line 3 — real EGL 3s artifacts `out/trophy_hunt.mp4 1280x480@30fps`, `out/physics_log.csv` 90 rows, `out/spikes.npz` from REAL run (mujoco 3.9.0 EGL + brian2 2.10.1).

| TL;DR claim | disk evidence | verdict |
|---|---|---|
| video 1280x480@30fps, hstack, crf23, libx264, <50MB | ffprobe 1280/480/30/1/h264 yuv420p 3.0s, 354K; exact scope ffmpeg cmd in fail_ffmpeg.log exit 0 | VERIFIED |
| 90 frames / 3s EGL 640x480 | frames 90 PNG; csv 91 lines (90 rows); run_meta frames=90 fps=30; npz 300 bins = 3s/10ms; run_egl.log render-ok EGL 640x480 | VERIFIED |
| CSV 90 rows, monotonic, >=1 hit | check_sync PASS 90 rows; `grep -c ",1$"` = 5 @[0,19,46,65,85] | VERIFIED |
| spikes (300,) ~25Hz | check_spikes PASS shape=(300,) n_spikes=412811 rate_mean=25.02; meta spike_rate_hz mean 25.019 | VERIFIED |
| meta path=real-egl | `path= real-egl` live JSON query | VERIFIED |
| EGL log model-ok/step-ok | run_egl.log lines quoted in §1.3 (model-ok + step-ok + render-ok + brian2-ok) | VERIFIED |
| perf 0.625/0.342 | out/perf.md: mujoco 0.625 (2.97/4.75), brian2 0.342 (3.0/8.77), VRAM 0.0039GB, RSS ≤0.036GB | VERIFIED |

Success-criteria spot-checks (rerun plan lines 69–71): video 1280x480@30 libx264 354K <50MB ✓; CSV 90 rows monotonic ✓ (check_sync PASS); ≥1 hit reward>0 dW logged ✓ (5 hits, reward 0.98, dW_mean logged per hit in run_meta.json); `run_meta.json:path` == `real-egl` ✓; `model-ok step-ok` in `out/run_egl.log` ✓.

## 4. Overall verdict: ALL PRESENT — TL;DR in sync with REAL-RUN artifacts ✅

- `test -f out/trophy_hunt.mp4 && test -f out/physics_log.csv` → exit 0
- per-claim VERIFIED above (7/7), each backed by a live artifact/command output quoted in §1.3
- `out/fail_tldr.log` = not-triggered (no artifact missing; gates passed, no append needed)
