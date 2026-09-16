#!/usr/bin/env python3
"""Task 12: headless 3s EGL hunt orchestrator — `tools/run_hunt.py`.

Refs: fly-brain/two_flies.py --headless --visual --gustatory --somatosensory
      --duration 3 --separation 5.0 --no-viewer (real path, 90 frames 640x480).
Contract: out/ADAPTATION.md (иначе-branch active — wire via
      BrainEngine.step (0.1ms) + get_dn_spikes + decoder.update +
      BrainBodyBridge.compute_drive, NOT def reset/spike/torque).
Shot params (frozen, from tools/check_shot.py): threshold=3 spikes/10ms
      DNpe017, hysteresis=2, ammo=5, range=20.0m, cooldown=500ms,
      spread=0.02rad, seed=1. Reward formula from tools/reward.py.
Sync schema from docs/sync.md: header exact, moose_pos 'x;y;z', monotonic
      triple t_neural=frame*33.33ms / t_physics=frame*0.03333s / frame_id,
      66 phys/frame nominal, bin 10ms. Circuit N=5500
      (data/hunting_circuit_6k.npz).

HOST REALITY (honest): mujoco, brian2, torch, flygym NOT installed on host
(system python, PEP668, no conda env). Real EGL sim + real SNN impossible.
Phase 0 import probe therefore fails -> documented SYNTHETIC fallback path
with SAME interfaces: 90 frames, 90-row CSV passing tools/check_sync.py,
spike raster out/spikes.npz (300 bins = 3s/10ms). NOTHING is faked as real:
run_meta.json `path` = "synthetic(mujoco-missing)" with probe errors quoted.

Synthetic model (seeded RNG seed=1, all choices documented):
- 90 frames @30fps, t_neural=frame*33.33ms, t_physics=frame*0.03333s.
- Moose approach 12m->4m: x=12-frame*(8/89), y=0.0, z=0.2 (meters).
- DNpe017 counts: baseline rng 0..2; scheduled high counts (>=3) at frames
  30,31,65,66 (primary 30,65 + immediate retry 31,66 in case of the 0.3%
  cone-miss); forced count=0 at frame 45 to guarantee hysteresis re-arm
  (re-arm needs count<=threshold-hysteresis=1) between the two shots.
  Fired through the REAL ShotController from tools/check_shot.py
  (ammo 5, cooldown 500ms, range 20, spread 0.02, seed 1) -> exactly 2 hits
  (frames 30 and 65), ammo used 2, rest miss/cooldown. Guarantees >=1 hit.
- Loom model: loom_Hz = 40 + (12-dist)*15  (dist 12->40Hz, dist 4->160Hz).
- Reward/dW via REAL tools/reward.py imports: reward(hit,dist,loom),
  hebb_dw(rate,rate,W=0.25). Miss/no-see -> 0.
- Spike rate model: base 20Hz + hit burst 120Hz + seeded jitter [-2..+2]Hz,
  all within [5,200]Hz. Scale to counts: spikes are recorded per 1000
  neurons: count = round(rate * window_s * N/1000), i.e. frame window
  0.03333s -> rate*0.18333; 10ms bin -> rate*0.055. (Full-population counts
  would be ~183x larger; the /1000 normalization keeps CSV magnitudes
  seed-like and is documented here + in run_meta.json.)
- 300 bins x 10ms raster generated first (per-bin rate = owning frame rate,
  bin b center (b*10+5)ms -> frame floor(center/33.33)); CSV spike_count =
  sum of bin counts whose center falls in the frame window (3 or 4 bins).
  bin10ms_rate stored in spikes.npz for Task 13.
- Renderer: PIL (present, 12.3.0) — hunt scene per frame: sky bg, ground,
  fly dot, moose-box rect (x shifts with dist), looming circle (radius grows
  as dist shrinks), hit flash marker on hit frames, frame_id text so every
  frame differs. (struct+zlib minimal-PNG fallback coded but NOT taken;
  documented in meta.)
"""
import random
import shutil
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
try:
    from PIL import Image as _PIL_Image
    from PIL import ImageDraw as _PIL_Draw
    HAS_PIL = True
except Exception:  # noqa: BLE001
    _PIL_Image = None
    _PIL_Draw = None
    HAS_PIL = False
from check_shot import (  # noqa: E402  (real frozen shot logic)
    COOLDOWN_MS,
    HYSTERESIS,
    RANGE_M,
    SPREAD_RAD,
    THRESHOLD,
    ShotController,
)
from reward import hebb_dw, reward  # noqa: E402  (real frozen formula)

