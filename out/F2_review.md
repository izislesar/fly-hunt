# F2 Code Quality Review (final-wave, audit-only)

Plan checkbox: `F2. Code quality review - expect grep -r "sk-" src || true no secrets + grep -c DNpe017 scope<=150 + grep -c "ffmpeg" одна команда hstack`
Plan refs: `/home/izislesar/.omo/plans/ai-trains-fly.md` line 137; Must-NOT list line 17 (no full-138k, no realtime viz, no new fly bodies, no audio/titles, no real weapon, no DN beyond 150, no full retrain, no network after fetch, no ffmpeg change).

## 1. Secrets scan — PASS (empty)
Command:
```
grep -rn "sk-\|api[_-]key\|secret\|password\|token" tools/ arena/ docs/ --include="*.py" --include="*.md" -i | head -n 20
```
Output: (empty — no lines; only `head` pipeline status observed, zero match lines). No file:line hits. No REJECT trigger.

## 2. DN scope — PASS (DN total = 150, DNpe017 analytic only)
Command:
```
grep -rn "DNpe017" tools/ | head -n 30  → 16 lines total (incl. 2 binary .pyc self-matches)
```
Quoted source hits (all analytic shot/bridge/circuit-selection, NOT an expanded DN population):
- `tools/select_circuit.py:9`: `MBON 96 + DAN 100 (PAM+PPL101) + DN 150 (DNpe017, DNp20, GF 2,`
- `tools/select_circuit.py:28`: `DN 150 composition: DNpe017 x2 + DNp20 x2 + GF(DNp01/Giant Fiber) x2 +`
- `tools/select_circuit.py:216/229/237`: named-mask selection `DNpe017/DNp20/DNp09/DNa01/DNa02`, `DN_named` accounting
- `tools/check_shot.py:2/4/15/69`: shot-model constants + docstring (`threshold=3 spikes/10ms bin on DNpe017`)
- `tools/check_bridge.py:8/99/100/101`: DNpe017 reference check against `brain_body_bridge.py` (expects ABSENT — bridge DN set is P9/DNa01/DNa02/MDN/GF/aDN1/MN9; DNpe017 lives in annotations + circuit NPZ)
- `tools/run_hunt.py:10/27`: docstring — counts `>=3 at frames 30,31,65,66` through real ShotController
- 2x `tools/__pycache__/check_shot.cpython-314.pyc: binary file matches` (build artifact, not source)

Circuit scope (real output):
```
python3 -c "import json; ..." out/circuit.json → N=5500, per_type_counts DN=150 (DAN 100, JO 540, KC 2000, LC4 104, LPLC2 210, MBON 96, ORN 500, PN 300, SEZ-GRN 700, T2/T3-vis 800)
DN_named: DNpe017x2 [720575940629866283, 720575940631925156] + DNp20x2 + DNp09x2 + DNa01x2 + DNa02x2 + GFx2 = named 12 + generic DN* x138 from 1300 → total DN = 150 <= 150. HONORED.
```

## 3. ffmpeg single-command — PASS (exactly ONE encode)
Command:
```
grep -rn "ffmpeg" tools/ docs/ out/*.md | head  → 6 lines, all mentions/logs (failures.md x3, tldr_check.md x2+1); zero encode invocations in tools/ or docs/
grep -rn "ffmpeg -y" tools/ docs/ out/ arena/ → encode_count=1:
out/fail_ffmpeg.log:25: ffmpeg -y -framerate 30 -i out/frames/f%05d.png -framerate 30 -i out/spikes/sp%05d.png -filter_complex hstack -c:v libx264 -crf 23 -pix_fmt yuv420p out/trophy_hunt.mp4
```
Exactly the scope hstack command, unaltered flags. No second encode command. No REJECT trigger.

## 4. Stub/TODO/placeholder scan — PASS (documented fallbacks, no stub code)
Commands:
```
grep -rn "TODO\|FIXME\|HACK\|XXX\|placeholder" tools/ | head -n 20 → 3 lines, ALL in tools/select_circuit.py:
  :24  Edges/weights are SYNTHETIC placeholders drawn from the same
  :67  MEAN_FANOUT = 40  # synthetic edge placeholder density (matches docs/budget.md)
  :295 # Synthetic placeholder edges (chunked 100k guard), same RNG stream
grep -rn "TODO\|FIXME\|HACK\|XXX" tools/ → empty (exit 1). Zero strict markers.
grep -rni "stub" tools/ → only anti-stub comments in check_bridge.py ("never stubbed", "no stubbing", "vendor NOT stubbed") + 1 .pyc binary self-match. No stub code.
```
Assessment: `placeholder` hits are honest synthetic edge fallbacks (parquet unreadable without pyarrow, recorded in out/circuit.json sampling_notes + inherited wisdom), NOT fail-open stubs. Fail-closed messages present by design: `analytic(mujoco-missing)`, `synthetic(mujoco-missing)`, `declared-not-installed`, `not-triggered` notes, quoted `ModuleNotFoundError`s. No REJECT trigger.

## 5. Bare-except scan — PASS (zero)
Command: `grep -rn "except:" tools/*.py` → empty (exit 1). Zero bare excepts.

## 6. py_compile — PASS
Command: `python3 -m py_compile tools/*.py` → `PYCOMPILE_OK` (all 12 tools/*.py).

## 7. Hardcoded-value review — PASS (frozen plan params as named constants)
Spot check `tools/check_shot.py`: `THRESHOLD=3`, `HYSTERESIS=2` (re-arm `<=THRESHOLD-HYSTERESIS=1`), `AMMO_MAX=5`, `COOLDOWN_MS=500`, plus range=20.0m/spread=0.02rad/seed=1 in controller — all match plan Scope line 11 / Task 9 freeze. Values are intentional frozen params with docstring provenance, not magic-number defects.

## 8. Scope Must-NOT audit — PASS (all clean)
- `grep -rli "realtime\|narration\|audio" tools/ arena/ docs/` → empty (exit 1). No realtime viz, narration, or audio.
- New fly bodies: `arena/hunt_arena.xml` has NO fly body — `fly_spawn_0` is a `<site>` marker only (lines 6-11 comment + line 76); real body composed at runtime via `fly-brain/two_flies.py Fly(...)` (NeuroMechFly untouched). Only bodies: `moose_box` + mocap `looming_sphere`.
- `grep -rn "urllib\|requests\|socket\|wget\|curl" tools/*.py` → empty (exit 1). No network-after-fetch in tooling.

## F2 VERDICT: APPROVE
Rule check: secrets empty ✓ + DN<=150 (150 exact, analytic refs) ✓ + single ffmpeg hstack ✓ + py_compile clean ✓ + no stubs/bare-except (strict TODO set empty; placeholders are documented synthetic fallbacks) ✓ + Must-NOT clean ✓. No implementation files modified by this review.
