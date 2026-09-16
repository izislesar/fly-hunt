# Path A Reverify (2026-09-16)

Env: `~/venv-brainfly314/bin/python` (Python 3.14.7), `MUJOCO_GL=egl CC=gcc CXX=g++` exported on every command line.
Libs: mujoco 3.9.0, brian2 2.10.1, flygym 2.1.0 (import-ok), numpy 2.5.3, pandas 2.3.3, pyarrow 25.0.1.
Circuit: `data/hunting_circuit_6k.npz` real-edge (N=5500, syn=120344, edges_synthetic=False).
No compat fixes needed. No files outside `out/` touched. `tools/run_hunt.py` NOT re-run. No pip installs. No plan-file edits.

## Phase 1 — gates (all live, venv python, EXIT 0)

| # | Gate (exact command) | Result line | EXIT | VERDICT |
|---|----------------------|-------------|------|---------|
| 1 | `tools/check_budget.py --vram-cap 3.5 --ram-cap 14` | `PASS rss=1.6484GB vram=0.1525GB` | 0 | PASS |
| 2 | `tools/check_circuit.py --input data/hunting_circuit_6k.npz --max-neurons 6500 --min-neurons 4000` | `PASS: N=5500 in [4000,6500], syn=120344, RSS_est=1.5014GB < 8.0GB` (keys neuron_ids/neuron_types/cell_type_detail/edges/weights_init/meta_json; meta seed=0 target=5500 edges_synthetic=False) | 0 | PASS |
| 3 | `tools/check_sync.py --csv out/physics_log.csv` | `PASS: 90 rows, header exact, columns==6, monotonic ...` | 0 | PASS |
| 4 | `tools/check_physics.py` | `PATH=real model=.../arena/hunt_arena.xml` + `no NaN in 500 steps` | 0 | PASS |
| 5 | `tools/check_shot.py --range 20 --spread 0.02` | `PASS: all shot checks passed` (hit-5m hit / miss-25m out-of-range / occluded no-visibility / cooldown ok / hysteresis ok, ammo_left=4) | 0 | PASS |
| 6 | `tools/check_reward.py --hit 1 --dist 5 --loom 50` | `reward=1.0 dW_mean=1.0587914334995865 pulse=True` + `PASS: 0<reward<=1, miss/no-see=0, clip probe raw=1.2->1.0` | 0 | PASS |
| 7 | `tools/check_spikes.py` | `shape=(300,) n_spikes=342 rate_mean=22.64` + `cross-check diff=0.27Hz OK` + `PASS: spikes.npz valid` | 0 | PASS |

Note: bare `check_budget.py` / `check_circuit.py` with no flags exit 2 (argparse, required flags) — expected, not a failure; historic flags from plan scope (`--vram-cap 3.5 --ram-cap 14`, `--input data/hunting_circuit_6k.npz --max-neurons 6500 --min-neurons 4000`) used above. Frozen numbers untouched; zero compat edits to `tools/*.py`.

**Phase 1 VERDICT: PASS (7/7 EXIT 0, no fixes required)**

## Phase 2 — real EGL attempt (mujoco 3.9.0 vs 3.1.6-schema XML)

Direct EGL first (no xvfb needed):

```
$ MUJOCO_GL=egl ~/venv-brainfly314/bin/python -c "import mujoco; m=mujoco.MjModel.from_xml_path('arena/hunt_arena.xml'); d=mujoco.MjData(m); mujoco.mj_step(m,d); print('model-ok step-ok', m.nq, m.nv)"
model-ok step-ok 7 6
EXIT:0
```

- Version warnings: NONE (no warnings printed; 3.9.0 loaded the 3.1.6-schema XML cleanly). No XML edits made (none needed — error-named-element condition never triggered).
- 500-step NaN check: `steps=500 nan= False qpos0= [5.0, 2.46e-22, 0.199997]` EXIT 0.
- Render: `mujoco.Renderer` present (`has_Renderer= True`). First attempt `Renderer(m, 640, 480)` failed with `ValueError: Image height 640 > framebuffer height 480...` (arg-order mistake, not a model error); retry `Renderer(m, 480, 640)` → `render-ok (480, 640, 3) uint8`, saved via PIL to `out/egl_probe.png` (640x480 RGB, 70240 B) EXIT 0. No context7 lookup needed. xvfb-run retry not required (direct EGL succeeded); `which xvfb-run` = `/usr/bin/xvfb-run` confirmed present as fallback.

**Phase 2 VERDICT: PASS — real sim achieved (model-ok + step-ok + 500 steps NaN-free + offscreen render saved).**

Caveats closed: T7 stepping caveat FALLS (real `mj_step` works, incl. 500-step loop); T8 analytic caveat PARTIALLY FALLS (check_physics now reports `PATH=real`, 500 real steps NaN-free — full-physics audit still downstream work); T12 synthetic-path caveat NARROWED but NOT fully closed (run artifacts remain synthetic-rendered; EGL render proven possible for future re-runs).

## Files
- No `tools/*.py` modifications (compat fixes: none).
- `out/egl_probe.png` created (640x480 RGB first-frame offscreen render).
- This file `out/PATH_A_REVERIFY.md` created.
