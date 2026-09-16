# 2026-09-16T16:50Z — Task 1 issues (all resolved or accepted)
- Vendor API drift: fly-brain/two_flies.py line 24 `from flygym import Fly` ImportError with installed flygym 2.1.0 (submodules: anatomy/compose/flybody/rendering/simulation/utils/vision/warp, no top-level Fly). Accepted: real-path fallback, vendor NOT edited. Evidence: out/fail_egl.log append.
- torch missing in venv-brainfly314 (no torch module at all). Accepted as CPU fallback per plan QA (False = not a failure). No pip install performed (env frozen).
- `git push origin rerun/run` over https first failed: `could not read Username` (no credential helper). Resolved via `gh auth setup-git` (user's own logged-in gh CLI, ssh protocol, account izislesar) — no URL invented/changed. Retry exit 0.
- Cosmetic: first shot fired at frame 0 (t=0, dist=12m) — Poisson DN-pair count ≥3 by chance; controller allows (in-range, visible). Accepted: spec only requires >=1 hit (got 5). No frozen-constant change made to suppress it.
