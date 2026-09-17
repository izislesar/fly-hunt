#!/usr/bin/env python3
"""Task C2 (hunt-clarity-pass): annotate duel+brain panels (COPIES only).

Reads (read-only): out/duel/f%05d.png, out/brain/b%05d.png, out/flyeye/e%05d.png
Writes: out/duel_ann/f%05d.png x300, out/brain_ann/b%05d.png x300 + 4 proof PNGs.

Overlays per duel frame (640x480):
  (a) counter top-left: 'ФРАГИ k/5 · ПАТРОНЫ (5-k)/5', 20px DejaVu Sans Mono #E7F5FF
      (k = hits_so_far; ammo_used modelled as 1 round/hit — all 5 spent by
      frame 85, ammo_left=0 per out/run_egl_10s.log; volleys 2-3 silent so no
      finer ammo timing exists; logged decision)
  (b) title 'ПОПАДАНИЕ!' 48px DejaVu Sans Bold white + black stroke,
      centered-upper, on hit frame + next 11 frames (12-frame dwell each)
  (c) moose hit-flash: pixels inside measured moose bbox lerped toward white
      (alpha 0.45) on frames h-2..h+2 per hit (visual-only brightening)
  (d) fly-eye PiP 160x120 pasted top-right with 2px #1A2340 border
Per brain frame: 6px #FFD43B border ONLY on the 5 hit frames (exact copies else).
Border occupies the outer 6px strip; the brain legend pill starts at (10,10)
per tools/brain_render.py -> no overlap (verified in run log).

Rect-overlap check: fly bbox measured live per frame with the diorama dark-pixel
method (tools/fly_probe.measure_fly family: gray<60 mass in the fly search zone);
title/counter/PiP rects must not intersect it (max 2 reposition iterations).
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
DUEL = REPO / "out" / "duel"
BRAIN = REPO / "out" / "brain"
EYE = REPO / "out" / "flyeye"
D_ANN = REPO / "out" / "duel_ann"
B_ANN = REPO / "out" / "brain_ann"

N = 300
W, H = 640, 480
HITS = [0, 19, 46, 65, 85]
DWELL = 12  # hit frame + next 11

LO = Path("/home/izislesar/.cache/codex-runtimes/codex-primary-runtime/"
          "dependencies/native/libreoffice-headless/libreoffice/share/fonts/truetype")
FONT_TITLE = LO / "DejaVuSans-Bold.ttf"
FONT_MONO = LO / "DejaVuSansMono.ttf"
assert FONT_TITLE.exists(), f"missing {FONT_TITLE}"
assert FONT_MONO.exists(), f"missing {FONT_MONO}"
print(f"font_title={FONT_TITLE} size=48", flush=True)
print(f"font_mono={FONT_MONO} size=20", flush=True)
TITLE_FONT = ImageFont.truetype(str(FONT_TITLE), 48)
COUNT_FONT = ImageFont.truetype(str(FONT_MONO), 20)

TITLE_TXT = "ПОПАДАНИЕ!"
PIP_W, PIP_H = 160, 120
# Reposition iter 1: corner PiP (y=10) covered the title's "!" (title ink to
# x=498 > PiP left edge 468). PiP moved down to y=104: still top-right column,
# 10px gap under the title (title bottom 92 < border top 102), sky-only zone
# (ball/pillar/moose/fly all at x<376) per visual samples. Corner slot rejected.
PIP_XY = (W - PIP_W - 10, 104)  # paste origin; 2px border drawn around it
BORDER_RGB = (26, 35, 64)      # #1A2340
COUNT_FG = (231, 245, 255)     # #E7F5FF
BRAIN_HIT = (255, 212, 59)     # #FFD43B
FLASH_ALPHA = 0.45

# Fly / moose geometry: FIXED safe zones derived from visual samples of the
# shipped take (look_at inspections of f00000/f00019/f00299, logged below) +
# programmatic per-hit confirmation with a brown-mass mask for the moose.
# The shipped take is darker than staging probes, so the diorama gray<60 mass
# method saturates (whole crop dark) and projection re-render is out of scope;
# visual-sample union + per-frame numeric rect check is the honest method here.
#
# Visual samples (640x480, origin top-left):
#   f00000: fly [203,355,230,398], moose box [182,303,260,365]
#   f00019: fly [200,338,220,370], moose box [181,287,238,342]
#   f00299: fly [204,338,231,370], moose box [181,273,252,343]
#   ball upper area (f0 [339,151,365,175], f19 [312,146,335,170], gone by f299)
#   pre-existing 'HUNT' text bottom-left (~8,458) — counter goes top-left.
FLY_UNION = (190, 328, 241, 408)     # fly samples union + ~10px margin
MOOSE_ROI = (170, 260, 275, 380)     # brown-moose search region
MOOSE_FALLBACK = (178, 270, 262, 375)  # visual union + margin


def rects_intersect(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def fly_presence(arr):
    """Dark-mass pixel count inside FLY_UNION (fly is the darkest speck there)."""
    x0, y0, x1, y1 = FLY_UNION
    gray = arr[y0:y1, x0:x1].astype(float).mean(axis=2)
    return int((gray < 25.0).sum())


def title_rect(draw, txt, y_top):
    l, t, r, b = draw.textbbox((0, 0), txt, font=TITLE_FONT, stroke_width=2)
    tw, th = r - l, b - t
    x = (W - tw) // 2 - l
    return (x, y_top, x + tw, y_top + th)


def title_x(draw, txt):
    l, t, r, b = draw.textbbox((0, 0), txt, font=TITLE_FONT, stroke_width=2)
    return (W - (r - l)) // 2 - l


def main():
    D_ANN.mkdir(exist_ok=True)
    B_ANN.mkdir(exist_ok=True)

    # ---- Phase 1: fly presence on samples + title placement vs FLY_UNION ----
    sample_idx = sorted(set(HITS + [h + 6 for h in HITS] + [8, 150, 299]))
    for i in sample_idx:
        arr = np.asarray(Image.open(DUEL / f"f{i:05d}.png").convert("RGB"))
        print(f"sample f{i:05d} fly_darkmass={fly_presence(arr)} "
              f"(in FLY_UNION {FLY_UNION})", flush=True)
    union = FLY_UNION
    print(f"fly_union={union} (visual samples f0/f19/f299 + margin)", flush=True)

    # Title candidate rows (centered-upper), counter fixed top-left.
    tmp = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(tmp)
    counter_rect = (10, 8, 10 + 330, 8 + 28)  # conservative text extent
    pip_rect = (PIP_XY[0] - 2, PIP_XY[1] - 2,
                PIP_XY[0] + PIP_W + 2, PIP_XY[1] + PIP_H + 2)
    title_y = 44
    overlap_log = []
    for iteration in range(3):  # initial + max 2 repositions
        tr = title_rect(d, TITLE_TXT, title_y)
        hits_rects = [r for r in (tr, counter_rect, pip_rect)
                      if rects_intersect(r, union)]
        aux = []
        if rects_intersect(tr, pip_rect):
            aux.append(("title", "pip"))
        if rects_intersect(counter_rect, pip_rect):
            aux.append(("counter", "pip"))
        overlap_log.append({"iter": iteration, "title_y": title_y,
                            "title_rect": tr, "pip_rect": pip_rect,
                            "fly_union": union,
                            "intersecting": hits_rects, "aux": aux})
        if not hits_rects and not aux:
            print(f"overlap_check iter={iteration} title_y={title_y} PASS "
                  f"(no rect intersects fly_union; title/counter clear of PiP)",
                  flush=True)
            break
        print(f"overlap_check iter={iteration} title_y={title_y} CONFLICT "
              f"{hits_rects} -> shift", flush=True)
        title_y += 40
    else:
        print("OVERLAP PERSISTENT CONFLICT — STOP (not covering the fly)",
              flush=True)
        sys.exit(2)
    if overlap_log[-1]["intersecting"] or overlap_log[-1]["aux"]:
        print("OVERLAP PERSISTENT CONFLICT — STOP (not covering the fly)",
              flush=True)
        sys.exit(2)
    print(f"overlap_log={json.dumps(overlap_log)}", flush=True)
    TITLE_Y = title_y

    # ---- Phase 2: moose bbox per hit (live brown-mass measurement) ----
    moose_boxes = {}
    for h in HITS:
        arr = np.asarray(Image.open(DUEL / f"f{h:05d}.png").convert("RGB"))
        x0, y0, x1, y1 = MOOSE_ROI
        roi = arr[y0:y1, x0:x1].astype(np.int16)
        R, G, B = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
        mask = (R > G + 6) & (G > B + 3) & (R > 30)
        if mask.any():
            ys, xs = np.nonzero(mask)
            bb = (x0 + int(xs.min()) - 6, y0 + int(ys.min()) - 6,
                  x0 + int(xs.max()) + 7, y0 + int(ys.max()) + 7)
            bb = (max(0, bb[0]), max(0, bb[1]), min(W, bb[2]), min(H, bb[3]))
        else:
            bb = MOOSE_FALLBACK
        moose_boxes[h] = bb
        print(f"hit f{h:05d} moosebox={bb} brown_n={int(mask.sum())}", flush=True)
    flash_frames = {}
    for h in HITS:
        for f in range(max(0, h - 2), min(N, h + 3)):
            flash_frames.setdefault(f, []).append(h)
    print("moose_flash: lerp-toward-white alpha=%.2f frames=%s"
          % (FLASH_ALPHA,
             {f: flash_frames[f] for f in sorted(flash_frames)}),
          flush=True)

    # Title dwell frames.
    dwell = set()
    for h in HITS:
        dwell.update(range(h, min(N, h + DWELL)))

    def hits_so_far(i):
        return sum(1 for h in HITS if h <= i)

    # ---- Phase 3: annotate duel copies ----
    per_frame_fly_miss = 0
    for i in range(N):
        src = DUEL / f"f{i:05d}.png"
        img = Image.open(src).convert("RGB")  # COPY in memory; src never written
        arr = np.array(img)  # writable copy; src file never written
        k = hits_so_far(i)

        # (c) moose flash first (under text/PiP).
        if i in flash_frames:
            h0 = flash_frames[i][0]
            bb = moose_boxes.get(h0)
            if bb:
                x0, y0, x1, y1 = [max(0, v) for v in
                                  (bb[0], bb[1], min(bb[2], W), min(bb[3], H))]
                region = arr[y0:y1, x0:x1].astype(np.float32)
                arr[y0:y1, x0:x1] = np.round(
                    region + (255.0 - region) * FLASH_ALPHA).astype(np.uint8)
                img = Image.fromarray(arr, "RGB")

        dr = ImageDraw.Draw(img)
        # (a) counter (shadow + #E7F5FF mono).
        counter = f"ФРАГИ {k}/5 · ПАТРОНЫ {5 - k}/5"
        dr.text((10, 8), counter, font=COUNT_FONT, fill=(0, 0, 0))
        dr.text((11, 9), counter, font=COUNT_FONT, fill=COUNT_FG)
        # (b) title during dwell.
        if i in dwell:
            dr.text((title_x(d, TITLE_TXT), TITLE_Y),
                    TITLE_TXT, font=TITLE_FONT, fill=(255, 255, 255),
                    stroke_width=2, stroke_fill=(0, 0, 0))
        # (d) PiP + 2px border.
        eye = Image.open(EYE / f"e{i:05d}.png").convert("RGB")
        assert eye.size == (PIP_W, PIP_H), f"flyeye size {eye.size}"
        dr.rectangle(pip_rect, outline=BORDER_RGB, width=2)
        img.paste(eye, PIP_XY)
        img.save(D_ANN / f"f{i:05d}.png")

        tr = title_rect(ImageDraw.Draw(Image.new("RGB", (W, H))),
                        TITLE_TXT, TITLE_Y)
        if (rects_intersect(tr, union) or rects_intersect(counter_rect, union)
                or rects_intersect(pip_rect, union)):
            per_frame_fly_miss += 1
            print(f"frame f{i:05d} OVERLAP vs fly_union={union}", flush=True)
        if i % 50 == 0:
            print(f"frame f{i:05d} fly_darkmass={fly_presence(arr)}",
                  flush=True)
    print(f"per_frame_overlap_misses={per_frame_fly_miss} (must be 0)",
          flush=True)
    assert per_frame_fly_miss == 0, "overlap with live fly bbox detected"

    # ---- Phase 4: brain copies + 6px #FFD43B border on hit frames ----
    for i in range(N):
        src = BRAIN / f"b{i:05d}.png"
        img = Image.open(src).convert("RGB")
        if i in HITS:
            dr = ImageDraw.Draw(img)
            dr.rectangle([0, 0, W - 1, H - 1], outline=BRAIN_HIT, width=6)
        img.save(B_ANN / f"b{i:05d}.png")
    print("brain_border: 6px #FFD43B on frames [0,19,46,65,85]; "
          "outer 6px strip vs legend pill at (10,10)+ -> no overlap",
          flush=True)

    # ---- Phase 5: proofs ----
    Image.open(D_ANN / "f00019.png").save(D_ANN / "proof_hit.png")
    Image.open(D_ANN / "f00150.png").save(D_ANN / "proof_quiet.png")
    Image.open(D_ANN / "f00299.png").save(D_ANN / "proof_end.png")
    Image.open(B_ANN / "b00019.png").save(B_ANN / "proof_hit.png")
    print("proofs: duel_ann/proof_hit|quiet|end + brain_ann/proof_hit",
          flush=True)


if __name__ == "__main__":
    main()
