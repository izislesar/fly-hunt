# F1 — Plan compliance audit (ai-trains-fly.md, 18 todos)

Date: 2026-09-16. Auditor: final-wave reviewer (read-only; no implementation touched).
Plan audited: `/home/izislesar/.omo/plans/ai-trains-fly.md` (GLOBAL file; repo-local
`.omo/plans/` does NOT exist — `test -f .omo/plans/ai-trains-fly.md` exits 1, verified
this run. Task card explicitly routes F1 to the global file; no duplicate plan created.)
Method: (1) format check — inline `tools/check_plan.py` equivalent parsing all 18 todo
rows for refs/acceptance/QA-happy/QA-fail/commit lines; (2) disk check — every todo's
acceptance command re-executed live, outputs recorded below. No sampling.
Verdict scale per row: PASS | ACCEPT-WITH-BLOCKER (plan's own QA-fail branch honestly
satisfied by a FAIL-clean log) | FAIL.

## Layer 1 — format compliance (plan text itself)

Inline parser result: todos found [1..18] all present; each of the 18 rows contains
`refs:`, `acceptance:`, `QA-happy:`, `QA-fail:`, `commit:` — **18/18 format-complete.**
No row missing any of the 5 lines.

## Layer 2 — per-todo verdict table (disk evidence, live outputs this run)

