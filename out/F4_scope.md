# F4. Scope fidelity — VERDICT: APPROVE

Checkbox: `F4. Scope fidelity - expect ls out/trophy_hunt.mp4 only video + grep -ri "realtime\|narration\|audio" src | wc -l == 0 + N 4000-6500`

Date: 2026-09-16. Auditor role: FINAL-WAVE REVIEWER, audit-only (no implementation files touched).

## 0. Layout mapping (plan says `src`, repo uses tools/+arena/+docs/+out)

Plan F4 line references `src`, but the repo has NO `src/` directory. Actual layout (verified `ls /home/izislesar/Projects/fly_oxota`):

```
arena/  data/  docs/  fly-brain/  out/  tools/  DATA_FETCH.md  pins.md  environment.yml
```

Honest mapping applied: `src` ≡ `tools/ + arena/ + docs/` (all first-party code/docs). `fly-brain/` is a pinned vendor copy (read-only, SHA 27cec28d); `data/` holds v783 blobs; `out/` holds frames/spikes/video/logs. All forbidden-content greps below were run against `tools/ arena/ docs/ out/*.md` and quoted verbatim.

## 1. Single-video proof

Command:
```
$ ls out/*.mp4
out/trophy_hunt.mp4
---exit:0
```
Result: exactly ONE line — PASS. No stray mp4 (`find out -maxdepth 1 -name "*.mp4"` → only `out/trophy_hunt.mp4`).

Frames / spikes / stray PNGs:
```
$ ls out/frames | wc -l            → 90
$ ls out/frames | head -5          → f00000.png … f00004.png (f%05d, start 0)
$ ls out/spikes | wc -l            → 90  (sp00000..sp00089)
$ ls out/frames/ | grep -v "^f[0-9]*\.png$" → (no output — all names standard)
$ ls out/*.png                     → zsh:1: no matches found: out/*.png (EXIT 1 — no loose PNG deliverables at out/ root)
```
`out/frames` (Task 12 owns, 90) contains only `f*.png`; spike PNGs live in `out/spikes/` (90, Task 14 owns). No extra videos. — PASS.

Parquet commit-strategy note: `du -sh data/*.parquet` → `97M data/2025_Connectivity_783.parquet` (present on disk, must stay uncommitted per plan Commit strategy). `git status` → `fatal: not a git repository (or any parent up to mount point /)` — workdir has NO git repo, so "uncommitted" holds vacuously; recorded honestly, no commit performed. — PASS (informational).

## 2. Forbidden-content greps (quote empties verbatim)

```
$ grep -rli "realtime\|real-time\|narration\|audio\|slow-mo\|slowmo" tools/ arena/ docs/ out/*.md
(no output, exit 1)
```
— PASS: zero hits, no audio/titles/slow-mo/narration content. No benign-mention disambiguation needed (nothing to quote).

```
$ grep -rli "weapon\|gun\|rifle" tools/ arena/ docs/
(no output, exit 1)
```
— PASS: no real-weapon content. Shot language is fantasy raycast-analytic only; params quoted from `tools/check_shot.py`:
```
Frozen params: threshold=3 spikes/10ms bin on DNpe017, hysteresis=2,
ammo=5, range=20.0m, cooldown=500ms, spread=0.02rad raycast cone.
THRESHOLD = 3          # spikes per 10ms bin on DNpe017
```
No mujoco needed for the shot model; no weapon instructions. — PASS.

```
$ grep -rli "urllib\|requests\|socket\|http" tools/*.py
(no output, exit 1 → NET_EXIT:1)
```
— PASS: no network-after-fetch in tools (offline-after-fetch holds; network was Task 4 only).

```
$ grep -rli "matplotlib.*anim\|FuncAnimation\|imshow.*pause\|plt.show\|cv2.imshow" tools/
(no output, exit 1 → RTVIZ_EXIT:1)
```
— PASS: no realtime spike-viz path; spike PNGs are offline (PIL/magma, Task 14).

## 3. N bounds (live check)

```
$ python3 -c "import numpy as np,json; d=np.load('data/hunting_circuit_6k.npz',allow_pickle=False); ..."
N= 5500
keys= ['neuron_ids', 'neuron_types', 'cell_type_detail', 'edges', 'weights_init', 'meta_json']
in_bounds= True
$ cat out/circuit.json → "N": 5500, "n_syn": 219965
```
N=5500 ∈ [4000,6500] — PASS.

## 4. Per-item Must-NOT verdicts (plan OUT section, line 17)

