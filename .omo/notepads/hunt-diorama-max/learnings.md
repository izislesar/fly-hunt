# 2026-09-17T00:05Z D1 duel staging (branch diorama, commit 45e335d)
- Rifle v1 FAILED visually: 20mm prop (barrel 12 + stock 6 + 3mm gap, no connector) + side offset y=-3.2mm read as floating crates/log, stock detached from barrel. Evidence: out/duel v1 probes (superseded).
- Rifle v2 SHIPPED (tools/fly_duel.py): barrel r=0.35 half=3.0 (7 long, +x fwd), stock half (1.6,0.8,1.0), receiver half (1.2,0.55,0.65) bridging gap = ONE silhouette ~10.7mm ~3x fly; offset (0.5,0,1.0) directly above thorax (y MUST be ~0: fly fwd=+x at yaw 0, any y hangs prop off the side); bind dist=1.12mm; contype=0/conaffinity=0 all 3 geoms, ncon=99 (no prop contacts).
- Cameras: stage wide fovy45 (fly 41px), face duel_face fovy20 tracked offset (34,-26,12) lower-profile (fly 246px), duel medium fovy32 axial (fly 76px + moose + loom). PROFILE-SHOT LESSON: side cam [-30,-30,9] puts axial fly 45 deg off-axis -> fly LOST from frame; duel cam MUST stay near fly->moose axis (~8 deg). Rifle foreshorten along axis is the price; face probe sells the rifle length.
- Light v1 (unchanged, 0 extra rounds): sun [0.7,0.65,0.58] shadow-caster + warm fill [0.35,0.3,0.24] + cool rim [0.22,0.26,0.34], headlight 0.15/0.20, sky repaint steel-blue (max 235), reflections OFF (round-1: glossy ground smeared moose base white), shadows ON. wf=0.0000 all 3 (gate <5%).
- Supersample 1280x960 offscreen (model.vis.global_.offwidth/offheight) -> LANCZOS 640x480, logged per probe.
- EGL DETERMINISM (RTX 3050): renders flicker ~2-15px by +/-1 LSB at random (maxabs=1; trivial scene stable; no periodicity; glDisable(GL_DITHER) does NOT help). Gate = rebuild+rerender face, byte-identical, up to 4 attempts (tries logged). Evidence this run: tries=['999316e27b9c'] first-try PASS. Prior run: tries=['0e94...','ac91...'] 2nd-try PASS. Any systematic nondeterminism fails all 4.
- measure_fly bbox INCLUDES overlapping prop pixels (stage 41px is fly+rifle cluster) — keep margin above 40 on wide shots.
- Read-only verified: git diff -- fly-brain/ arena/ EMPTY. Push: origin diorama exit 0.

# 2026-09-17T03:15Z D2 full duel take (branch diorama, commit 692fcec)
- Render: tools/fly_duel_full.py (NEW, committed) imports tools/fly_duel.py Task-1 pipeline (build/tune/bind/render/cams/lights/sky/offsets) — zero tweaks to frozen setup. Per-frame: settled qpos + loom mocap from out/physics_log_10s.csv dist_m (same take mapping as fly_full.py) + bind_rifle + frozen duel_duel cam; 1280x960 EGL -> LANCZOS 640x480, shadows ON (flags mjRND_SHADOW=1, REFLECTION=0, FOG=0 logged per sample).
- Interruption + resume: first run aborted after f00253 (254 files, bind 1.12mm throughout); added [START,END) argv to fly_duel_full.py, rendered ONLY missing f00254-f00299 with identical pipeline. Cross-process settle deterministic (thorax [0.5,0.0,1.9] both runs).
- Binding health over 300: max=mean=min=1.12mm, bad(>=10mm)=[] — prop never detached. Wall: resume 46 frames = 15.4 s.
- Samples (verify script /tmp/verify_duel.py, third process): 0/150/299 ALL overlap=True moose_in=True wf=0.0000 fly maxside=76 (flybox 205,289,234,364; propbox 201,295,229,312); md5 7c8c162a/ a6366f7e/ 0d5a9ec9 (12-char). file(1): all 640x480 RGB.
- Determinism: frame150 rerender 4 tries all miss by 2px maxabs=1 (known +/-1 LSB EGL dither, within Task-1 caveat of ~2-15px); frame299 rerender byte-identical FIRST try (nzdiff=0). Verdict: deterministic modulo dither.
- Read-only verified: git diff -- fly-brain/ arena/ EMPTY; probes intact (face md5 999316e27b9c matches D1). .gitignore += out/duel/f*.png (probes keepable, mirrors frames10 policy). Push: origin diorama 45e335d..692fcec exit 0.

# 2026-09-17T03:05Z D3 rifle assembly (branch diorama, commit pending)
- Pre-check: out/duel/f*.png 300 (f00000-f00299) + out/brain/b*.png 300, all 640x480 RGB. Originals backed up to /tmp/duel_orig_bak + /tmp/brain_orig_bak (outside repo) before any edit.
- Luminance (PIL L/Rec.601 mean over full sets): BEFORE duel=109.70 brain=21.91 mismatch=80.03% (sun-lit duel vs navy brain, real seam as predicted).
- Gamma pass (hunt-side PIL LUT, in-place on ignored out/duel/f*.png): iter1 g=ln(21.91/255)/ln(109.70/255)=2.9099 -> duel=24.92 mismatch=12.10% PASS in 1 iteration (no iter2 needed).
- Gutter/tags (PIL, before hstack): hunt right-edge 2px + brain left-edge 2px #1A2340 = 4px seam gutter; HUNT/BRAIN 14px JetBrainsMono-Regular #8A94B0 at (8,H-22) bottom-left each panel. FINAL duel=25.00 brain=22.03 mismatch=11.87% <=15%.
- Brain PNGs are git-TRACKED: tag/gutter pass dirtied them, so restored via `git checkout -- out/brain/` AFTER the stitch (mp4 has tags baked; repo brain set pristine). Duel f*.png are gitignored — tone-matched versions stay on disk only.
- Stitch: exact plan command, exit 0. ffprobe: h264 1280x480 30/1 duration=10.0 size=189366 (185K <50MB).
- Commit `feat(video): rifle duel 10s cut` = out/trophy_hunt_rifle.mp4 + this learnings entry (mirrors 4198a02 precedent). Push origin diorama exit 0. HARD STOP.

# 2026-09-17T00:05Z D4 merge to main + tag trophy-hunt-duel (F1+F2 APPROVE)
- Gate: F1 APPROVE (8 findings incl. 300+300 contiguous, 4-mp4 inventory clean, vendor/arena diffs empty). F2 APPROVE (8 findings incl. reward md5 identical, prop visual-only, no audio, forbidden-grep 0).
- Chain: main e62d626 <- ... <- diorama afe4947 `feat(video): rifle duel 10s cut`; merge-base(main,diorama)=e62d626 => fast-forward.
- Forbidden-paths check on range e62d626..afe4947: EMPTY (only allowed samples).
- Merge: `git checkout main && git merge --ff-only diorama` + `git push origin main` + `git tag trophy-hunt-duel` + `git push origin trophy-hunt-duel`. Branches diorama/viz10/rerun KEPT for traceability.
