# ai-trains-fly-rerun - Work Plan (Path A, real EGL)
## TL;DR (For humans)
Что получишь: те же артефакты `out/trophy_hunt.mp4 1280x480@30fps`, `out/physics_log.csv` 90 строк, `out/spikes.npz` — но теперь из РЕАЛЬНОГО прогона (mujoco 3.9.0 EGL + brian2 2.10.1 + torch cu130 с CUDA), а не синтетики. База уже готова: venv `~/venv-brainfly314` (py3.14.7), torch установлен (считать CUDA-рабочим; проверка `torch.cuda.is_available()` — первый шаг R1), контур N=5500 с реальными ребрами S=120344, EGL доказан (`model-ok step-ok`, 500 шагов без NaN, `out/egl_probe.png`), публичный git-репо создан. Осталось: git baseline + реальный headless-ран 3с → перерендер спайков → пересклейка тем же ffmpeg → свежий perf → сверка TL;DR → мини-аудит. Каждый todo = коммит + пуш в свою ветку, финал — мерж в `main`. Effort: 6 todos + 2 final. Risk: вендорный `two_flies.py` может нести API-дрейф flygym 2.x — закрыто ADAPTATION-контрактом и фолбэком на `run_hunt.py real-path`. Decisions: либы mujoco 3.9.0/brian2 2.10.1/flygym 2.1.0/torch-cu130, CC=gcc16.2.1, те же фризы (threshold3/hyst2/ammo5/range20/cooldown500/spread0.02, reward-формула, clip [0,2], 66 phys/frame, bin10ms).

