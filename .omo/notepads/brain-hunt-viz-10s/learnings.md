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

# 2026-09-16T22:05Z — G1 fix DONE (global normalization, re-pushed viz10/brain)
- Human gate rejected per-frame min-max (equal-brightness evidence above, logged in out/fail_brain.log).
- Change confined to tools/brain_render.py normalization: global p99 anchor A=2.0 counts over
  1000-bin per-neuron matrix (single vectorized bincount, 5.5M cells); map [0,A]->[0.03,1.0].
  Aggregation (mean of frame's 10/3 bins), tau=4 weight-normalized decay, sprite/bloom/gamma,
  palette, bg, legend all byte-identical logic. Side benefit: matrix reuse cut render to 0.72s/0.04s.
- Probes re-rendered ONLY (frames 65 hit / 158 med): gap now 2.81x (lum>100) / 9.75x (lit>0.2) /
  157x (lit>0.3). bg exact, white 0%, legend legible, VRAM 0.030GB, 300f projection ~114s.
- Commit `fix(brain): global normalization for G1` + push (see below). HARD STOP, awaiting G1 re-review.

# 2026-09-16T19:30Z — Task 4 DONE (C2 full 300 frames, pushed viz10/brain)
- Renderer FROZEN byte-for-byte: tools/brain_render.py md5 30d8e89fc69be420884cad5bae94c3b6 before AND after
  (no param change; driver /tmp/kilo/brain_full.py imported render_frame/frame_bins/gauss_kernel2d + consts;
  repo diff contains only the 300 PNGs). Global p99 anchor recomputed = 2.0000 counts (max 9, mean 0.2463),
  norm [0.03,1.0], sprite r6/s2.0, bloom r12/s4.0/0.6, gamma 2.2, tau 4, same legend pipeline.
- Render: frames 0-299 -> out/brain/b%05d.png, `ls out/brain/b*.png | wc -l` = 300, dir 45M.
  WALL_S=80.3 (<=600 PASS), torch.cuda.max_memory_allocated peak 0.030 GB (<=3 PASS),
  nvidia-smi post-run 5MiB/4096MiB. venv torch 2.14.0+cu130 CUDA True RTX 3050 Laptop GPU.
- Spot checks: file b00000/b00150/b00299 = PNG 640x480 8-bit RGB; md5 sample all distinct
  (b00000 aff89f3f, b00001 8b0dad76, b00065 13f1ce1a, b00150 41c9d297, b00158 6bcc73aa, b00299 46836386).
- Commit 324d51e `feat(brain): full 300 frames` (300 files, exact message) on viz10/brain.
  Push: 3x transient `Recv failure: Connection reset` (same flake as Task 3); retry loop attempt-1 printed
  `c28b14a..324d51e viz10/brain -> viz10/brain`; ls-remote confirms origin/viz10/brain = 324d51e. Exit 0.
- Ready for Task 7 assembly: complete consistent 300-PNG set (b00000-b00299).

# 2026-09-16T23:10Z — Task 5 DONE (C3 hunt adapter + 3 G2 probes, pushed viz10/hunt)
- Branch: `git checkout -b viz10/hunt` from viz10/brain tip 324d51e (brain 300 PNGs carried over, untouched).
- Vendor API resolution (live, venv-brainfly314 / flygym 2.1.0 — never guessed):
  1. `fly-brain/two_flies.py --help` reproduces drift: `ImportError: cannot import name 'Fly'`
     (top-level `flygym/__init__.py` exports only assets_dir/anatomy/compose/flybody/Simulation/Renderer/...).
  2. CORRECT: `from flygym.compose import NeuroMechFly` (`Fly` is a deprecated alias of the same class;
     using the canonical name avoids the DeprecationWarning). Rotations: `flygym.utils.math.Rotation3D`
     (`Vec3` is a jaxtyping alias — spawn positions passed as plain sequences).
  3. Ground contact sensors broken in 2.1: compile fails `unrecognized name 'nmf/lf_coxa' of sensorized
     object` (any fly name) -> `add_fly(..., add_ground_contact_sensors=False)` (look-dev needs no contacts).
  4. World units are MM (SCALE=1000); hunt_arena.xml values converted m->mm in the adapter (XML untouched).
- New code ONLY in tools/: `tools/fly_compose.py` (build_hunt_scene: FlatGroundWorld(half_size=15000) +
  colorized NeuroMechFly + static moose-box 0.4x0.3x0.4m@x=5m + MOCAP loom r=0.15m + sun + fill + runtime
  cameras + lerp-0.2 tracking helper + pinhole project; tune_visuals) and `tools/fly_probe.py` (3 probes +
  dark-pixel bbox + 16-bin bands + md5 determinism). `git diff -- fly-brain/ arena/` EMPTY (both read-only).
- Gotchas hit (evidence, not lore): (a) 500-step settle LAUNCHED the fly to z=129mm (spawn contact explosion)
  -> static neutral-pose only (thorax z=1.9mm, feet on ground; probes are single frames). (b) Default fly geoms
  all uniform gray 0.5 -> `colorize(visuals.yaml)` required for the real amber/red-eyed Drosophila look.
  (c) FlatGroundWorld ships vis.map.zfar=250 (=250mm here) + haze 0.3 -> every render beyond 250mm was pure
  white (wide+mid); runtime-only fix `tune_visuals` (zfar=1e5, haze=0, headlight 0.5/0.6->0.2/0.25, spec untouched).
  (d) MjSpec enums are ints: add_geom type=mjtGeom.mjGEOM_BOX/SPHERE, add_light type=mjtLightType (no `directional`
  kwarg); static moose needed contype=conaffinity=0 + 5mm lift (static-static contact is FatalError).
  (e) Real-scale truth: fly and 4m-loom sit ~40 deg apart from any near-fly camera — no single 20-deg framing
  holds both (Momus #5 verified numerically); mid-action is a bisect-aimed two-shot at fovy=32 (logged).
- Probes (640x480 EGL, `MUJOCO_GL=egl`, identical settled qpos in all three): wide fovy45 (establishing:
  checker + moose + loom dot, fly ~2px as predicted, bbox 0 logged honestly), close fovy20 tracking
  (offset 32,-26,22 converged via 40x lerp-0.2 steps): bbox 52x55 maxside=55 (>=40 PASS), bands=5 (>=3 PASS);
  mid fovy32 bisect (fly ~15px + ~90px loom ball + moose edge): fly 7x6, bands=5. Determinism: close re-render
  from rebuilt scene = byte-identical True. Cmd: `MUJOCO_GL=egl venv-brainfly314/bin/python tools/fly_probe.py`.
- Commit `feat(hunt): fly adapter + G2 probes` + `git push origin viz10/hunt` exit 0. HARD STOP: full 300-frame
  render is Task 6 (needs G2 human OK). NOTE: out/frames10/f*.png (300 arena-only take frames) present on disk
  from an earlier lane, git-ignored, left untouched.