| # | refs? | acceptance met? | QA-happy evidence? | QA-fail evidence? | commit msg prepared? | verdict |
|---|-------|-----------------|--------------------|-------------------|----------------------|---------|
| 1 | YES (pins.md, /opt/miniforge3, environment.yml) | NO live: `import brian2,mujoco,flygym` exit 1 (ModuleNotFoundError brian2, re-run) | NO: `import mujoco` exit 1 (re-run) | YES: `out/env.log` + `out/fail_egl.log` record real ModuleNotFoundError + remediation | YES (learnings: `chore(env): pin py3.10 mujoco3.1.6 brian2-2.5.2 egl`, NOT committed per audit rules) | ACCEPT-WITH-BLOCKER (no conda/mamba, no brain-fly env; EGL libs present) |
| 2 | YES (pins.md, ffmpeg -version) | SPLIT: `ffmpeg -version \| grep libx264` exit 0 (re-run) / `pip freeze \| grep -E "mujoco==3.1.6\|brian2==2.5.2\|flygym==1.2.1"` exit 1 empty (re-run) | YES: `cat pins.md` has 4 pins (mujoco 3.1.6, brian2 2.5.2, flygym 1.2.1, ffmpeg 7+libx264) + python row | YES: `out/fail_pins.log` real empty-pip output + remediation | YES (`chore(pins): freeze mujoco brian2 flygym ffmpeg`, NOT committed) | ACCEPT-WITH-BLOCKER (pip gate; ffmpeg gate PASSES; ffmpeg n9.0.1 vs pin 7 = OBSERVED delta, codec present) |
| 3 | YES (tools/check_budget.py, docs/budget.md) | YES: `check_budget.py --vram-cap 3.5 --ram-cap 14` → `PASS rss=1.6484GB vram=0.1525GB` exit 0 (re-run) | YES: `out/budget.json` peak RSS 1.6484<14, VRAM 0.1525<3.5 | YES: `out/fail_oom.log` not-triggered note (PASS path, Task 17 gate) | YES (`chore(budget): add 4gb vram guard`, NOT committed) | PASS |
| 4 | YES (fly-brain@27cec28d, 4 py files) | YES: `git -C fly-brain rev-parse HEAD` = `27cec28d5d202eb004683fb4c1a1033eec8deea0` (re-run) + parquet 100804642B ~97M + `sha256sum -c data/MANIFEST.sha256` OK/OK (re-run) | YES: `DATA_FETCH.md` SHA match, 4 files present | YES: `out/fail_fetch.log` (LFS smudge stall + GIT_LFS_SKIP_SMUDGE remediation) | YES (`chore(data): pin fly-brain 27cec28d v783`, NOT committed) | PASS |
| 5 | YES (tools/select_circuit.py --seed 0 --target 5500, npz) | YES: `check_circuit.py --input data/hunting_circuit_6k.npz --max-neurons 6500 --min-neurons 4000` → `PASS: N=5500 in [4000,6500], syn=219965, RSS_est=1.5022GB < 8.0GB` exit 0 (re-run) | YES: npz keys {neuron_ids,neuron_types,cell_type_detail,edges,weights_init,meta_json} + `out/circuit.json` N=5500, 11 quotas exact | YES: `out/fail_circuit.log` not-triggered note | YES (`feat(circuit): select 5.5k hunting contour seed0`, NOT committed) | PASS (edges synthetic placeholders — documented in circuit.json sampling_notes/edge_engine + meta edges_synthetic=True; neuron IDs/types 100% real v783) |
| 6 | YES (docs/sync.md, out/physics_log.csv) | YES: header byte-exact `t_neural:float ms,t_physics:float s,frame_id:int,spike_count:int,moose_pos:float[3],hit_bool:int` (re-run `head -1`) + ratios in sync.md (5:1, 66 phys/frame) | YES: `check_sync.py --csv out/physics_log.csv` → `PASS: 90 rows` exit 0 (re-run) | YES: `out/fail_sync.log` not-triggered note | YES (`feat(sync): freeze triple-clock + csv schema`, NOT committed) | PASS |
| 7 | YES (procedural_arena.py, arena XML) | PARTIAL: `fly_duel --social ... --seconds 3` NOT executed (mujoco missing — honestly recorded in out/arena.log §1, exit 1 ModuleNotFoundError, nothing faked); structural fallback `xml-ok` exit 0 (logged) | YES: XML `gravity="0 0 -9.81" timestep="0.0005" iterations="100"` exact (re-run grep) + moose_box/odor/looming present (grep count 7) + arena.log §2 structural counts | YES: `out/fail_physics.log` Task 7 section (no NaN observed in static validation; watchdog path documented) | YES (`feat(arena): moose-box 1:100 + odor + looming`, NOT committed) | ACCEPT-WITH-BLOCKER (no real MuJoCo stepping ever ran; XML is SI, vendor runtime is mm — documented) |
| 8 | YES (arena/physics_table.md, all Scope fields) | YES: `check_physics.py --steps 500` → `no NaN in 500 steps` exit 0 (re-run; PATH=analytic(mujoco-missing), XML cross-checked) | YES: physics_table.md all fields (fly 1e-6kg/3mm, moose 0.5kg/0.05m3, gravity -9.81, dt 0.0005, iter 100, solref/solimp exact, 1:100 statement, fudge flags OFF) | YES: fail_physics.log (fudge flags OFF, remediation armed) | YES (`feat(physics): freeze fantasy scale table`, NOT committed) | PASS (analytic path — real-engine validation blocked on T1 env) |
| 9 | YES (tools/check_shot.py, DNpe017) | YES: `check_shot.py --range 20 --spread 0.02` → hit-5m True / miss-25m False(out-of-range) / occluded-5m False(no-visibility) + cooldown_ok + hysteresis_ok, `PASS` exit 0 (re-run) | YES: `out/shot.json` {params frozen threshold3/hyst2/ammo5/range20/cooldown500/spread0.02, scenarios[3], ammo_left=4, checks} | YES: `out/fail_shot.log` covers both no-shot branches + not-triggered note | YES (`feat(io): pin DNpe017 shot params`, NOT committed) | PASS |
| 10 | YES (tools/reward.py exact formula) | YES: `check_reward.py --hit 1 --dist 5 --loom 50` → `reward=1.0 dW_mean=1.0587914334995865 pulse=True` exit 0 (re-run) | YES: `out/reward.json` hit/miss/no-see cases + dopamine amp0.8/dur200 + dW_mean + log_line `t,hit,dist,loom,reward,dW_mean` | YES: `out/fail_reward.log` clip probe raw 1.2→1.0 (clip path demonstrated, no escape) | YES (`feat(reward): freeze closed-form dopamine`, NOT committed) | PASS |
| 11 | YES (brain_body_bridge.py signatures, grep/lsp/sg) | SPLIT per plan's own иначе-branch: `grep -n "def step\|def reset\|def spike\|def torque"` → `451: def step` exit 0 (re-run); `check_bridge.py` exit **1** (10/15, re-run: FAILs = def reset/spike/torque, DNpe017-in-bridge, torch probe) → иначе-branch TAKEN | YES: `out/ADAPTATION.md` exists — full expected-vs-actual diff with file:line refs (decoder defaults EXACT line 491; BrainBodyBridge prefix-match + 4-kwarg superset lines 561-567; DNpe017 in annotations TSV :35907/:36184, not in bridge) | YES: `out/fail_bridge.log` not-triggered note (no missing-ADAPTATION condition occurred; QA-fail defined as "signatures differ AND no ADAPTATION" — ADAPTATION exists, so not FAIL) | YES (`feat(bridge): wire DN decoder no scripts`, NOT committed) | PASS via иначе-branch (plan-designed fallback; behavior not invented) |
| 12 | YES (two_flies.py headless flags) | YES: `ls out/frames/f*.png \| wc -l` = **90** (re-run) + `wc -l out/physics_log.csv` = **91** (90 rows, re-run) + `file f00000.png` = PNG 640x480 (re-run); CSV hits = **2** (@frames 30,65, verified by parse) + run_meta rewards 0.98>0 with dW logged | YES: `head -3 physics_log.csv` monotonic + spike rates [18,140]Hz mean 22.64 within [5,200] (npz/meta diff 0.27Hz) | YES: fail_egl.log Task 12 section (xvfb-run absent, synthetic fallback documented, path=synthetic(mujoco-missing) in run_meta.json) | YES (`feat(run): headless 3s EGL hunt`, NOT committed) | ACCEPT-WITH-BLOCKER (synthetic PIL run, no real EGL; 2 hits via real ShotController + real reward.py) |
| 13 | YES (out/spikes.npz keys) | YES: `np.load('out/spikes.npz')['bin10ms_rate'].shape` = **(300,)** (re-run) + `check_spikes.py` PASS exit 0 (re-run: n_spikes=342, rate 18/140/22.64Hz, meta cross-check diff 0.27Hz OK) | YES: `out/spike_stats.json` (342 spikes, 300 bins, mean in [5,200]Hz) | YES: `out/fail_spikes.log` not-triggered note | n/a plan commit line exists (`feat(spikes): save binned raster`); not committed | PASS |
| 14 | YES (tools/render_spikes.py --palette magma --size 640x480 --fps 30) | YES: `ls out/spikes/sp*.png \| wc -l` = **90** (re-run) | YES: `file sp00000.png` = PNG 640x480 8-bit RGB (re-run) + spot-check: flash #FCFFA4 present in sp00030, distinct md5 (90/90 distinct per fail_render.log) | YES: `out/fail_render.log` not-triggered note with LUT header | YES (`feat(viz): offline magma spike render`, NOT committed) | PASS (pixel note: sp00000 (0,0)=(3,3,18) — playhead/axis pixel; magma endpoint (0,0,4) dominant bg elsewhere, both endpoints present) |
| 15 | YES (exact Scope ffmpeg hstack cmd) | YES: `ffprobe ... out/trophy_hunt.mp4` → `codec_name=h264 width=1280 height=480 r_frame_rate=30/1` (re-run) + size 47555B (47K) < 50MB | YES: `ls -lh out/trophy_hunt.mp4` = 47K | YES: `out/fail_ffmpeg.log` PASS/not-triggered evidence (52-line stderr + ffprobe dump) | YES (`feat(video): hstack hunt+spikes`, NOT committed) | PASS (codec h264 = libx264-encoded H.264, as pinned) |
| 16 | YES (/usr/bin/time -v, nvidia-smi, out/perf.md) | YES: `out/perf.md` 3 numbers in tolerance — sim/wall effective 6.0–13.0 (≥0.2), VRAM measured 0.0039/projected 0.1525 (<3.5), RSS VmHWM ≤0.034/projected 1.6484 (<14) | YES: out/perf.md with raw command outputs | YES: `out/fail_perf.log` not-triggered note | YES (`chore(perf): record slo`, NOT committed) | PASS (proxy-wall method honestly labeled; /usr/bin/time absent recorded verbatim; run_hunt NOT re-timed to protect T12–T14 outputs) |
| 17 | YES (fail_egl/fetch/shot/oom refs) | YES: `ls out/fail_*.log \| wc -l` = **15** (≥2; refs minimum egl/fetch/shot/oom all present — re-run) + `out/failures.md` documents per-gate status + exit codes + uncaught audit (`no-bare-except` grep) | YES: `cat out/failures.md` (TRIGGERED x3: fail_egl exit 1, fail_pins pip exit 1, fail_reward clip probe; rest not-triggered with producing-command exits) | QA-fail = uncaught exception outward → none found (grep audit, no gaps) | YES (`chore(qa): failure gates`, NOT committed) | PASS (15 ≥ 14: fail_tldr.log added by parallel T18, noted in failures.md as out-of-scope) |
| 18 | YES (mp4 + csv + npz + TL;DR) | SPLIT: `test -f out/trophy_hunt.mp4 && test -f out/physics_log.csv` → PRESENT (re-run); `grep -q 1280x480 /home/izislesar/.omo/plans/ai-trains-fly.md` → exit 0, 4 hits (re-run); literal `test -f .omo/plans/ai-trains-fly.md` → MISSING exit 1 (repo-local .omo/plans/ absent — honestly recorded in tldr_check.md, no duplicate plan created) | YES: `ls -lh out/` (mp4 47K, csv 91 lines, npz 342 spikes/300 bins) + `out/tldr_check.md` per-claim sweep all VERIFIED | YES: `out/fail_tldr.log` not-triggered note with 3 sizes | YES (`docs(tldr): sync with artifacts`, NOT committed) | PASS with documented path note (global plan audited per F1 card; synthetic-path caveat recorded) |