| # | Must-NOT item | Evidence | Verdict |
|---|---|---|---|
| 1 | Full 138k/15M on GPU | N=5500 CPU (Brian2 priority), syn=219965 (~220k, fan-out 40), RSS_est 1.5022GB <8GB, VRAM proj 0.1525GB <3.5GB (`out/circuit.json`, `out/budget.json`) | PASS |
| 2 | Realtime spike viz | Offline PNGs only: 90× `out/spikes/sp%05d.png` 640×480 magma + 90× `out/frames/f%05d.png`; no anim/imshow realtime path (grep empty, RTVIZ_EXIT:1) | PASS |
| 3 | New fly XML bodies | `arena/hunt_arena.xml`: fly is a site marker only — `fly_spawn_0` is `<site …/>`, NOT a body; comment quotes `Fly(name=…, spawn_pos=…)` runtime composition via `fly-brain/two_flies.py`, NeuroMechFly untouched | PASS |
| 4 | Audio/titles/slow-mo/narration | Forbidden grep empty `(no output, exit 1)` across tools/+arena/+docs/+out/*.md | PASS |
| 5 | Real weapon / instructions | Weapon grep empty `(no output, exit 1)`; shot is raycast analytic with frozen params quoted above (threshold3/hyst2/ammo5/range20/cooldown500/spread0.02) | PASS |
| 6 | DN beyond 150 | `out/circuit.json` per_type_counts DN=150 exactly (named 12: DNpe017×2, DNp20×2, GF×2, DNa01×2, DNa02×2, DNp09×2 + generic 138) | PASS |
| 7 | Full-weight retrain | Closed-form KC→MBON only: `dW=1e-4*r_i*r_j-1e-7*W`, clip W [0,2], dopamine amp 0.8 dur 200ms PPL101→KC→MBON gate (`tools/reward.py` docstring + `out/reward.json` hebb dims `(96,32)`) | PASS |
| 8 | Network after fetch | `grep urllib\|requests\|socket\|http tools/*.py` empty `(no output, NET_EXIT:1)` | PASS |
| 9 | ffmpeg command change | Exact scope cmd used, from `out/fail_ffmpeg.log`: `ffmpeg -y -framerate 30 -i out/frames/f%05d.png -framerate 30 -i out/spikes/sp%05d.png -filter_complex hstack -c:v libx264 -crf 23 -pix_fmt yuv420p out/trophy_hunt.mp4` (exit 0, frame=90 encoded) | PASS |

Known honest deviations (from inherited wisdom, none violate Must-NOT): synthetic run path (mujoco/brian2 missing, documented in `out/run_meta.json` path=`synthetic(mujoco-missing)`), T5 synthetic edges (fan-out 40 placeholders, neuron IDs/types 100% real v783), bridge иначе-branch (`out/ADAPTATION.md`). No new fly bodies, no audio, no real weapon, no DN expansion, no full retrain, no network, exact ffmpeg cmd.

## 5. Success criteria cross-check

| Criterion | Check | Result |
|---|---|---|
| Video 1280x480@30 libx264 <50MB | `ffprobe … out/trophy_hunt.mp4` → `codec_name=h264, width=1280, height=480, r_frame_rate=30/1, duration=3.000000`; `ls -lh` → 47K (47555 B ≪ 50MB) | ✓ PASS |
| CSV 90 rows monotonic, ≥1 hit, reward>0, dW logged | `wc -l out/physics_log.csv` → 91 (header+90); `check_sync.py` → `PASS: 90 rows … monotonic`; hits=2 @frames 30,65; `out/run_meta.json` hits: frame30 reward 0.98 dW 1.96, frame65 reward 0.98 dW 1.90 | ✓ PASS |
| N/VRAM/RSS/sim-wall | N=5500 ∈ [4000,6500]; VRAM measured 0.0039GB / proj 0.1525GB <3.5; RSS VmHWM ≤0.034GB / proj 1.6484GB <14; sim/wall effective 6.0–13.0 ≥0.2 (`out/perf.md` ALL-PASS) | ✓ PASS |

## 6. VERDICT rule

APPROVE iff all Must-NOT items PASS + single video + N bounds + success criteria hold. All hold (9/9 Must-NOT PASS, 1 video, N=5500, 3/3 success criteria ✓).

```
F4 VERDICT: APPROVE
```

## 7. Verification commands + outputs (quoted)

- `ls out/*.mp4` → `out/trophy_hunt.mp4` (single line, exit 0)
- `grep -rli "realtime\|real-time\|narration\|audio\|slow-mo\|slowmo" tools/ arena/ docs/ out/*.md` → `(no output, exit 1)`
- `grep -rli "weapon\|gun\|rifle" tools/ arena/ docs/` → `(no output, exit 1)`
- `grep -rli "urllib\|requests\|socket\|http" tools/*.py` → `(no output, NET_EXIT:1)`
- `python3 -c "import numpy…"` → `N= 5500 … in_bounds= True`
- `ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,codec_name,duration -of default=nw=1 out/trophy_hunt.mp4` → `codec_name=h264 / width=1280 / height=480 / r_frame_rate=30/1 / duration=3.000000`
- `wc -l out/physics_log.csv` → `91`; `python3 tools/check_sync.py --csv out/physics_log.csv` → `PASS: 90 rows … monotonic`
- `du -sh data/*.parquet` → `97M data/2025_Connectivity_783.parquet`; `git status` → `fatal: not a git repository …` (no repo — nothing committed)

Audit-only: only this file (`out/F4_scope.md`) created + notepad append. No implementation files modified, no commits, no fixes.
