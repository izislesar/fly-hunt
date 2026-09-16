# F3 QA — Real manual agent-executed verification (2026-09-16T13:45:10Z)

All four gates re-executed LIVE by QA reviewer (fresh commands, no copy-paste from prior logs).
Working directory: /home/izislesar/Projects/fly_oxota. No implementation files modified; run_hunt.py NOT re-run.

## Gate 1 — check_circuit
Command: `python3 tools/check_circuit.py --input data/hunting_circuit_6k.npz --max-neurons 6500 --min-neurons 4000`
Exit: 0
Key output (first 10+ lines, verbatim):
```
keys: ['cell_type_detail', 'edges', 'meta_json', 'neuron_ids', 'neuron_types', 'weights_init']
N = 5500 (bounds [4000,6500])
synapses (edges) = 219965
RSS_est = 1.5022 GB (cap 8.0 GB)
  DAN: 100
  DN: 150
  JO: 540
  KC: 2000
  LC4: 104
  LPLC2: 210
  MBON: 96
  ORN: 500
  PN: 300
  SEZ-GRN: 700
  T2/T3-vis: 800
meta: seed=0 target=5500 N=5500 edges_synthetic=True
PASS: N=5500 in [4000,6500], syn=219965, RSS_est=1.5022GB < 8.0GB
```
Evidence: data/hunting_circuit_6k.npz, out/circuit.json

## Gate 2 — headless-3s equivalent (synthetic, honest)
Commands:
- `python3 tools/check_sync.py --csv out/physics_log.csv` → Exit 0
  Output: `PASS: 90 rows, header exact, columns==6, monotonic t_neural/t_physics/frame_id; ratio 5:1 neural:physics (0.1ms x5 = 0.5ms) ok; 66 phys/frame (33.0ms ~= 33.33ms, residual accumulate-and-correct) ok; moose_pos 'x;y;z' ok`
- `ls out/frames/f*.png | wc -l` → `90`, Exit 0
- `wc -l out/physics_log.csv` → `91 out/physics_log.csv` (header + 90 rows)
- Real-EGL probe: `which xvfb-run` → `xvfb-run not found`, Exit 1
- Real-EGL probe: `python3 -c "import mujoco"` → `ModuleNotFoundError: No module named 'mujoco'`, Exit 1
Failure-branch note: real EGL sim IMPOSSIBLE in this env (no mujoco package, no xvfb-run). Synthetic artifacts (90 frames + 90-row CSV PASS) are the executed evidence; the real-EGL branch is BLOCKED-by-env with clean coverage in out/fail_egl.log (import probe + xvfb attempt + synthetic-fallback record). No EGL success faked.
Evidence: out/physics_log.csv, out/frames/f00000..f00089.png, out/fail_egl.log, out/run_meta.json (path=synthetic(mujoco-missing))

## Gate 3 — check_shot
Command: `python3 tools/check_shot.py --range 20 --spread 0.02`
Exit: 0
Key output (verbatim):
```
scenario hit-5m: hit=True reason=hit
scenario miss-25m: hit=False reason=out-of-range
scenario occluded-5m: hit=False reason=no-visibility
cooldown check: ok=True (hit=False reason=cooldown)
hysteresis check: ok=True (hit=False reason=hysteresis-not-rearmed)
ammo_left=4
PASS: all shot checks passed
```
Evidence: out/shot.json

## Gate 4 — ffprobe video
Command: `ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,codec_name -of default=nw=1 out/trophy_hunt.mp4`
Exit: 0
Output (verbatim):
```
codec_name=h264
width=1280
height=480
r_frame_rate=30/1
```
Duration probe: `ffprobe -v error -show_entries format=duration -of default=nw=1 out/trophy_hunt.mp4` → `duration=3.000000`, Exit 0 (≈3s ✓)
Evidence: out/trophy_hunt.mp4

