# Failure gates inventory — Task 17 (2026-09-16) + Task 5 rerun section (2026-09-16, branch rerun/qa)

Acceptance: `ls out/fail_*.log` = 14 files (>= 2 required). TRIGGERED clean-fail entries: 3
(fail_egl, fail_pins pip gate, fail_reward clip probe). Exit codes below are read from each
gate file's recorded output, not invented.

| gate file | exists | status | exit code | cause + remediation |
|---|---|---|---|---|
| out/fail_egl.log | YES | TRIGGERED clean-fail | 1 (`import mujoco` ModuleNotFoundError, no MUJOCO_GL env) | cause: mujoco/brian2/flygym not installed on system python 3.14.7 (PEP668), no brain-fly env; EGL libs present but unusable. remediation: miniforge `mamba env create -f environment.yml`, retry `MUJOCO_GL=egl python -c "import mujoco;print(mujoco.__version__)"` expect 3.1.6. Task 12 section records synthetic fallback (xvfb-run absent). |
| out/fail_fetch.log | YES | NOT-TRIGGERED pass-note | final 0 (`git lfs pull`); initial clone stalled exit 124 (timeout, not hard failure) | cause of stall: LFS smudge payload slow. remediation used: `GIT_LFS_SKIP_SMUDGE=1 git clone` + `git lfs pull`. Fail-closed rule for later tasks recorded in file. |
| out/fail_shot.log | YES | NOT-TRIGGERED pass-note (branch coverage) | acceptance `python tools/check_shot.py --range 20 --spread 0.02` exit 0 | no-shot branches handled cleanly: out-of-range (25m > 20m) and no-visibility (occluded 5m) -> hit=False with reason; in-range 5m count=3 -> hit=True; cooldown/hysteresis sub-checks ok=True. No unhandled miss. |
| out/fail_oom.log | YES | NOT-TRIGGERED pass-note | 0 (`python tools/check_budget.py --vram-cap 3.5 --ram-cap 14` PASS) | cause none: rss=1.6484GB (<14), vram=0.1525GB (<3.5). remediation armed: chunked 100k-synapse load when RSS>12GB. |
| out/fail_pins.log | YES | TRIGGERED clean-fail (pip gate) | pip grep exit 1 (empty match); ffmpeg libx264 grep exit 0 | cause: system pip 26.2.1 PEP668 externally-managed, no conda/mamba, brain-fly env missing; pins declared-not-installed in pins.md. remediation: `mamba env create -f environment.yml`, re-run pip freeze grep expect exit 0. ffmpeg n9.0.1 OBSERVED (not failed) — libx264 present so PASS. |
| out/fail_sync.log | YES | NOT-TRIGGERED pass-note | 0 (`python tools/check_sync.py --csv out/physics_log.csv` PASS, 90 rows) | cause none: monotonic t_neural/t_physics/frame_id, 5:1 neural:physics, 66 phys/frame with residual correction. |
| out/fail_circuit.log | YES | NOT-TRIGGERED pass-note | 0 (`python tools/check_circuit.py` PASS) | cause none: N=5500 in [4000,6500], syn=219965, RSS_est=1.5022GB < 8GB. |
| out/fail_physics.log | YES | NOT-TRIGGERED pass-note | 0 (`python tools/check_physics.py --steps 500` PASS) | cause none: analytic path (mujoco missing), XML cross-checked, no NaN in 500 steps; fudge flags OFF. Task 7 section notes no NaN/freeze observed; watchdog recovery path documented for real runs. |
| out/fail_reward.log | YES | TRIGGERED clean-clip (handled) | acceptance `python tools/check_reward.py --hit 1 --dist 5 --loom 50` exit 0; probe raw=1.2 -> clipped 1.0 | cause of probe: hit=1 dist=0 loom=0 gives raw 1.2 > 1. remediation built-in: `reward()` clips to [0,1], no escape observed; miss->0, no-see->0 asserted. |
| out/fail_bridge.log | YES | NOT-TRIGGERED (иначе-branch handled) | acceptance grep exit 0 (`451: def step`); `tools/check_bridge.py` exit 1 but covered | cause of check_bridge FAILs (10/15): `def reset/spike/torque`, DNpe017-in-bridge, torch probe — all covered by out/ADAPTATION.md diff. No missing-ADAPTATION condition occurred. |
| out/fail_spikes.log | YES | NOT-TRIGGERED pass-note | 0 (`python tools/check_spikes.py` PASS) | cause none: raster non-empty, n_spikes=342, bins=300, rate_mean=22.64Hz in [5,200]Hz. |
| out/fail_render.log | YES | NOT-TRIGGERED pass-note | 0 (render + structural verify) | cause none: 90/90 PNG 640x480 distinct md5, LUT endpoints exact #000004->#FCFFA4, burst color on hit frames 30/65. CLI `python3 tools/render_spikes.py --palette magma:#000004-#FCFFA4 --size 640x480 --fps 30`. |
| out/fail_ffmpeg.log | YES | NOT-TRIGGERED pass-note | 0 (exact scope ffmpeg cmd) | cause none: 1280x480 30/1 h264, 3.0s, 47555B < 50MB; 90+90 inputs verified. QA-fail path not hit. |
| out/fail_perf.log | YES | NOT-TRIGGERED pass-note | SLO ALL-PASS (checker walls 0.231–0.498s, sim/wall effective 6.0–13.0) | cause none: VRAM 0.0039 measured / 0.1525 projected (<3.5), RSS VmHWM <=0.034 / 1.6484 projected (<14). Remediation on exceedance: chunked 100k + CPU Brian2 priority, re-run check_budget.py. |

