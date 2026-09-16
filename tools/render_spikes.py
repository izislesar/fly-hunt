#!/usr/bin/env python3
"""Offline magma spike render: out/spikes.npz + run_meta hits -> out/spikes/sp%05d.png (90 x 640x480).

LUT: matplotlib _cm magma 256-entry when importable (endpoints forced EXACT
#000004 (0,0,4) -> #FCFFA4 (252,255,164)); else hand-coded 8-stop approximation
through #000004,#1C1044,#4F127B,#812581,#B5367A,#E55964,#FB8761,#FEC488,#FCFFA4.
LUT source is recorded in out/fail_render.log header comment.

Frame mapping: 90 frames <- 300 bins (3.333 bins/frame):
  frame f aggregates bins [f*300/90, (f+1)*300/90).
Raster: x = 300 time-bins compressed to 640px (x = bin*640/300);
  y = neuron subset: 480 rows sampled from 5500 (seed 0, sorted).
Intensity = binned rate normalized to [0,1] via (rate-min)/(max-min).
Hit frames (from out/run_meta.json, 30/65) get #FCFFA4 flash bar + counter text.
PIL path used when importable (PIL 12.3.0 here); struct+zlib fallback otherwise.
"""
import argparse
import json
import os
import struct
import sys
import zlib