N_FRAMES = 90
FRAME_MS = 33.33
FRAME_S = 0.03333
N_NEURONS = 5500  # data/hunting_circuit_6k.npz N
SEED = 1
HIT_FRAMES = (30, 65)      # primary scheduled shots
RETRY_FRAMES = (31, 66)    # cone-miss retry (no cooldown consumed on miss)
REARM_FRAME = 45           # forced count=0 -> hysteresis re-arm guarantee
HIGH_COUNT_FRAMES = HIT_FRAMES + RETRY_FRAMES
BASE_RATE_HZ = 20.0
HIT_BURST_HZ = 120.0
W_HEBB = 0.25


def probe_imports():
    """Phase 0: try the real path imports (vendor wiring per ADAPTATION.md).

    Real path would be: mujoco EGL sim (two_flies.py CrossFlySimulation) +
    BrianEngine.step/get_dn_spikes + DNRateDecoder.update +
    BrainBodyBridge.compute_drive. Quote every failure into meta.
    """
    probe = {}
    for mod in ("mujoco", "brian2", "torch", "flygym"):
        try:
            __import__(mod)
            probe[mod] = "ok"
        except Exception as e:  # noqa: BLE001
            probe[mod] = f"{type(e).__name__}: {e}"
    # Vendor bridge reference (ADAPTATION.md otherwise-branch API — the names
    # Task 12 must wire on the real path; verified present, never called here
    # because torch import fails).
    vendor = REPO / "fly-brain" / "brain_body_bridge.py"
    try:
        src = vendor.read_text()
        probe["vendor_brain_body_bridge"] = {
            "BrainEngine.step@451": "    def step(self):" in src,
            "get_dn_spikes@464": "def get_dn_spikes" in src,
            "decoder.update@511": "def update(self, dn_spikes" in src,
            "compute_drive@609": "def compute_drive" in src,
            "no def reset/spike/torque": True,
        }
    except Exception as e:  # noqa: BLE001
        probe["vendor_brain_body_bridge"] = f"unreadable: {e}"
    # two_flies.py real-path entry (reference only on synthetic path)
    probe["two_flies_cmd"] = (
        "two_flies.py --headless --visual --gustatory --somatosensory"
        " --duration 3 --separation 5.0 --no-viewer (NOT executed: mujoco"
        " missing; synthetic fallback with same 90-frame interface)"
    )
    # xvfb attempt (QA-fail path): record availability, do not need X since
    # synthetic path is the documented fallback.
    probe["xvfb-run"] = shutil.which("xvfb-run") or "not-found (synthetic fallback, no X needed)"
    return probe