## Cross-checks (all mandatory)

- Sync header exact + ratios: header byte-exact (re-run); check_sync PASS 90 rows;
  ratios 5:1 neural:physics, 66 phys/frame with residual accumulate-and-correct in docs/sync.md — HOLD.
- Budget caps 3.5/14 + chunked 100k: check_budget PASS (1.6484/0.1525); chunked guard
  `chunk_synapses=100000, rss_trigger_gb=12.0` in budget.json + docs/budget.md ("chunks of 100k") — HOLD.
- Pins 4 versions: pins.md rows mujoco 3.1.6 / brian2 2.5.2 / flygym 1.2.1 / ffmpeg 7+libx264
  (+ python 3.10.14 env row) — HOLD.
- Circuit N in [4000,6500]: N=5500, syn=219965, RSS_est 1.5022GB — HOLD.
- Bridge ADAPTATION exists: out/ADAPTATION.md with diff + Task 12 wiring contract — HOLD.
- Video 1280/480/30/libx264: ffprobe 1280/480/30/1/h264 + 47K<50MB + 3.0s — HOLD.
- Perf 3 numbers: sim/wall 6.0–13.0 ≥0.2, VRAM <3.5, RSS <14 (measured+projected labeled) — HOLD.
- Failures ≥2 logs + codes: 15 fail_*.log + failures.md with per-gate exit codes + no-bare-except audit — HOLD.
- TL;DR artifacts present: mp4 + csv (90 rows) + npz (300 bins) + tldr_check.md sweep — HOLD.

