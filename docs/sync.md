# Triple-clock sync + CSV schema (Task 6, seed-schema-only)

> `seed-schema-only` — this CSV seed (3 rows) is REPLACEABLE.
> Task 12 overwrites `out/physics_log.csv` with the real 90-row run, not append.
> `tools/check_sync.py` validates both the 3-row seed and the final 90-row file.

## 1. Clocks

| Clock   | dt nominal | Rate    | Source                              |
|---------|------------|---------|-------------------------------------|
| neural  | 0.1 ms     | 10 kHz  | Brian2 SNN `dt_neural`              |
| physics | 0.5 ms     | 2 kHz   | MuJoCo `timestep 0.0005 s`          |
| frame   | 33.33 ms   | 30 fps  | video `640x480@30fps`, `1/30 s`     |

## 2. Ratio derivations

- **5 neural steps per physics step:** `0.1 ms x 5 = 0.5 ms`.
  Ratio neural:physics = 5:1. The neural integrator advances 5 sub-steps,
  then hands binned activity to one physics step.
- **66 physics steps ≈ 1 frame:** `66 x 0.5 ms = 33.0 ms` vs
  frame `1000/30 = 33.333... ms` (spec nominal `33.33 ms`).
  Residual `+0.33 ms/frame` (≈ +0.333 ms exact).
  **Residual policy: accumulate-and-correct every frame** — keep a running
  residual accumulator; when it exceeds one physics dt (0.5 ms, i.e. every
  ~2 frames given 0.33 ms/frame drift... in practice every 2nd frame),
  insert one extra physics step (67 instead of 66) and subtract 0.5 ms from
  the accumulator. Nominal log text stays `66 phys/frame`; corrected frames
  are still frame-aligned via `frame_id * 33.33 ms`. The checker therefore
  validates `t_neural ≈ t_physics * 1000` and `t_neural ≈ frame_id * 33.33`
  with ±1.0 ms tolerance instead of exact equality.
- **Frame mapping (nominal):**
  `t_neural_ms(frame) = frame_id * 33.33`,
  `t_physics_s(frame) = frame_id * 0.03333`.

## 3. Spike bin 10 ms -> frame aggregation rule

- Neural spikes are binned at **10 ms** (`r = binned rate in Hz`).
- One frame (33.33 ms) holds **≈3.33 bins** → aggregation rule:
  **3 full 10-ms bins per frame + every 3rd frame absorbs a 4th partial bin**
  (alternatively: sum bin rates overlapping `[frame*33.33, (frame+1)*33.33)`).
  `spike_count` in the CSV is the integer sum of spikes in that frame window.
- `out/spikes.npz` keeps the full 10 ms raster (`300 bins` for 3 s);
  the CSV keeps only the per-frame aggregate.

## 4. CSV schema

Header (EXACT, do not rename):

```
t_neural:float ms,t_physics:float s,frame_id:int,spike_count:int,moose_pos:float[3],hit_bool:int
```

| Column            | Type       | Unit | Meaning                              |
|-------------------|------------|------|--------------------------------------|
| `t_neural`        | float      | ms   | neural time, `frame_id * 33.33` nom. |
| `t_physics`       | float      | s    | physics time, `frame_id * 0.03333`   |
| `frame_id`        | int        | —    | 0-based frame index, strictly +1     |
| `spike_count`     | int        | —    | spikes aggregated in frame window    |
| `moose_pos`       | float[3]   | m    | moose-box xyz in meters, see §5      |
| `hit_bool`        | int        | {0,1}| shot hit flag for this frame       |

Units per column are part of the header suffixes (`ms`, `s`, `int`,
`float[3]`) and the table above.

## 5. `moose_pos` serialization choice

- **Chosen: `x;y;z`** (semicolon-separated floats inside one CSV field,
  e.g. `12.5;0.0;3.2`).
- Rationale: preserves **exactly 6 CSV columns per row**. Space-separated
  `x y z` would also stay in one field only if quoted; comma-separated would
  break the column count. `;` is unambiguous and needs no quoting.
- `tools/check_sync.py` enforces: every row has **6 columns**, and `moose_pos`
  splits on `;` into exactly 3 parseable floats.

## 6. Monotonicity guarantee

- Writer contract: rows are appended in increasing `frame_id` order;
  `t_neural`, `t_physics`, and `frame_id` are **strictly increasing**
  row-over-row. No reordering, no duplicate frames, no time going backwards.
- `tools/check_sync.py --csv out/physics_log.csv` enforces this and exits
  non-zero + writes `out/fail_sync.log` with the offending row on violation.
  On PASS it (re)writes `out/fail_sync.log` as a not-triggered note so the
  Task 17 failure-gate sees a clean record.

## 7. Seed rows (replaceable)

`out/physics_log.csv` currently holds the header + 3 demonstrative rows
(`frame_id` 0..2, frame-aligned times, strictly monotonic) so Task 12 has a
schema to overwrite with 90 real rows.

## 8. QA

- Happy: `python tools/check_sync.py --csv out/physics_log.csv` → `PASS`, exit 0.
- Fail: non-monotonic edit → `FAIL` + `out/fail_sync.log` names the row.
- Commit (DO NOT COMMIT per task card): `feat(sync): freeze triple-clock + csv schema`