## Cross-consistency
- CSV hits: `grep -c ",1$" out/physics_log.csv` → `2` (frames 30, 65)
- run_meta.json hits: 2 entries (frame 30 dist 9.3034, frame 65 dist 6.1573) — AGREES with CSV
- shot.json params: threshold=3, ammo=5, range_m=20.0, spread_rad=0.02 — AGREES with run_meta shot_params (threshold 3, ammo_max 5, range 20.0, spread 0.02); hit-5m scenario True (model check), run hits 2 ≥ 1 ✓
- Spike rate: mean 22.911 Hz (run_meta) / 22.64 Hz (spike_stats) in [5,200] ✓ (min 18.0, max 140.0)
- Video duration 3.000000s ≈ 3s ✓; resolution 1280x480 @30fps h264 ✓

## F3 VERDICT: APPROVE
4/4 gates exit 0 live + cross-consistency holds. Headless real-EGL branch BLOCKED-by-env, covered cleanly by fail_egl.log (honest synthetic verification, no fabrication).

## RERUN (real-egl, 2026-09-16T17:07Z, branch rerun/qa)

QA re-execution on REAL rerun artifacts (Tasks 1-5 outputs). All 7 plan gates run LIVE
this run (fresh commands, no cached results). Prior content above preserved byte-for-byte.

### Gate results (live, this run)

- budget: `python3 tools/check_budget.py --vram-cap 3.5 --ram-cap 14` → EXIT 0, `PASS rss=1.6484GB vram=0.1525GB`
- circuit: `python3 tools/check_circuit.py --input data/hunting_circuit_6k.npz --max-neurons 6500 --min-neurons 4000` → EXIT 0, `PASS: N=5500 in [4000,6500], syn=120344, RSS_est=1.5014GB < 8.0GB` (edges now REAL: edges_synthetic=False, S=120344)
- sync: `python3 tools/check_sync.py --csv out/physics_log.csv` → EXIT 0, `PASS: 90 rows, header exact, ... 66 phys/frame ... ok`
- physics: `python3 tools/check_physics.py` → EXIT 0, `no NaN in 500 steps`
- shot: `python3 tools/check_shot.py --range 20 --spread 0.02` → EXIT 0, `PASS: all shot checks passed`
- reward: `python3 tools/check_reward.py --hit 1 --dist 5 --loom 50` → EXIT 0, `PASS: 0<reward<=1, miss/no-see=0, clip probe raw=1.2->1.0`
- spikes: `python3 tools/check_spikes.py` → EXIT 0, `PASS: spikes.npz valid` (shape=(300,) n_spikes=412811 rate 4.8/142.7/25.02Hz, meta cross-check diff 0.00Hz)
- bridge (informational 8th): EXIT 1, 10/15 — known иначе-branch state, vendor untouched, not a finding.

Findings: (none — 7/7 EXIT 0, no silent fixes made.)

### Cross-consistency (real run)

- ffprobe (EXIT 0): h264 1280x480 pix_fmt=yuv420p r_frame_rate=30/1 duration=3.000000 size=362406 (354K <50MB) ✓
- CSV hits: `grep -c ",1$" out/physics_log.csv` → 5; run_meta.json hits 5 entries (frames 0,19,46,65,85, dist 12.0→4.36, reward 0.98 each) — AGREE ✓
- N=5500 (circuit gate + npz meta) / DN==150 (circuit quota row) ✓
- shot.json params threshold3/hyst2/ammo5/range20/cooldown500/spread0.02 — frozen, untouched ✓
- run_meta.json path=real-egl, frames=90, 640x480@30 ✓
- Single ffmpeg stitch command (from out/fail_ffmpeg.log): `ffmpeg -y -framerate 30 -i out/frames/f%05d.png -framerate 30 -i out/spikes/sp%05d.png -filter_complex hstack -c:v libx264 -crf 23 -pix_fmt yuv420p out/trophy_hunt.mp4` ✓

RERUN VERDICT: APPROVE
