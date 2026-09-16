#!/usr/bin/env python3
"""C2 torch-CUDA brain rasterizer (Task 3, G1 probes only).

Vectorized GPU scatter of glow sprites over static edge background:
  sprite radius 6px / sigma 2.0, additive blending,
  bloom radius 12px strength 0.6, output gamma 2.2.
GLOBAL normalization (G1 fix): reference anchor A = 99th percentile of all
per-neuron per-bin firing counts over the 1000 bins; norm(v) = LO+(HI-LO)*clip(v/A,0,1)
with [LO,HI]=[0.03,1.0], so quiet base-rate frames stay dim vs volley frames.
Frame f aggregates mean of its 10/3 bins (1000 bins -> 300 frames);
persistence = exponential decay tau=4 frames (weight-normalized average).
Legend: top-left monospace 14px #E7F5FF on 40%-alpha navy pill.

Usage (probes only -- full 300-frame render is Task 4, forbidden here):
  python tools/brain_render.py --probes 65,158
"""
import argparse
import math
import os
import subprocess
import sys
import time

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

W, H = 640, 480
BG_HEX = (11, 16, 32)
SPRITE_R, SPRITE_SIGMA = 6, 2.0
BLOOM_R, BLOOM_SIGMA, BLOOM_STRENGTH = 12, 4.0, 0.6
GAMMA = 2.2
TAU = 4.0
NORM_LO, NORM_HI = 0.03, 1.0  # GLOBAL norm floor/dim anchor (was per-frame [0.15, 1.0])
N_BINS, N_FRAMES = 1000, 300
FRAME_S = 10.0 / 300.0
DECAY_WIN = 24  # ~6*tau, tail < 0.25%
FONT_SIZE = 14
LEGEND_FG = (231, 245, 255)
NAVY_PILL = (11, 16, 32)

FONT_CANDIDATES = [
    "/home/izislesar/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/"
    "libreoffice-headless/libreoffice/share/fonts/truetype/DejaVuSansMono.ttf",
]


