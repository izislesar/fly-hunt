# Pins (frozen per plan ai-trains-fly.md TL;DR)
# Task 1 owns: python, mujoco, brian2 rows.
# Task 2 completed: flygym, ffmpeg rows verified 2026-09-16 (see Verification below).

| pkg | version |
|-----|---------|
| python | 3.10.14 |
| mujoco | 3.1.6 |
| brian2 | 2.5.2 |
| flygym | 1.2.1 |
| ffmpeg | 7 with libx264 |

Env: `CC=gcc12 CXX=g++12 MUJOCO_GL=egl`
Fallbacks: `QT_QPA_PLATFORM=xcb`, `xvfb-run -a`

> NOTE 2026-09-16: rows above (python 3.10.14 / mujoco 3.1.6 / brian2 2.5.2 / flygym 1.2.1 / ffmpeg 7) — superseded by Fresh resolve 2026-09-16 (Path A) below. Old rows KEPT byte-identical as audit trail; do not delete.

## Verification (Task 2, 2026-09-16)
- `ffmpeg -version | grep libx264` exit 0 — PASS. System ffmpeg n9.0.1
  (`ffmpeg version n9.0.1`, built with gcc 16, config contains `--enable-libx264`).
  DELTA (OBSERVED, not FAILED): plan pins ffmpeg7; host provides n9.0.1 (newer)
  with libx264 present, which is the acceptance gate. See out/env.log + out/fail_pins.log.
- `pip freeze | grep -E "mujoco==3.1.6|brian2==2.5.2|flygym==1.2.1"` exit 1 on
  system python 3.14.7 — packages NOT installed (no brain-fly conda env yet;
  system pip PEP668 externally-managed; no conda/mamba on host).
  Status per row: mujoco 3.1.6 / brian2 2.5.2 / flygym 1.2.1 = declared-not-installed.
  Remediation: `mamba env create -f environment.yml`, then re-run gates inside env.
   Evidence: out/fail_pins.log (real pip output, no fabrication).

## Fresh resolve 2026-09-16 (Path A)
Host moved to Path A: fresh libs on Arch, gcc 16.2.1, system python 3.14 venv at ~/venv-brainfly314. VERIFIED-BY-USER-FREEZE + live import confirmation by agent 2026-09-16.

| pkg | version | status |
|-----|---------|--------|
| python | 3.14.7 | VERIFIED-BY-USER-FREEZE (venv `~/venv-brainfly314/bin/python --version` -> Python 3.14.7) |
| mujoco | 3.9.0 | VERIFIED-BY-USER-FREEZE (live `import mujoco` -> 3.9.0; `pip freeze` -> mujoco==3.9.0) |
| brian2 | 2.10.1 | VERIFIED-BY-USER-FREEZE (live `import brian2` -> 2.10.1; `pip freeze` -> Brian2==2.10.1) |
| flygym | 2.1.0 | VERIFIED-BY-USER-FREEZE (`pip freeze` -> flygym==2.1.0; `import flygym` import-ok) |
| ffmpeg | n9.0.1 + libx264 | VERIFIED-BY-USER-FREEZE (`ffmpeg -version | grep libx264` exit 0, see Verification above) |
| CC | gcc 16.2.1 | VERIFIED-BY-USER-FREEZE (`gcc --version | head -1` -> gcc (GCC) 16.2.1 20260810) |

Also frozen (user-verified): matplotlib==3.11.2, numpy==2.5.3, pandas==2.3.3, pyarrow==25.0.1.

Env (Path A): `CC=gcc CXX=g++ MUJOCO_GL=egl`
CC deviation rationale: gcc12 absent from Arch repos (plan pin CC=gcc12 obsolete); wheels need no CC except brian2 codegen which accepts gcc16. Verified live: brian2 2.10.1 imports under gcc 16.2.1 host.
Verification method: `pip freeze` + live import with absolute venv python `~/venv-brainfly314/bin/python` (never ambient python).
Xvfb: `/usr/bin/xvfb-run` present on host 2026-09-16.