N_NEURONS = 5500
N_ROWS = 480
N_BINS = 300
N_FRAMES = 90
MAGMA_LO = (0, 0, 4)       # #000004
MAGMA_HI = (252, 255, 164)  # #FCFFA4
APPROX_STOPS = ["#000004", "#1C1044", "#4F127B", "#812581", "#B5367A",
                "#E55964", "#FB8761", "#FEC488", "#FCFFA4"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Offline magma spike render")
    p.add_argument("--palette", default="magma:#000004-#FCFFA4",
                   help="palette spec, only magma:#000004-#FCFFA4 supported")
    p.add_argument("--size", default="640x480",
                   help="WxH, only 640x480 supported")
    p.add_argument("--fps", type=int, default=30,
                   help="fps, only 30 supported")
    p.add_argument("--input", default="out/spikes.npz")
    p.add_argument("--meta", default="out/run_meta.json")
    p.add_argument("--outdir", default="out/spikes")
    return p.parse_args(argv)


def hexrgb(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def build_lut():
    """Return (lut256 list of RGB, source_tag). Endpoints forced exact."""
    try:
        import matplotlib
        try:
            from matplotlib import colormaps
            cmap = colormaps["magma"]
        except Exception:
            from matplotlib import cm as _cm
            cmap = _cm.get_cmap("magma")
        lut = []
        for i in range(256):
            r, g, b, _a = cmap(i / 255.0)
            lut.append((int(round(r * 255)), int(round(g * 255)), int(round(b * 255))))
        lut[0] = MAGMA_LO
        lut[-1] = MAGMA_HI
        return lut, "matplotlib-magma-256(matplotlib %s)" % matplotlib.__version__
    except Exception as e:
        stops = [hexrgb(h) for h in APPROX_STOPS]
        lut = []
        segs = len(stops) - 1
        for i in range(256):
            pos = i / 255.0 * segs
            k = min(int(pos), segs - 1)
            t = pos - k
            c0, c1 = stops[k], stops[k + 1]
            lut.append((int(round(c0[0] + (c1[0] - c0[0]) * t)),
                        int(round(c0[1] + (c1[1] - c0[1]) * t)),
                        int(round(c0[2] + (c1[2] - c0[2]) * t))))
        lut[0] = MAGMA_LO
        lut[-1] = MAGMA_HI
        return lut, "handcoded-8stop-approx(%s)" % e


def write_png_struct(path, w, h, rgb_rows):
    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return c
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(px) for row in rgb_rows for px in [row])
    # rgb_rows: list of h rows, each flat bytes len w*3
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def main(argv=None):
    a = parse_args(argv)
    # Record parsed args even though only defaults supported
    if a.palette != "magma:#000004-#FCFFA4":
        print("WARN only magma:#000004-#FCFFA4 supported, got %s" % a.palette, file=sys.stderr)
    try:
        w_s, h_s = a.size.lower().split("x")
        W, H = int(w_s), int(h_s)
    except Exception:
        print("bad --size, want WxH", file=sys.stderr)
        return 2
    if (W, H) != (640, 480):
        print("WARN only 640x480 supported, got %dx%d" % (W, H), file=sys.stderr)
        W, H = 640, 480
    if a.fps != 30:
        print("WARN only --fps 30 supported, got %d" % a.fps, file=sys.stderr)

    import numpy as np
    d = np.load(a.input)
    rate = np.asarray(d["bin10ms_rate"], dtype=float)
    assert rate.shape == (300,), "bin10ms_rate shape %s != (300,)" % (rate.shape,)
    times = np.asarray(d["spike_times"], dtype=float)
    ids = np.asarray(d["spike_ids"], dtype=int)
    with open(a.meta) as f:
        meta = json.load(f)
    hit_frames = set(h["frame"] for h in meta.get("hits", []))

    lut, lut_src = build_lut()
    print("LUT source: %s endpoints %s->%s" % (lut_src, MAGMA_LO, MAGMA_HI))

    rng = np.random.default_rng(0)
    subset = sorted(rng.choice(N_NEURONS, size=N_ROWS, replace=False).tolist())
    row_of = {nid: r for r, nid in enumerate(subset)}

    rmin, rmax = float(rate.min()), float(rate.max())
    span = (rmax - rmin) or 1.0
    norm = (rate - rmin) / span  # (300,)

    # bin events
    ev_bins = np.clip((times // 10).astype(int), 0, N_BINS - 1)

    try:
        from PIL import Image, ImageDraw
        pil_ok = True
    except Exception as e:
        print("PIL missing (%s), struct+zlib fallback" % e, file=sys.stderr)
        pil_ok = False
    render_path = "PIL" if pil_ok else "struct+zlib"

    os.makedirs(a.outdir, exist_ok=True)
    bins_per_frame = N_BINS / N_FRAMES  # 3.333

    for f in range(N_FRAMES):
        b0 = int(f * bins_per_frame)
        b1 = max(int((f + 1) * bins_per_frame), b0 + 1)
        is_hit = f in hit_frames
        # frame intensity: max norm over aggregated bins (burst pops)
        fint = float(norm[b0:b1].max()) if b1 > b0 else 0.0

        if pil_ok:
            img = Image.new("RGB", (W, H), MAGMA_LO)
            px = img.load()
            # background columns: per-bin magma color over full height
            for b in range(N_BINS):
                x0 = int(b * W / N_BINS)
                x1 = max(int((b + 1) * W / N_BINS), x0 + 1)
                c = lut[int(round(norm[b] * 255))]
                for x in range(x0, min(x1, W)):
                    for y in range(H):
                        px[x, y] = c
            # raster dots: spikes in window +/-1 frame highlighted brighter
            wb0 = max(0, int((f - 1) * bins_per_frame))
            wb1 = min(N_BINS, int((f + 2) * bins_per_frame) + 1)
            for t, nid, b in zip(times, ids, ev_bins):
                if wb0 <= b < wb1 and int(nid) in row_of:
                    x = int(b * W / N_BINS)
                    y = row_of[int(nid)]  # 0..479 rows top
                    boost = 255 if (b0 <= b < b1) else 200
                    c = lut[boost]
                    for dx in (0, 1):
                        for dy in (0, 1):
                            xx, yy = min(x + dx, W - 1), min(y + dy, H - 1)
                            px[xx, yy] = c
            # playhead at current frame center
            phx = int((f + 0.5) * W / N_FRAMES)
            for y in range(H):
                px[phx, y] = MAGMA_HI
            # hit flash bar top 24px
            if is_hit:
                dr = ImageDraw.Draw(img)
                dr.rectangle([0, 0, W - 1, 23], fill=MAGMA_HI)
                dr.text((8, 5), "HIT frame %02d rate %.0fHz" % (f, rmin + fint * span), fill=(0, 0, 0))
            else:
                dr = ImageDraw.Draw(img)
                dr.text((8, 5), "frame %02d/90 rate %.0fHz" % (f, rmin + fint * span), fill=MAGMA_HI)
            img.save(os.path.join(a.outdir, "sp%05d.png" % f))
        else:
            rows = []
            for y in range(H):
                row = bytearray()
                for x in range(W):
                    b = min(int(x * N_BINS / W), N_BINS - 1)
                    v = int(round(norm[b] * 255))
                    row += bytes(lut[v])
                rows.append(bytes(row))
            # overlay dots + playhead + flash bar as raw pixel ops
            rarr = [bytearray(r) for r in rows]
            wb0 = max(0, int((f - 1) * bins_per_frame))
            wb1 = min(N_BINS, int((f + 2) * bins_per_frame) + 1)
            for nid, b in zip(ids, ev_bins):
                if wb0 <= b < wb1 and int(nid) in row_of:
                    x = int(b * W / N_BINS)
                    y = row_of[int(nid)]
                    boost = lut[255] if (b0 <= b < b1) else lut[200]
                    for dx in (0, 1):
                        for dy in (0, 1):
                            xx, yy = min(x + dx, W - 1), min(y + dy, H - 1)
                            rarr[yy][xx * 3:(xx * 3) + 3] = bytes(boost)
            phx = int((f + 0.5) * W / N_FRAMES)
            for y in range(H):
                rarr[y][phx * 3:(phx * 3) + 3] = bytes(MAGMA_HI)
            if is_hit:
                for y in range(24):
                    for x in range(W):
                        if y < 4 or (x % 16) < 12:  # marker bar pattern
                            rarr[y][x * 3:(x * 3) + 3] = bytes(MAGMA_HI)
            blob = write_png_struct(os.path.join(a.outdir, "sp%05d.png" % f), W, H, [bytes(r) for r in rarr])
            with open(os.path.join(a.outdir, "sp%05d.png" % f), "wb") as fh:
                fh.write(blob)

    print("wrote %d PNGs via %s LUT=%s hits=%s" % (N_FRAMES, render_path, lut_src, sorted(hit_frames)))
    print("RENDER_PATH=%s LUT=%s" % (render_path, lut_src))
    return 0


if __name__ == "__main__":
    sys.exit(main())