## Scope
IN:
- Venv `~/venv-brainfly314/bin/python` (py3.14.7, mujoco 3.9.0, brian2 2.10.1, flygym 2.1.0, pyarrow 25.0.1, PIL 12.3.0); `MUJOCO_GL=egl CC=gcc CXX=g++` на каждой команде; абсолютный путь к python, не ambient
- Реальный headless-ран 3с: `arena/hunt_arena.xml` + контур `data/hunting_circuit_6k.npz` (real-edge S=120344) + `out/ADAPTATION.md` контракт (BrainEngine.step/get_dn_spikes/compute_drive, DNRateDecoder defaults exact) + `tools/reward.py` формула + shot-параметры; выход: `out/frames/f%05d.png` 90 шт 640x480 (EGL-рендер), `out/physics_log.csv` 90 строк (тот же заголовок, монотонно, >=1 hit), `out/spikes.npz` (300 бинов), `out/run_meta.json` (`path=real-egl`, import_probe ok)
- Перерендер `out/spikes/sp%05d.png` 90 шт magma из нового npz тем же `tools/render_spikes.py`
- Пересклейка ТОЙ ЖЕ командой `ffmpeg -y -framerate 30 -i out/frames/f%05d.png -framerate 30 -i out/spikes/sp%05d.png -filter_complex hstack -c:v libx264 -crf 23 -pix_fmt yuv420p out/trophy_hunt.mp4` → ffprobe 1280/480/30/h264 <50MB
- Свежий `out/perf.md` с РЕАЛЬНЫМИ wall-числами (sim/wall из настоящего прогона), `out/tldr_check.md` + `out/failures.md` обновлены
- Бэкапы синтетики ПЕРЕД перезаписью: `out/frames.synth.bak/` (или tar), `out/physics_log.synth.bak.csv`, `out/spikes.synth.bak.npz`, `out/trophy_hunt.synth.bak.mp4`
- Git: публичный репо создан пользователем; remote `origin` (Atlas проверяет `git remote -v`, при отсутствии — STOP с инструкцией, не выдумывать URL); ветки `rerun/run`, `rerun/video`, `rerun/qa` от `main`; `.gitignore` (data/*.parquet, out/frames/*.png кроме 3 сэмплов, `*.bak.*`, `__pycache__/`, `*.pt` вне LFS-списка); git-lfs на `data/*.parquet` + `out/*.mp4`; `fly-brain/` НЕ пушится (вендор по SHA, клонируется); каждый todo = коммит + `git push origin <ветка>`; мерж в `main` только после F1–F2 APPROVE
OUT / Must-NOT-Have:
- Смена замороженных чисел (shot, reward, clip, sync-заголовок, 66 phys/frame); новые тела мухи; аудио/титры; второй видеофайл; pip install/upgrade (env заморожен); правки вендора fly-brain/; правки плана v1 (глобальный `ai-trains-fly.md` — только чтение)

## Verification strategy
Agent-executed only. Каждый todo несет refs/acceptance/QA-happy/QA-fail/commit. Гейты: `check_sync.py` PASS 90 строк; `check_spikes.py` PASS (300,); `check_shot.py` PASS; `check_reward.py` PASS; ffprobe 1280/480/30/h264; `grep -c hit,1$` CSV >=1; EGL-доказательство (как минимум `model-ok step-ok` в логе рана).

## Execution strategy
Строго последовательно (каждый следующий читает артефакты предыдущего): 1 бэкапы+ран -> 2 спайки-рендер -> 3 склейка -> 4 perf -> 5 tldr+failures -> 6 мини-аудит. Ран: сначала проба вендорного `two_flies.py --headless` (сухой импорт + `--help`), при дрейфе — `tools/run_hunt.py` real-path (расширить Phase-0 ветку: EGL уже доказан). Один запрос = один план.

## TODOs
- [ ] 1. Git baseline + бэкапы синтетики + реальный EGL-ран 3с (90 frames + CSV + npz + meta)
  - refs: `tools/run_hunt.py`, `fly-brain/two_flies.py`, `arena/hunt_arena.xml`, `out/ADAPTATION.md`, `docs/sync.md`, `git remote -v`, `.gitignore`, `git-lfs`
  - acceptance: `git remote -v` показывает origin + `git status --short` чист от лишнего + ветка `rerun/run` + `~/venv-brainfly314/bin/python -c "import torch;print(torch.__version__,torch.cuda.is_available())"` exit 0 + `ls out/frames/f*.png | wc -l` == 90 640x480 + `python3 tools/check_sync.py --csv out/physics_log.csv` PASS 90 rows + `bin10ms_rate.shape` == (300,) + `run_meta.json:path` == `real-egl` + >=1 hit reward>0 dW logged + `git push origin rerun/run` exit 0
  - QA-happy: `grep -c ",1$" out/physics_log.csv` >= 1 + ран-лог содержит `model-ok step-ok` evidence `out/run_egl.log` + torch CUDA True/False запротоколирован (False = CPU-фолбэк, не фейл)
  - QA-fail: нет origin -> STOP + инструкция пользователю (URL не выдумывать) evidence `out/fail_git.log`; вендорный дрейф/torch-импорт -> `run_hunt.py real-path` фолбэк + `out/fail_egl.log` append evidence (read-first, append-only)
  - commit: `feat(run): real egl 3s hunt` + push `rerun/run`
- [ ] 2. Перерендер спайков magma 90 PNG из нового npz
  - refs: `tools/render_spikes.py --palette magma:#000004-#FCFFA4 --size 640x480 --fps 30`
  - acceptance: `ls out/spikes/sp*.png | wc -l` == 90 + `file out/spikes/sp00000.png` PNG 640x480
  - QA-happy: 90/90 distinct md5 + `#FCFFA4` на hit-кадрах evidence `out/fail_render.log` (append)
  - QA-fail: mismatch count -> `out/fail_render.log` evidence + fix
  - commit: `feat(viz): rerender magma from real run`
- [ ] 3. Пересклейка trophy_hunt.mp4 той же командой
  - refs: exact cmd из Scope
  - acceptance: ffprobe == 1280/480/30/h264 + size<50MB
  - QA-happy: `ls -lh out/trophy_hunt.mp4` evidence
  - QA-fail: ffprobe mismatch -> `out/fail_ffmpeg.log` evidence (append)
  - commit: `feat(video): restitch real hunt+spikes`
- [ ] 4. Свежий perf.md с реальными wall-числами
  - refs: `out/run_egl.log` wall, `nvidia-smi`, `out/perf.md`
  - acceptance: `cat out/perf.md` содержит sim/wall>=0.2 (реальный wall), VRAM<3.5, RSS<14
  - QA-happy: evidence `out/perf.md`
  - QA-fail: превышение -> chunked + `out/fail_perf.log` evidence (append)
  - commit: `chore(perf): real-run slo`
- [ ] 5. Сверка TL;DR + failures под реальный прогон
  - refs: `out/tldr_check.md`, `out/failures.md`, `out/trophy_hunt.mp4`, `out/physics_log.csv`, `out/spikes.npz`
  - acceptance: `test -f out/trophy_hunt.mp4 && test -f out/physics_log.csv` exit 0 + per-claim VERIFIED в tldr_check
  - QA-happy: `ls -lh out/` evidence
  - QA-fail: артефакта нет -> `out/fail_tldr.log` evidence (append)
  - commit: `docs(tldr): sync real-run artifacts`
- [ ] 6. Мини-аудит: compliance + live-gates на новых артефактах
  - refs: `out/F1_audit.md`, `out/F3_qa.md` (обновить rerun-секцией, не переписывать)
  - acceptance: 7 гейтов EXIT 0 live (budget/circuit/sync/physics/shot/reward/spikes) + ffprobe 1280/480/30/h264 + N=5500 + DN==150 + single ffmpeg cmd
  - QA-happy: `RERUN VERDICT: APPROVE` в обоих файлах evidence
  - QA-fail: любой EXIT!=0 -> numbered findings, без фиксов молча
  - commit: `chore(qa): rerun audit approve`

## Final verification wave
- [ ] F1. Rerun compliance — expect все 1–6 чекбоксы со ссылками на живые выводы + `path=real-egl` в run_meta + бэкапы синтетики на месте + каждый todo закоммичен и запушен (`git log origin/rerun/run origin/rerun/video origin/rerun/qa` содержат сообщения из плана)
- [ ] F2. Scope fidelity — expect один mp4 + forbidden-grep пуст + N=5500 + замороженные числа нетронуты (diff `tools/reward.py`, shot-констант, sync-заголовка пуст)

## Commit strategy
Ветки: `rerun/run` (задачи 1–2), `rerun/video` (задача 3), `rerun/qa` (задачи 4–6). По одному коммиту на todo сообщениями из каждого `commit:` + обязательный `git push origin <ветка>` сразу после коммита (каждая задача считается закрытой только после пуша). Не коммитить `data/*.parquet`, `out/frames/*.png` (кроме 3 сэмплов), `*.bak.*`, `fly-brain/`. Мерж веток в `main` + `git push origin main` только после F1–F2 APPROVE. Тег `trophy-hunt-real-egl`.

## Success criteria
- `out/trophy_hunt.mp4` 1280x480@30fps libx264 <50MB из реальных EGL-кадров
- `out/physics_log.csv` 90 строк монотонно, >=1 hit reward>0 dW_mean, `check_sync` PASS
- `run_meta.json:path` == `real-egl`, `model-ok step-ok` в `out/run_egl.log`
- Ветки `rerun/run`, `rerun/video`, `rerun/qa` запушены в origin; `main` смержен после APPROVE
- 1–6 + F1–F2 APPROVE
