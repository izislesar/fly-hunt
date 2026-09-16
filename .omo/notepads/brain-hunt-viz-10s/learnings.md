# 2026-09-16T18:30Z — Task 1 DONE (CUDA-check + real EGL 10s take, pushed viz10/sim)
- Branch: `git checkout -b viz10/sim` from main tip e62d626 (clean except pre-existing session noise: modified run-continuation json + out/fail_circuit.log, both left uncommitted/out of scope).
- STEP 0 CUDA gate PASS (before anything expensive): venv python torch probe → `2.14.0+cu130 True NVIDIA GeForce RTX 3050 Laptop GPU`; `nvidia-smi --query-gpu=name,memory.total --format=csv` → `NVIDIA GeForce RTX 3050 Laptop GPU, 4096 MiB`. No fail_cuda.log needed.
- Code: new `--real-egl-10s` path in tools/run_hunt.py (dispatch BEFORE `--real-egl`; diff 267 insertions / 0 deletions — 3s functions byte-identical). New consts: N_FRAMES_10=300, N_BINS_10=1000, STIM_FRAMES_10=(30,31,65,66,130,131,165,166,230,231,265,266)@140Hz, REARM_FRAMES_10=(45,145,245)@5Hz, base 20Hz; new fns `build_bin_rate_schedule_10`, `run_brian2_raster_10` (10s), `run_mujoco_egl_10` (pixels → NEW out/frames10/, 3s out/frames/ untouched), `torch_state_probe_10`, `main_real_egl_10`. Frozen reused: threshold3/hyst2/ammo5/range20/cooldown500/spread0.02/seed1, reward.py, 66 phys/frame x0.5ms, bin10ms, sync header.
- .gitignore: added `out/frames10/*.png` + `!out/frames10/probe_*.png` (300 PNGs stay untracked; Task 5 probes keepable).
- Exact cmd: `MUJOCO_GL=egl CC=gcc CXX=g++ /home/izislesar/venv-brainfly314/bin/python tools/run_hunt.py --real-egl-10s` → exit 0.
- Wall times (out/run_egl_10s.log): mujoco sim 9.9000s / wall 11.57s (19800 steps); brian2 10s / wall 24.84s (1354381 spikes, PoissonGroup 5500 TimedArray-10ms seed=1); total_wall=59.29s (incl. vendor probes). Vendor drift unchanged: two_flies.py --help + --headless both exit 1, ImportError flygym.Fly.
- Results: hits=5 @frames [0,19,46,65,85], ammo_used=5, ammo_left=0 (early schedule identical to 3s take → same 5 hits; later volleys 130/230 unfired, ammo exhausted — expected, acceptance >=1). npz keys exact, bin10ms_rate (1000,) mean 24.63Hz. meta path=real-egl-10s frames=300. Log has model-ok + render-ok + step-ok + brian2-ok + torch CUDA line.
- Verification: check_sync --csv out/physics_log_10s.csv → PASS 300 rows (fail_sync.log side-effect reverted); grep -c ",1$" = 5; inline npz shape/mean PASS (check_spikes.py hardcodes 300 bins — NOT edited, per plan); 3s files verified unmodified (git status on physics_log.csv/spikes.npz/run_egl.log/run_meta.json/frames//spikes//trophy_hunt.mp4 → empty).
- Commit `feat(sim10): real egl 10s take` = 2036110 (7 files, +3695), `git push origin viz10/sim` exit 0 (new branch, PR link offered by remote). Tree left ready for Task 2 (layout): pre-existing noise (run-continuation json, fail_circuit.log) still uncommitted; plan/design docs untracked.

# 2026-09-16T18:45Z — Task 2 DONE (C1 layout + edge layer, pushed viz10/brain)
- Branch: `git checkout -b viz10/brain` from viz10/sim tip a60ea00. Commit 34eaec3 `feat(brain): layout + edge layer` (4 files, +181), `git push origin viz10/brain` exit 0 (new branch).
- Code: `tools/brain_layout.py` (CPU-only; venv /home/izislesar/venv-brainfly314/bin/python). Live npz read first: 11 types sorted [DAN DN JO KC LC4 LPLC2 MBON ORN PN SEZ-GRN T2/T3-vis], counts [100 150 540 2000 104 210 96 500 300 700 800]; palette assigned in sorted order.
- Method: radial-fallback (honest record in npz). Primary spectral ran FAST (wall 1.3–1.4 s, eigsh k=3 SM, eigvals [-0,-0,0]) but collapsed: graph has ≥5 zero eigenvalues (disconnected components); thumbnail bar 0/11 separable. Zero-skipping retry (k=8, first two eigvals>1e-8 = 0.0017/0.0025) still 2/11 → genuine hairball, fallback per spec. Never claimed spectral.
- Fallback geometry: 11 centers on 600x440 ellipse ordered by live count desc from top (-90°), R=k*sqrt(count) with k=70/sqrt(2000)≈1.565 so KC (largest, 36%) R=70 fits without overlap, jitter σ=0.35R, seed=7, clipped to 24px margins. Radial thumbnail: 11/11 separable (bar ≥9/11 PASS).
- Contrast vs #0B1020 (all ≥3:1 PASS): DAN 6.82, DN 9.95, JO 13.28, KC 10.84, LC4 10.52, LPLC2 7.65, MBON 6.38, ORN 7.85, PN 7.93, SEZ-GRN 12.25, T2/T3-vis 17.04.
- Edge layer: top 20000/120344 by weights_init desc, 5716 zeros dropped, #5A6B9A alpha 0.08. Rendered at 2x supersample + LANCZOS downscale to honor 0.5px linewidth (PIL min 1px); coverage 25.34% pixels above bg+8 (<40% AND >0 PASS). Fix note: first attempt k_scale=9.0 gave R_KC=402px (clusters spanning frame) + 1px lines → 79.35% coverage FAIL; compact sizing + 0.5px rendering fixed it.
- Outputs: out/brain_layout.npz keys [positions colors palette type_names counts seed method], positions (5500,2) float32 in [24,616]x[24,456]; out/brain_edge_bg.png 640x480 RGB (0 pure-black px); out/brain_thumb_320x240.png evidence. 10 s take files verified untouched (git diff empty).

# 2026-09-16T21:55Z — Task 3 DONE (C2 renderer + G1 probes, pushed viz10/brain)
- Renderer: `tools/brain_render.py` (venv torch 2.14.0+cu130, CUDA True, RTX 3050 Laptop GPU).
  Vectorized splat (index_put_ accumulate, 3ch) + depthwise gaussian sprite (r6/s2.0) +
  bloom (r12/s4.0/0.6) additive over edge bg in LINEAR space (bg sRGB->linear pow2.2,
  encode pow(1/2.2) once). Per-frame min-max norm [0.15,1.0], frame=mean of its 10/3 bins,
  decay tau=4 weight-normalized average over trailing 24 frames. White-hot core = lit^2*0.6.
  Legend DejaVuSansMono 14px #E7F5FF on 40%-alpha navy pill (`frame F/300 · t T.Ts · rate R Hz`).
- Frame-rate scan (1000 bins -> 300 frames): hits [0,19,46,65,85] rates
  [19.85,19.98,19.84,109.01,20.25]Hz -> HIT probe = frame 65 (volley 65,66, hottest hit).
  Median frame rate 19.98Hz -> MED probe = frame 158 (far from hits, base-rate quiet).
- Probe stats (640x480 sRGB): hit rate=109.01 lit_max=0.540 lit_mean=0.3036;
  med rate=19.98 lit_max=0.485 lit_mean=0.2616. bg sample (11,16,32) exact (3 spots, both).
  White frac 0.000% both (<5% PASS). Hot px hit-vs-med: lum>60 16407/14752 (+11%),
  lum>100 5825/4523 (+29%), lum>150 1104/901 (+22%), lum>200 478/419. Neurons lit>0.4:
  220 vs 62 (3.5x). core_p99 359 vs 335. Legend band max #E7F5FF exact, min ~bg (legible).
- Perf: nvidia-smi 4096MiB total / 5MiB idle; torch max_memory_allocated peak 0.030 GB
  (<=3GB PASS, 2 probes only). Render t 1.43s/0.22s (hit builds 25-frame decay history);
  render-only fps ~1.21 -> 300f projection ~248s (<=10min bound; Task-4 loop amortizes
  history, runs incremental decay instead). First-attempt bg wash (61,72,99) root-caused
  to double-gamma, fixed in linear pipeline, evidence in out/fail_brain.log (no spec-number retune).
- Commit `feat(brain): cuda renderer + G1 probes` + `git push origin viz10/brain` exit 0.
  HARD STOP after push: full 300-frame render is Task 4 (needs G1 human OK).
- Push: first attempt connection-reset, retry exit 0 (`34eaec3..3f6a545 viz10/brain -> viz10/brain`).