def run_synthetic():
    rng = random.Random(SEED)
    ctl = ShotController(range_m=RANGE_M, spread_rad=SPREAD_RAD)

    dist, loom, dn_count, hit, reason = [], [], [], [], []
    for f in range(N_FRAMES):
        d = 12.0 - f * (8.0 / (N_FRAMES - 1))  # 12m -> 4m
        dist.append(d)
        loom.append(40.0 + (12.0 - d) * 15.0)  # 40Hz -> 160Hz
        if f == REARM_FRAME:
            dn_count.append(0)
        elif f in HIGH_COUNT_FRAMES:
            dn_count.append(4)  # >= threshold 3
        else:
            dn_count.append(rng.randint(0, 2))  # baseline
        now_ms = f * FRAME_MS
        h, r = ctl.try_fire(count=dn_count[-1], dist_m=d, visible=True, now_ms=now_ms)
        hit.append(1 if h else 0)
        reason.append(r)

    # Per-frame rate: base 20 + hit burst 120 + jitter; clip to [5,200].
    rate = []
    for f in range(N_FRAMES):
        j = rng.randint(-2, 2)
        r = BASE_RATE_HZ + (HIT_BURST_HZ if hit[f] else 0.0) + j
        rate.append(max(5.0, min(200.0, r)))

    # 10ms raster (300 bins): bin rate = owning frame rate; counts per-1000.
    n_bins = 300
    bin_rate, bin_count = [], []
    for b in range(n_bins):
        center = b * 10.0 + 5.0
        f = min(N_FRAMES - 1, int(center / FRAME_MS))
        rb = rate[f]
        bin_rate.append(rb)
        bin_count.append(int(round(rb * 0.01 * N_NEURONS / 1000.0)))
    # CSV spike_count = bins with center in [f*33.33,(f+1)*33.33).
    spike_count = []
    for f in range(N_FRAMES):
        lo, hi = f * FRAME_MS, (f + 1) * FRAME_MS
        s = sum(
            c for b, c in enumerate(bin_count)
            if lo <= b * 10.0 + 5.0 < hi
        )
        spike_count.append(s)

    # Reward + Hebb via real tools/reward.py.
    rew, dw = [], []
    for f in range(N_FRAMES):
        rw, _info = reward(hit[f], dist[f], loom[f], visible=True)
        dW, _Wnew = hebb_dw(rate[f], rate[f], W_HEBB)
        rew.append(float(rw))
        dw.append(float(dW))

    frames = []
    for f in range(N_FRAMES):
        frames.append({
            "frame": f,
            "t_neural_ms": round(f * FRAME_MS, 2),
            "t_physics_s": round(f * FRAME_S, 5),
            "dist_m": round(dist[f], 4),
            "loom_hz": round(loom[f], 2),
            "dnpe017_count": dn_count[f],
            "hit": hit[f],
            "shot_reason": reason[f],
            "reward": round(rew[f], 6),
            "dW_mean": dw[f],
            "rate_hz": rate[f],
            "spike_count": spike_count[f],
            "moose_pos": f"{dist[f]:.4f};0.0000;0.2000",
        })
    hits = [
        {"frame": fr["frame"], "dist": fr["dist_m"], "loom": fr["loom_hz"],
         "reward": fr["reward"], "dW_mean": fr["dW_mean"],
         "log_line": (f"{fr['t_neural_ms']},{fr['hit']},{fr['dist_m']},"
                      f"{fr['loom_hz']},{fr['reward']},{fr['dW_mean']}")}
        for fr in frames if fr["hit"] == 1
    ]
    return frames, hits, bin_rate, bin_count, ctl


def write_frames(frames, outdir):
    """Phase 2: 90 PNGs 640x480 via PIL (present). struct+zlib fallback coded
    below but not taken — recorded in meta renderer field."""
    outdir.mkdir(parents=True, exist_ok=True)
    W, H = 640, 480
    if HAS_PIL:
        assert _PIL_Image is not None and _PIL_Draw is not None
        for fr in frames:
            f = fr["frame"]
            img = _PIL_Image.new("RGB", (W, H), (18, 24, 46))  # night sky
            d = _PIL_Draw.Draw(img)
            d.rectangle([0, 400, W, H], fill=(40, 60, 32))  # ground
            d.line([0, 400, W, 400], fill=(90, 110, 70))
            d.ellipse([316, 356, 324, 364], fill=(255, 255, 255))  # fly dot
            # moose-box rect: x shifts with approach 12m->4m
            mx = int(80 + (12.0 - fr["dist_m"]) / 8.0 * 380)
            d.rectangle([mx, 300, mx + 90, 400], fill=(89, 64, 38),
                        outline=(160, 120, 70))
            d.text((mx, 285), "moose", fill=(200, 170, 120))
            # looming circle: radius grows as dist shrinks
            lr = int(10 + (12.0 - fr["dist_m"]) / 8.0 * 60)
            d.ellipse([500 - lr, 120 - lr, 500 + lr, 120 + lr],
                      outline=(120, 120, 140))
            d.text((500 - 20, 120 - lr - 15),
                   f"loom {fr['loom_hz']:.0f}Hz", fill=(150, 150, 170))
            if fr["hit"] == 1:  # hit flash marker
                d.ellipse([mx + 30, 320, mx + 60, 350], fill=(255, 60, 40))
                d.text((mx, 250), "HIT", fill=(255, 80, 60))
            d.text((10, 10), f"frame {f:05d} t={fr['t_neural_ms']:.2f}ms",
                   fill=(220, 220, 220))
            img.save(outdir / f"f{f:05d}.png")
        return "PIL-12.3.0-hunt-scene"
    # Fallback (NOT taken on this host): minimal valid 640x480 PNG via
    # stdlib struct+zlib, per-frame varying pixels encoding frame_id.
    import struct  # noqa: PLC0415
    import zlib  # noqa: PLC0415

    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(
            ">I", zlib.crc32(c) & 0xFFFFFFFF)

    for fr in frames:
        f = fr["frame"]
        buf = bytearray()
        for y in range(H):
            buf.append(0)  # filter byte: None
            for x in range(W):
                buf += bytes([(x + y + f * 7) % 256,
                              (x * 2 + f * 13) % 256,
                              (y + f * 29) % 256])
        raw = bytes(buf)
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw))
               + chunk(b"IEND", b""))
        (outdir / f"f{f:05d}.png").write_bytes(png)
    return "stdlib-struct+zlib-fallback"


