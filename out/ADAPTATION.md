# ADAPTATION — Task 11 Bridge (иначе-branch, `out/ADAPTATION.md`)

Date: 2026-09-16. Vendor file (read-only, NEVER edited):
`fly-brain/brain_body_bridge.py` (747 lines).
Checker: `tools/check_bridge.py` → 10/15 PASS, exit 1. This file is the
contract Task 12 reads. **Behavior is NOT invented below** — only the
expected-vs-actual diff plus exact file:line references.

## 1. Recorded acceptance evidence (real outputs)

- `grep -n "def step\|def reset\|def spike\|def torque" fly-brain/brain_body_bridge.py`
  → `451:    def step(self):`, exit 0 (only `step`; no `reset`/`spike`/`torque`).
- `grep -n "DNRateDecoder\|BrainBodyBridge\|DNpe017" fly-brain/brain_body_bridge.py`
  → `488:class DNRateDecoder:`, `558:class BrainBodyBridge:` (no DNpe017 hit).
- `grep -rn "DNpe017" fly-brain/` → found ONLY in
  `fly-brain/data/flywire_annotations.tsv:35907` and `:36184`
  (left/right DNpe017, FlyWire IDs 720575940629866283 / 720575940631925156).
  No hit inside `brain_body_bridge.py`.
- `which sg` → not installed (`sg not found`); ast-grep check NOT run,
  grep fallback used (recorded here per plan).
- `python3 tools/check_bridge.py` → exit 1 (10/15 PASS; 5 FAILs listed in §2).

## 2. Expected vs actual diff

| Expected (plan Scope/Task 11) | Actual (vendor, file:line) | Verdict |
|---|---|---|
| `DNRateDecoder(window_ms=50.0, dt_ms=0.1, max_rate=200.0)` | `def __init__(self, window_ms=50.0, dt_ms=0.1, max_rate=200.0):` line 491 | MATCH exact |
| `BrainBodyBridge(decoder, escape_threshold, groom_threshold)` | `def __init__(self, decoder,` line 561 + `escape_threshold=0.3, groom_threshold=0.02,` line 562, then `feeding_threshold=0.05,` line 563 + `escape_turn_gain=4.0,` line 564 + `tactile_escape_force=35.0,` line 565 + `sound_orientation_gain=0.3,` line 566 + `olfactory_attraction_gain=10.0` line 567 | MATCH as prefix; vendor is a SUPERSET (4 extra kwargs with defaults) |
| `def step` | `def step(self):` line 451 (`BrainEngine.step`, advances 0.1 ms, returns spike tensor) | MATCH (on BrainEngine, not on bridge/decoder) |
| `def reset` | absent (no exact `def reset`; nearest: `save_plastic_weights` line 400, `set_stimulus` line 407) | MISMATCH |
| `def spike` | absent as exact def (spike access is `get_dn_spikes` line 464, `get_population_spikes` line 475, `update(dn_spikes, pop_spikes=None)` line 511) | MISMATCH (name-level only) |
| `def torque` | absent (torque-level output is `compute_drive(dt=0.01)` line 609 → `np.array([left_drive, right_drive])` line 731) | MISMATCH (name-level only) |
| `sg -p "DNpe017"` found in bridge | sg missing; grep: DNpe017 NOT in bridge file, present in annotations TSV (above) | MISMATCH (bridge has no DNpe017-named DN; its DN set is P9/DNa01/DNa02/MDN/GF/aDN1/MN9, lines 37–63) |
| import + instantiate decoder with defaults | `ModuleNotFoundError: No module named 'torch'` (vendor imports torch + `run_pytorch` at lines 13/22; torch not installed on host) — AST/grep fallback used, vendor NOT stubbed | PROBE SKIP (honest) |

## 3. Signature dump (actual API Task 12 must wire)

- `DNRateDecoder.__init__(window_ms=50.0, dt_ms=0.1, max_rate=200.0)` (line 491):
  `window_steps = int(50.0/0.1) = 500`, `dt_s = 0.0001`, `max_rate = 200.0`.
- `DNRateDecoder.update(dn_spikes, pop_spikes=None)` (line 511),
  `get_rate(name)` (534), `get_normalized(name)` = rate/max_rate clipped to [0,1] (538),
  `get_group_rate(group_name)` (542), `get_pop_rate(name)` (549),
  `register_population(name)` (505).
- `BrainBodyBridge.__init__(decoder, escape_threshold=0.3, groom_threshold=0.02, feeding_threshold=0.05, escape_turn_gain=4.0, tactile_escape_force=35.0, sound_orientation_gain=0.3, olfactory_attraction_gain=10.0)` (lines 561–567).
- `BrainBodyBridge.compute_drive(dt=0.01)` (line 609) → `np.ndarray shape (2,)` (line 731).
- `BrainBodyBridge.get_status_str()` (line 733); mode hysteresis `_set_mode` (601), `_min_mode_dur = 0.3` s (583).
- `BrainEngine.step()` (line 451) is the only `def step`; there is no `reset`/`spike`/`torque` method to call.

## 4. Linear DN→joint statement (quoted projection, reference only)

Vendor maps normalized DN rates to `[left_drive, right_drive]` (consumed by
HybridTurningController → CPG → 42 joints, per module docstring lines 2–9).
Quoted lines 635/638–642/720–729:

- `forward = p9_drive + 0.5 * mn9_drive  # MN9 adds approach behavior` (line 635)
- `turn = turn_sustained + 0.5 * turn_transient` with
  `turn_sustained = DNa01_left - DNa01_right`,
  `turn_transient = DNa02_left - DNa02_right` (lines 638–642)
- `effective_turn = turn + sound_turn + olfactory_turn` (line 725)
- `left_drive = clip(forward * (1.0 + effective_turn) - backward, -0.5, 1.5)` (726–727)
- `right_drive = clip(forward * (1.0 - effective_turn) - backward, -0.5, 1.5)` (728–729)

No control policy, steering logic, or movement script was written for this
task — wiring is by API reference only.

## 5. Impact for Task 12 (run wiring)

1. Instantiate per §3 with defaults; do NOT call `reset`/`spike`/`torque` —
   those methods do not exist. Step the brain via `BrainEngine.step()`,
   feed `get_dn_spikes()` into `decoder.update(...)`, read
   `bridge.compute_drive(dt=0.01)`.
2. DNpe017 shot logic (Task 9: threshold 3 spikes/10 ms on DNpe017) CANNOT be
   sourced from `brain_body_bridge.py` — the bridge's DN set has no DNpe017
   entry. Source DNpe017 counts from the hunting-circuit NPZ
   (`data/hunting_circuit_6k.npz`, DN150 incl. DNpe017 x2) / Brian2 raster,
   not from the bridge decoder.
3. Extra `BrainBodyBridge` kwargs (feeding/thresholds/gains) keep defaults;
   do not retune — behavior preservation.
4. Import probe fails without torch (`ModuleNotFoundError: No module named
   'torch'`); Task 12 runs inside the brain-fly env where torch exists, or
   keeps AST-level wiring. Do not stub the vendor to fake a PASS.

## 6. Behavior-not-invented declaration

Where the vendor API differs from the plan's expected names
(`reset`/`spike`/`torque`, DNpe017 in bridge), NO substitute behavior was
invented and no behavioral script was written. Downstream Task 12 must follow
§3–§5 exactly. Mismatches are name-level; the functional path
DN spikes → rates → `[left_drive, right_drive]` exists verbatim in the vendor
file and is quoted, not paraphrased, in §4.
