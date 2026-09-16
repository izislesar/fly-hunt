# 2026-09-16T16:50Z — Task 1 DONE (real EGL 3s hunt, pushed)
- Baseline: repo had 0 commits; created .gitignore (data/*.parquet, out/frames+spikes/*.png except 3 samples, *.bak.*, __pycache__/, *.pt, fly-brain/, .claude-flow/), initial commit `chore(baseline)` on main (32fa829), branch `rerun/run` from main.
- Backups BEFORE overwrite: out/frames.synth.bak/ (90 PNG), out/physics_log.synth.bak.csv, out/spikes.synth.bak.npz, out/trophy_hunt.synth.bak.mp4 (all git-ignored via *.bak.*).
- Venv probes (/home/izislesar/venv-brainfly314/bin/python, py3.14.7): mujoco 3.9.0 ok, brian2 2.10.1 ok, `import torch` FAILS (ModuleNotFoundError, CPU fallback per plan QA), `import flygym` ok as package but `from flygym import Fly` FAILS (vendor drift).
- Vendor dry-probe: `two_flies.py --help` exit=1 AND `--headless --duration 3 --no-viewer` exit=1, both ImportError line 24 `from flygym import Fly` → used tools/run_hunt.py --real-egl fallback (extended Phase-0 branch, new code in run_hunt.py only).
- EGL fix: mujoco.Renderer(model, height, width) — first call passed (640,480) and raised ValueError; correct order (480,640). Camera hunt_cam, moose_box teleported 12m→4m per frame, 66x0.5ms steps/frame.
- brian2 fix: TimedArray values need Hz units (rates*Hz), else DimensionMismatchError. PoissonGroup(5500) TimedArray-10ms 3s seed=1, numpy codegen.
- Run cmd: `MUJOCO_GL=egl CC=gcc CXX=g++ /home/izislesar/venv-brainfly314/bin/python tools/run_hunt.py --real-egl` → brian2 wall 8.77s (412811 spikes), mujoco wall 4.75s (5940 steps, sim 2.9700s), total 27.74s. Hits=5 @frames [0,19,46,65,85], ammo_left=0. DNpe017 counts from real raster neurons {0,1}.
- Verification: 90 PNG 640x480, check_sync PASS 90 rows, grep ",1$" = 5, npz {spike_times (412811,), spike_ids (412811,), bin10ms_rate (300,)}, check_spikes PASS (mean 25.02Hz), meta path=real-egl, run_egl.log has model-ok + step-ok. Note: full-population spike counts now (no /1000 norm; documented in meta spike_scale).
- Commit `feat(run): real egl 3s hunt` (9 files) + `git push origin rerun/run` exit 0 (after `gh auth setup-git`; initial https push failed with no-credential error).
- Frozen untouched: shot threshold3/hyst2/ammo5/range20/cooldown500/spread0.02/seed1, reward formula, clip [0,2], 66 phys/frame, bin10ms, sync header.
- Task 2 ready: out/spikes.npz (300-bin real raster) + out/physics_log.csv + 90 EGL frames in place.
# 2026-09-16T16:49Z — Task 2 DONE (magma spike rerender from real npz, pushed)
- Render cmd: `/home/izislesar/venv-brainfly314/bin/python tools/render_spikes.py --palette 'magma:#000004-#FCFFA4' --size 640x480 --fps 30 --input out/spikes.npz --meta out/run_meta.json --outdir out/spikes` (flags confirmed via --help first; input = CURRENT real-egl npz, never .synth.bak).
- Render output: LUT matplotlib-magma-256 (3.11.2), PIL path, hits=[0,19,46,65,85]; wrote 90 PNGs over stale set (no leftovers possible — full overwrite).
- Verify: `ls out/spikes/sp*.png | wc -l`=90; `file sp00000.png`=PNG 640x480 8-bit RGB; distinct md5=90/90; #FCFFA4 top-24px counts f0=14966 f19=14986 f46=14976 f65=14982 f85=14989; nonhit sp00001 topleft magma (24,15,61).
- Git: .gitignore keeps only 3 spike samples (sp00000/sp00030/sp00065); other 87 PNGs ignored by rule. Committed b0eb76f `feat(viz): rerender magma from real run` (5 files: 3 sample PNGs + out/fail_render.log + learnings.md) + `git push origin rerun/run` exit 0 (2b1c047..b0eb76f). Left untouched: plan-md edit + run-continuation json (out of scope).
# 2026-09-16T16:53Z — Task 3 DONE (restitch real hunt+spikes on rerun/video, pushed)
- Branch: `git checkout -b rerun/video` from `rerun/run` tip 9fb49aa (real EGL frames + magma spikes + code carried over; uncommitted plan-md edit + run-continuation jsons left untouched/out of scope).
- Pre-check: glob `out/frames/f*.png`=90 + `out/spikes/sp*.png`=90 (both 640x480 real inputs, no mismatch, no .synth.bak use).
- Exact cmd (verbatim, exit 0): `ffmpeg -y -framerate 30 -i out/frames/f%05d.png -framerate 30 -i out/spikes/sp%05d.png -filter_complex hstack -c:v libx264 -crf 23 -pix_fmt yuv420p out/trophy_hunt.mp4`.
- ffprobe: codec_name=h264 width=1280 height=480 pix_fmt=yuv420p r_frame_rate=30/1 duration=3.000000 size=362406; `ls -lh`=354K (<50MB PASS). Evidence appended to out/fail_ffmpeg.log as success record.
- LFS note: `git check-attr filter out/trophy_hunt.mp4`=unspecified (no lfs set up) — committed normally per plan fallback, single side-by-side 1280x480 file, no second video/audio/titles.
- Commit 6fb9fd4 `feat(video): restitch real hunt+spikes` (2 files: out/trophy_hunt.mp4 + out/fail_ffmpeg.log) + `git push origin rerun/video` exit 0 (new branch).
- Frozen untouched: shot/reward/clip/sync constants, run_hunt/render code, perf.md/tldr/failures.md/audit; no pip install, no fly-brain edits, no .synth.bak overwrite.