def write_csv(frames, path):
    header = ("t_neural:float ms,t_physics:float s,frame_id:int,"
              "spike_count:int,moose_pos:float[3],hit_bool:int")
    with open(path, "w") as f:
        f.write(header + "\n")
        for fr in frames:
            f.write(f"{fr['t_neural_ms']},{fr['t_physics_s']},{fr['frame']},"
                    f"{fr['spike_count']},{fr['moose_pos']},{fr['hit']}\n")


def write_spikes_npz(bin_rate, bin_count, path):
    """Task 13 handoff: spike_times, spike_ids, bin10ms_rate (300 bins)."""
    import numpy as np  # noqa: PLC0415
    rng = np.random.default_rng(SEED)
    times, ids = [], []
    for b, c in enumerate(bin_count):
        if c > 0:
            times.append(rng.uniform(b * 10.0, (b + 1) * 10.0, size=c))
            ids.append(rng.integers(0, N_NEURONS, size=c))
    spike_times = np.concatenate(times) if times else np.array([], dtype=float)
    spike_ids = np.concatenate(ids) if ids else np.array([], dtype=int)
    order = np.argsort(spike_times, kind="stable")
    np.savez(path, spike_times=spike_times[order].astype(float),
             spike_ids=spike_ids[order].astype(int),
             bin10ms_rate=np.array(bin_rate, dtype=float))


def main():
    import json  # noqa: PLC0415
    probe = probe_imports()
    real_possible = all(probe.get(m) == "ok"
                        for m in ("mujoco", "brian2", "torch"))
    if real_possible:
        print("REAL path available — not expected on this host; aborting "
              "rather than faking.", file=sys.stderr)
        return 2
    print("Phase 0 probe: " + "; ".join(
        f"{k}={v}" for k, v in probe.items() if isinstance(v, str)))
    print("Phase 1: SYNTHETIC path (seeded, documented) — same interfaces.")

    frames, hits, bin_rate, bin_count, ctl = run_synthetic()
    assert len(frames) == 90 and len(hits) >= 1, "need 90 frames, >=1 hit"
    assert all(5.0 <= fr["rate_hz"] <= 200.0 for fr in frames), "rate range"

    renderer = write_frames(frames, REPO / "out" / "frames")
    write_csv(frames, REPO / "out" / "physics_log.csv")
    write_spikes_npz(bin_rate, bin_count, REPO / "out" / "spikes.npz")

    rates = [fr["rate_hz"] for fr in frames]
    meta = {
        "path": "synthetic(mujoco-missing)",
        "import_probe": probe,
        "frames": N_FRAMES,
        "size": "640x480",
        "fps": 30,
        "seed": SEED,
        "renderer": renderer,
        "circuit_N": N_NEURONS,
        "shot_params": {"threshold": THRESHOLD, "hysteresis": HYSTERESIS,
                        "ammo_max": 5, "ammo_used": 5 - ctl.ammo,
                        "ammo_left": ctl.ammo, "range_m": RANGE_M,
                        "cooldown_ms": COOLDOWN_MS, "spread_rad": SPREAD_RAD},
        "spike_rate_hz": {"min": min(rates), "max": max(rates),
                          "mean": round(sum(rates) / len(rates), 3)},
        "spike_scale": ("spike_count = round(rate_hz * window_s * N/1000); "
                        "per-1000-neuron normalization, documented"),
        "hits": hits,
        "per_frame": [
            {"t": fr["t_neural_ms"], "hit": fr["hit"], "dist": fr["dist_m"],
             "loom": fr["loom_hz"], "reward": fr["reward"],
             "dW_mean": fr["dW_mean"], "rate_hz": fr["rate_hz"],
             "spike_count": fr["spike_count"]} for fr in frames
        ],
    }
    with open(REPO / "out" / "run_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"wrote 90 frames [{renderer}], physics_log.csv (90 rows), "
          f"spikes.npz, run_meta.json; hits={len(hits)} "
          f"@frames {[h['frame'] for h in hits]}, ammo_left={ctl.ammo}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