def resolve_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, FONT_SIZE), p
    try:
        out = subprocess.run(
            ["fc-match", "monospace", "--format=%{file}\n"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        for p in out:
            if p.endswith((".ttf", ".otf")) and os.path.exists(p):
                return ImageFont.truetype(p, FONT_SIZE), p
    except Exception:
        pass
    raise RuntimeError("no monospace TTF found (refusing PIL default bitmap font)")


def frame_bins(f):
    a = int(math.floor(f * N_BINS / N_FRAMES))
    b = int(math.ceil((f + 1) * N_BINS / N_FRAMES))
    return list(range(max(a, 0), min(b, N_BINS)))


def gauss_kernel2d(radius, sigma, device):
    ax = torch.arange(-radius, radius + 1, device=device, dtype=torch.float32)
    k1 = torch.exp(-0.5 * (ax / sigma) ** 2)
    k1 = k1 / k1.sum()
    return (k1[:, None] * k1[None, :])[None, None, :, :]


@torch.no_grad()
def render_frame(F, pos_xy, color01, gmat, anchor, bin_rate,
                 bg, k_sprite, k_bloom, font, device):
    t0 = time.perf_counter()
    f0 = max(0, F - DECAY_WIN)
    hist_frames = F - f0 + 1
    # raw per-neuron values for history frames: mean count over frame bins
    # (identical aggregation as before); GLOBAL normalization via anchor
    ws, acc = [], torch.zeros(pos_xy.shape[0], device=device, dtype=torch.float32)
    for k in range(f0, F + 1):
        bins = frame_bins(k)
        cnt = gmat[bins].mean(axis=0).astype(np.float32)  # mean over frame's bins
        v = torch.from_numpy(cnt).to(device)
        norm = NORM_LO + (NORM_HI - NORM_LO) * (v / anchor).clamp(0.0, 1.0)
        w = math.exp(-(F - k) / TAU)
        ws.append(w)
        acc = acc + norm * w
    lit = acc / sum(ws)  # weight-normalized decay average, stays in [0.03, 1.0]
    # vectorized splat: deposit (color + white-hot core) at rounded pixels
    xs = pos_xy[:, 0].round().clamp(0, W - 1).long()
    ys = pos_xy[:, 1].round().clamp(0, H - 1).long()
    hot = lit * lit * 0.6
    dep = color01 * lit[:, None] + hot[:, None]  # (N,3), white-hot core grows quadratically
    grid = torch.zeros(3, H, W, device=device, dtype=torch.float32)
    for c in range(3):
        grid[c].index_put_((ys, xs), dep[:, c], accumulate=True)
    glow = torch.nn.functional.conv2d(grid[None], k_sprite.expand(3, 1, -1, -1),
                                      padding=SPRITE_R, groups=3)[0]
    bloom = torch.nn.functional.conv2d(grid[None], k_bloom.expand(3, 1, -1, -1),
                                       padding=BLOOM_R, groups=3)[0] * BLOOM_STRENGTH
    img = bg + glow + bloom  # additive over static edge background
    img = img.clamp(0.0, 1.0) ** (1.0 / GAMMA)
    u8 = (img.clamp(0, 1) * 255.0).round().byte().cpu().permute(1, 2, 0).numpy()
    dt = time.perf_counter() - t0
    # legend on navy pill (40% alpha)
    bins = frame_bins(F)
    rate = float(bin_rate[bins].mean())
    label = f"frame {F}/300 \u00b7 t {F * FRAME_S:.1f}s \u00b7 rate {rate:.1f} Hz"
    pil = Image.fromarray(u8, "RGB").convert("RGBA")
    ov = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    l, t_, r_, b_ = dr.textbbox((0, 0), label, font=font)
    pad = 6
    x0, y0 = 10, 10
    dr.rounded_rectangle([x0, y0, x0 + (r_ - l) + 2 * pad, y0 + (b_ - t_) + 2 * pad],
                         radius=6, fill=NAVY_PILL + (int(255 * 0.4),))
    pil = Image.alpha_composite(pil, ov)
    dr2 = ImageDraw.Draw(pil)
    dr2.text((x0 + pad, y0 + pad), label, font=font, fill=LEGEND_FG + (255,))
    return pil.convert("RGB"), dt, rate, float(lit.max()), float(lit.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probes", required=True, help="comma-separated frame ids, e.g. 65,158")
    ap.add_argument("--outdir", default="out/brain")
    ap.add_argument("--names", default="probe_hit,probe_med")
    args = ap.parse_args()
    assert torch.cuda.is_available(), "CUDA required (C2)"
    device = torch.device("cuda")
    print(f"cuda=True device={torch.cuda.get_device_name(0)} torch={torch.__version__}",
          flush=True)

    lay = np.load("out/brain_layout.npz", allow_pickle=True)
    pos = lay["positions"].astype(np.float32)
    assert pos.shape == (5500, 2), pos.shape
    assert pos[:, 0].min() >= 0 and pos[:, 0].max() < W, "x out of 640 bounds"
    assert pos[:, 1].min() >= 0 and pos[:, 1].max() < H, "y out of 480 bounds"
    print(f"layout method={lay['method']} seed={lay['seed']} "
          f"x[{pos[:,0].min():.1f},{pos[:,0].max():.1f}] y[{pos[:,1].min():.1f},{pos[:,1].max():.1f}]",
          flush=True)
    col = lay["colors"].astype(np.float32) / 255.0
    pos_t = torch.from_numpy(pos).to(device)
    col_t = torch.from_numpy(col).to(device)
    bg_srgb = (torch.from_numpy(np.array(Image.open("out/brain_edge_bg.png").convert("RGB"))
                            .astype(np.float32) / 255.0)
               .permute(2, 0, 1).to(device))
    bg = bg_srgb.clamp(0.0, 1.0) ** GAMMA  # sRGB -> linear; composite in linear, encode at end
    assert tuple(np.array(Image.open("out/brain_edge_bg.png").convert("RGB"))[0, 0]) == BG_HEX, \
        "edge-bg corner pixel != #0B1020"

    sp = np.load("out/spikes_10s.npz", allow_pickle=True)
    st_ms, sids = sp["spike_times"], sp["spike_ids"]
    bin_rate = sp["bin10ms_rate"]
    assert bin_rate.shape == (1000,)
    bin_of_spike = np.clip((st_ms // 10).astype(np.int64), 0, 999)
    # GLOBAL anchor: full per-neuron x per-bin count matrix, single vectorized pass
    gmat = np.bincount(bin_of_spike * 5500 + sids.astype(np.int64),
                       minlength=1000 * 5500).reshape(1000, 5500)
    anchor = float(np.percentile(gmat, 99))
    print(f"global anchor p99={anchor:.4f} counts (max={int(gmat.max())}, "
          f"mean={gmat.mean():.4f}); norm maps [0, anchor] -> [{NORM_LO}, {NORM_HI}]",
          flush=True)

    k_sprite = gauss_kernel2d(SPRITE_R, SPRITE_SIGMA, device)
    k_bloom = gauss_kernel2d(BLOOM_R, BLOOM_SIGMA, device)
    font, font_path = resolve_font()
    print(f"font={font_path} size={FONT_SIZE}", flush=True)

    frames = [int(x) for x in args.probes.split(",")]
    names = args.names.split(",")
    assert len(frames) == len(names) == 2, "G1: exactly 2 probe frames"
    os.makedirs(args.outdir, exist_ok=True)
    torch.cuda.reset_peak_memory_stats()
    dts = []
    for F, name in zip(frames, names):
        img, dt, rate, lmax, lmean = render_frame(
            F, pos_t, col_t, gmat, anchor, bin_rate, bg, k_sprite, k_bloom, font, device)
        path = os.path.join(args.outdir, name + ".png")
        img.save(path)
        a = np.array(img)
        white_frac = float((a.sum(axis=2) == 765).mean())
        core = a.reshape(-1, 3).astype(np.float32).sum(axis=1)
        print(f"{name}: frame={F} rate={rate:.2f}Hz lit_max={lmax:.3f} lit_mean={lmean:.4f} "
              f"white_frac={white_frac * 100:.3f}% core_p99={float(np.percentile(core, 99)):.1f} "
              f"core_max={float(core.max()):.0f} render_t={dt:.2f}s -> {path}", flush=True)
        dts.append(dt)
    peak = torch.cuda.max_memory_allocated() / 1e9
    print(f"vram_peak_GB={peak:.3f} (limit 3.0)", flush=True)
    per_frame = sum(dts) / len(dts)
    print(f"fps_probe={1.0 / per_frame:.2f} render-only; 300f projection ~{300 * per_frame:.0f}s "
          f"(render passes only; full Task-4 loop cheaper per frame, history amortized)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