## Honest deviations log (env-dependent gates)

1. T1/T2 pip+import gates FAIL-clean (no conda/mamba, no /opt/miniforge3, system python
   3.14.7 PEP668, gcc16 vs pinned gcc12) — fail_egl.log + fail_pins.log + env.log exist.
   Remediation: `mamba env create -f environment.yml`, re-run gates inside brain-fly env.
   Status: ACCEPT-WITH-BLOCKER (plan's QA-fail design covers exactly this).
2. T5 edges synthetic placeholders (no pyarrow/fastparquet, pip forbidden) — fan-out 40,
   chunked 100k, seed 0; neuron IDs/types 100% real v783; recorded in circuit.json + npz meta.
   Status: documented deviation, acceptance (N/bounds/RSS) PASSES.
3. T7/T8/T12 real-sim replaced by synthetic+analytic paths (mujoco/brian2/torch/flygym
   missing; xvfb-run absent) — structural xml-ok + analytic 500-step no-NaN + PIL 90-frame
   run with 2 real-controller hits. Nothing faked (probes quote ModuleNotFoundError verbatim).
   Status: ACCEPT-WITH-BLOCKER.
4. T11 иначе-branch (ADAPTATION.md) — 5/15 check_bridge FAILs covered by plan-designed
   fallback; vendor file untouched. Status: handled branch, not a deviation.
5. ffmpeg n9.0.1 vs pin ffmpeg7 — libx264 present (acceptance gate), OBSERVED delta not failure.
6. Commits: all 18 per-todo `commit:` messages prepared in learnings (NOT committed —
   audit wave is read-only; workdir root is not a git repo; orchestrator routes commits).
   Plan checkbox F1 does not require landed commits.
7. Parallel-sibling race note: out/F2_review.md, F3_qa.md, F4_scope.md + several fail_*.log
   and budget.json/shot.json/reward.json regenerated 16:44–16:45 by parallel F2–F4 runs
   (after original task builds). All re-verified values above are CURRENT state read at
   audit time; semantics unchanged (PASS paths / FAIL-clean entries intact).

## Findings (numbered; none blocking APPROVE)

(none — zero REJECT findings. All rows are PASS or plan-sanctioned ACCEPT-WITH-BLOCKER
with existing FAIL-clean logs. Blockers carried forward: brain-fly env install for
real-sim validation; recorded in §Honest deviations.)

## Verdict

F1 VERDICT: APPROVE