## Uncaught-exception audit (2026-09-16)

- `grep -rn "except:" tools/*.py` -> `no-bare-except` (no bare `except:` in any checker/tool).
- Known failure modes route to fail_*.log: EGL/import errors (fail_egl), pins mismatch (fail_pins),
  OOM/budget (fail_oom), fetch stall (fail_fetch), circuit bounds (fail_circuit), sync monotonicity
  (fail_sync), physics NaN (fail_physics), shot no-shot branches (fail_shot), reward clip (fail_reward),
  bridge mismatch (fail_bridge via ADAPTATION.md), empty raster (fail_spikes), render count (fail_render),
  ffmpeg mismatch (fail_ffmpeg), perf SLO (fail_perf).
- No uncaught tracebacks observed outside fail logs. No gaps found; no code fixes made (per task card,
  gaps would be documented as findings for the orchestrator — none to report).
- Statement: `no bare except found` + `all known failure modes route to fail_*.log`.

## Counts

- `ls out/fail_*.log | wc -l` = 14 (>= 2 acceptance met; refs minimum egl/fetch/shot/oom all present).
- TRIGGERED clean-fail/clip entries: fail_egl (exit 1), fail_pins pip gate (exit 1), fail_reward clip probe
  (clipped, exit 0 acceptance) = 3 documented FAIL-clean entries.
- Fail logs are read-only inputs; only this file (out/failures.md) was written by Task 17.
- Note: out/fail_tldr.log appeared mid-task (parallel Task 18 TL;DR owns it) — out of scope here,
  inventoried 14 above; `ls` count at verification time = 15, acceptance (>=2) unaffected.
- Prepared commit msg (NOT committed): chore(qa): failure gates

---

## RERUN section — Task 5 real-egl rerun (2026-09-16, branch rerun/qa)

Historical Task 17 entries above are PRESERVED unchanged. This section records only what
failed (or was accepted as known) during the real rerun (Tasks 1–4) and Task 5 verification.

### Rerun failures (all resolved, zero open blockers)

| # | failure | evidence | resolution | status |
|---|---|---|---|---|
| R1 | Vendor drift: `fly-brain/two_flies.py` line 24 `from flygym import Fly` → ImportError with flygym 2.1.0 (`--help` exit=1, `--headless --duration 3 --no-viewer` exit=1) | `out/run_egl.log` line 4 (`vendor: two_flies.py --help exit=1, --headless exit=1 (ImportError flygym.Fly -> run_hunt.py real-path fallback)`); `out/run_meta.json` → `vendor_drift.{--help,--headless --duration 3 --no-viewer}.exit=1` with ImportError tails | Fallback used: `tools/run_hunt.py --real-egl` (extended Phase-0 branch; vendor NOT edited per plan ADAPTATION contract) → real EGL run delivered 90 frames + CSV + npz + meta path=real-egl | known-accepted, closed |
| R2 | torch absent in `~/venv-brainfly314` (`ModuleNotFoundError: No module named 'torch'`) | `out/run_egl.log` line 3 (`torch: ModuleNotFoundError ... (CPU fallback, not a failure)`); `out/run_meta.json` → `torch_state` + `import_probe.torch` same message | CPU fallback accepted per rerun plan QA (`torch.cuda False = CPU fallback, not a failure`); no pip install performed (env frozen); run completed brian2 wall 8.77s, 412811 spikes | known-accepted, closed |
| R3 | LFS unconfigured (`git check-attr filter out/trophy_hunt.mp4` = unspecified) | Task 3 learnings entry (2026-09-16T16:53Z) | Normal commit of single 354K mp4 per plan fallback (no second video, no LFS invention); pushed to `origin/rerun/video` exit 0 | known-accepted, closed |

### Rerun QA-happy (Task 5 verification, live this task)

- `test -f out/trophy_hunt.mp4 && test -f out/physics_log.csv` → exit 0 (GATES_OK).
- ffprobe live: `codec_name=h264 width=1280 height=480 pix_fmt=yuv420p r_frame_rate=30/1 duration=3.000000` exit=0; mp4 354K <50MB.
- `python3 tools/check_sync.py --csv out/physics_log.csv` → PASS 90 rows exit=0; `grep -c ",1$"` = 5.
- `python3 tools/check_spikes.py --input out/spikes.npz` → `shape=(300,) n_spikes=412811 rate_mean=25.02` PASS exit=0.
- `out/run_meta.json` → `path= real-egl frames= 90` (live query).
- `out/run_egl.log` → model-ok + step-ok + render-ok + brian2-ok lines present (quoted in tldr_check §1.3).
- `out/perf.md` (Task 4, rerun/qa) → mujoco 0.625, brian2 0.342, VRAM 0.0039GB, RSS ≤0.036GB.
- `out/fail_tldr.log` = not-triggered (no artifact missing; no append needed — QA-happy path).

### Open blockers: ZERO

- No unresolved failures from the rerun. R1–R3 are known-accepted with fallbacks recorded.
- Downstream Task 6 (mini-audit) can read `out/tldr_check.md` + this file as complete and traceable.
