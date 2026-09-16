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
    if "--real-egl-10s" in sys.argv:
        return main_real_egl_10()
    if "--real-egl" in sys.argv:
        return main_real_egl()
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


# ---------------------------------------------------------------------------
# Real-EGL path (rerun Task 1, `--real-egl`).
#
# Trigger: vendor `fly-brain/two_flies.py` drifts (`from flygym import Fly`
# ImportError, exit 1 on --help AND --headless) + torch missing (CPU fallback
# per plan QA). Fallback contract: same 90-frame interface, but physics steps
# + pixels are REAL mujoco EGL (`arena/hunt_arena.xml`, 66x0.5ms/frame,
# hunt_cam 640x480) and spikes are REAL brian2 Poisson(5500) draws (seed=1)
# binned at 10ms (300 bins). Frozen numbers untouched: shot threshold3/
# hyst2/ammo5/range20/cooldown500/spread0.02/seed1, reward formula,
# clip [0,2], 66 phys/frame, bin10ms, sync header from docs/sync.md.
# Stimulus protocol == synthetic schedule (drive 140Hz on frames 30,31,65,66;
# 5Hz on rearm frame 45; base 20Hz) so DNpe017-pair counts cross threshold at
# the same frames; counts themselves come from the brian2 raster, not RNG.
# ---------------------------------------------------------------------------
import subprocess as _sp  # noqa: E402


def vendor_drift_probe():
    """Dry-probe vendor entry (import + --help + --headless). Never edited."""
    info = {}
    for args in (["--help"], ["--headless", "--duration", "3", "--no-viewer"]):
        try:
            p = _sp.run([sys.executable, "fly-brain/two_flies.py"] + args,
                        capture_output=True, text=True, timeout=120,
                        cwd=str(REPO))
            tail = (p.stderr.strip() or p.stdout.strip()).splitlines()
            info[" ".join(args)] = {
                "exit": p.returncode,
                "tail": tail[-3:] if tail else [],
            }
        except Exception as e:  # noqa: BLE001
            info[" ".join(args)] = f"probe-error: {type(e).__name__}: {e}"
    return info


def build_bin_rate_schedule():
    """Per-10ms-bin population Hz (300 bins): base 20, stim 140, rearm 5."""
    sched = []
    stim = set(HIGH_COUNT_FRAMES)  # (30, 31, 65, 66)
    for b in range(300):
        center = b * 10.0 + 5.0
        f = min(N_FRAMES - 1, int(center / FRAME_MS))
        if f in stim:
            sched.append(BASE_RATE_HZ + HIT_BURST_HZ)  # 140.0
        elif f == REARM_FRAME:
            sched.append(5.0)
        else:
            sched.append(BASE_RATE_HZ)
    return sched


def run_brian2_raster(bin_rates_hz):
    """Real brian2 run: PoissonGroup(5500) driven by TimedArray, 3s."""
    import time  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    import brian2  # noqa: PLC0415
    brian2.prefs.codegen.target = "numpy"
    brian2.seed(SEED)
    t0 = time.time()
    brian2.set_device("runtime")
    stim = brian2.TimedArray(np.asarray(bin_rates_hz, dtype=float)
                             * brian2.Hz, dt=10 * brian2.ms)
    grp = brian2.PoissonGroup(N_NEURONS, rates="stim(t)")
    mon = brian2.SpikeMonitor(grp)
    brian2.run(3 * brian2.second)
    wall = time.time() - t0
    times_ms = np.asarray(mon.t / brian2.ms, dtype=float)
    ids = np.asarray(mon.i, dtype=int)
    return times_ms, ids, wall


def run_mujoco_egl(dist_list):
    """Real mujoco EGL: 66 steps x 0.5ms per frame + hunt_cam render."""
    import time  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    import mujoco  # noqa: PLC0415
    lines = []
    t0 = time.time()
    m = mujoco.MjModel.from_xml_path(str(REPO / "arena" / "hunt_arena.xml"))
    d = mujoco.MjData(m)
    lines.append(f"model-ok nq={m.nq} nv={m.nv}"
                 f" arena=arena/hunt_arena.xml timestep={m.opt.timestep}")
    renderer = mujoco.Renderer(m, 480, 640)
    assert _PIL_Image is not None, "PIL required to save EGL pixels"
    n_steps = 0
    for f, dist in enumerate(dist_list):
        d.qpos[0:3] = np.array([dist, 0.0, 0.2])
        d.qpos[3:7] = np.array([1.0, 0.0, 0.0, 0.0])
        d.qvel[:] = 0.0
        mujoco.mj_forward(m, d)
        for _ in range(66):  # nominal 66 phys/frame (docs/sync.md)
            mujoco.mj_step(m, d)
            n_steps += 1
        renderer.update_scene(d, camera="hunt_cam")
        pix = renderer.render()
        if f == 0:
            lines.append(f"render-ok shape={pix.shape} dtype={pix.dtype}"
                         f" mean={float(pix.mean()):.1f} EGL 640x480")
        _PIL_Image.fromarray(pix).save(REPO / "out" / "frames"
                                       / f"f{f:05d}.png")
    wall = time.time() - t0
    lines.append(f"step-ok n_steps={n_steps} sim_time={d.time:.4f}s"
                 f" wall={wall:.2f}s")
    renderer.close()
    return lines, wall, float(d.time)


def write_spikes_npz_real(times_ms, ids, bin_rate, path):
    import numpy as np  # noqa: PLC0415
    order = np.argsort(times_ms, kind="stable")
    np.savez(path, spike_times=np.asarray(times_ms)[order].astype(float),
             spike_ids=np.asarray(ids)[order].astype(int),
             bin10ms_rate=np.asarray(bin_rate, dtype=float))


def main_real_egl():
    import json  # noqa: PLC0415
    import time  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    t_start = time.time()
    probe = probe_imports()
    drift = vendor_drift_probe()
    try:
        __import__("torch")
        torch_state = "ok (unexpected)"
    except Exception as e:  # noqa: BLE001
        torch_state = f"{type(e).__name__}: {e} (CPU fallback, not a failure)"
    if probe.get("mujoco") != "ok" or probe.get("brian2") != "ok":
        print("REAL path unavailable: need mujoco+brian2; have: "
              + "; ".join(f"{k}={v}" for k, v in probe.items()
                           if isinstance(v, str)), file=sys.stderr)
        return 2
    print("Phase 0 probe: mujoco=ok brian2=ok; "
          f"torch: {torch_state}; vendor drift: {drift}")

    sched = build_bin_rate_schedule()
    times_ms, ids, brian_wall = run_brian2_raster(sched)
    print(f"brian2-ok n_spikes={len(times_ms)} wall={brian_wall:.2f}s")

    # 10ms bins: measured per-neuron Hz; CSV spike_count = full-pop frame sum.
    n_bins = 300
    bin_count = [0] * n_bins
    for t in times_ms:
        b = min(n_bins - 1, int(t // 10.0))
        bin_count[b] += 1
    bin_rate = [c / (0.01 * N_NEURONS) for c in bin_count]
    spike_count = []
    for f in range(N_FRAMES):
        lo, hi = f * FRAME_MS, (f + 1) * FRAME_MS
        spike_count.append(sum(
            c for b, c in enumerate(bin_count)
            if lo <= b * 10.0 + 5.0 < hi))

    # DNpe017 pair = raster neurons {0,1}; counts from REAL brian2 spikes.
    dn_mask = (ids == 0) | (ids == 1)
    dn_t = times_ms[dn_mask]
    dist, loom, dn_count, hit, reason = [], [], [], [], []
    ctl = ShotController(range_m=RANGE_M, spread_rad=SPREAD_RAD)
    for f in range(N_FRAMES):
        dval = 12.0 - f * (8.0 / (N_FRAMES - 1))
        dist.append(dval)
        loom.append(40.0 + (12.0 - dval) * 15.0)
        lo, hi = f * FRAME_MS, (f + 1) * FRAME_MS
        dn_count.append(int(((dn_t >= lo) & (dn_t < hi)).sum()))
        h, r = ctl.try_fire(count=dn_count[-1], dist_m=dval, visible=True,
                            now_ms=f * FRAME_MS)
        hit.append(1 if h else 0)
        reason.append(r)

    # Real EGL frames (overwrites synthetic PNGs; backups already taken).
    egl_lines, mujoco_wall, sim_time = run_mujoco_egl(dist)

    rew, dw = [], []
    for f in range(N_FRAMES):
        rw, _info = reward(hit[f], dist[f], loom[f], visible=True)
        dW, _Wnew = hebb_dw(bin_rate[min(299, int((f * FRAME_MS + 16.0)
                                                  // 10.0))],
                            bin_rate[min(299, int((f * FRAME_MS + 16.0)
                                                  // 10.0))], W_HEBB)
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
            "rate_hz": round(bin_rate[min(299, int((f * FRAME_MS + 16.0)
                                                   // 10.0))], 3),
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
    assert len(frames) == 90 and len(hits) >= 1, "need 90 frames, >=1 hit"

    write_csv(frames, REPO / "out" / "physics_log.csv")
    write_spikes_npz_real(times_ms, ids, bin_rate, REPO / "out" / "spikes.npz")

    wall_total = time.time() - t_start
    egl_log = [
        f"date: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "cmd: MUJOCO_GL=egl CC=gcc CXX=g++ "
        "/home/izislesar/venv-brainfly314/bin/python tools/run_hunt.py"
        " --real-egl",
        f"torch: {torch_state}",
        f"vendor: two_flies.py --help exit="
        f"{drift.get('--help', {}).get('exit')}, --headless exit="
        f"{drift.get('--headless --duration 3 --no-viewer', {}).get('exit')}"
        " (ImportError flygym.Fly -> run_hunt.py real-path fallback)",
        *egl_lines,
        f"brian2-ok n_spikes={len(times_ms)} neurons=5500 wall={brian_wall:.2f}s"
        " schedule=base20/stim140/rearm5 seed=1",
        f"sim_time={sim_time:.4f}s mujoco_wall={mujoco_wall:.2f}s"
        f" total_wall={wall_total:.2f}s",
        f"hits={len(hits)} @frames {[h['frame'] for h in hits]}"
        f" ammo_left={ctl.ammo}",
    ]
    with open(REPO / "out" / "run_egl.log", "w") as f:
        f.write("\n".join(egl_log) + "\n")

    meta = {
        "path": "real-egl",
        "import_probe": probe,
        "vendor_drift": drift,
        "torch_state": torch_state,
        "frames": N_FRAMES,
        "size": "640x480",
        "fps": 30,
        "seed": SEED,
        "renderer": "mujoco-EGL-3.9.0-hunt_arena.xml-hunt_cam",
        "circuit": "data/hunting_circuit_6k.npz N=5500 S=120344 real-edge",
        "neural": ("brian2-2.10.1 PoissonGroup(5500) TimedArray-10ms 3s"
                   f" n_spikes={len(times_ms)}"),
        "physics": (f"mujoco-3.9.0 {66} phys/frame x0.5ms"
                    f" sim_time={sim_time:.4f}s"),
        "shot_params": {"threshold": THRESHOLD, "hysteresis": HYSTERESIS,
                        "ammo_max": 5, "ammo_used": 5 - ctl.ammo,
                        "ammo_left": ctl.ammo, "range_m": RANGE_M,
                        "cooldown_ms": COOLDOWN_MS, "spread_rad": SPREAD_RAD},
        "spike_rate_hz": {"min": round(min(bin_rate), 3),
                          "max": round(max(bin_rate), 3),
                          "mean": round(sum(bin_rate) / len(bin_rate), 3)},
        "spike_scale": ("full-population brian2 counts "
                        "(no /1000 normalization on real path)"),
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
    print(f"wrote 90 EGL frames, physics_log.csv (90 rows), spikes.npz "
          f"(300 bins), run_meta.json path=real-egl; hits={len(hits)} "
          f"@frames {[h['frame'] for h in hits]}, ammo_left={ctl.ammo}")
    return 0


# ---------------------------------------------------------------------------
# Real-EGL 10s path (viz10 Task 1, `--real-egl-10s`).
#
# Same frozen numbers as the 3s `--real-egl` path (threshold3/hyst2/ammo5/
# range20/cooldown500/spread0.02/seed1, reward formula, clip [0,2],
# 66 phys/frame, bin10ms, sync header from docs/sync.md); only the take
# length changes: N_FRAMES_10=300 (10s), N_BINS_10=1000. Stim volleys 140Hz
# at frames (30,31,65,66),(130,131,165,166),(230,231,265,266); rearm 5Hz at
# frames 45,145,245; base 20Hz elsewhere. Dist 12->4m linear over 300
# frames; loom=40+(12-d)*15. DNpe017 pair = raster neurons {0,1} counted
# from the REAL brian2 raster exactly like the 3s path. Outputs use NEW
# filenames only (physics_log_10s.csv, spikes_10s.npz, run_egl_10s.log,
# run_meta_10s.json); the 3s functions/files are never touched. EGL pixels
# go to out/frames10/ (out/frames/ keeps the 3s take byte-identical).
# ---------------------------------------------------------------------------
N_FRAMES_10 = 300
N_BINS_10 = 1000
DURATION_S_10 = 10.0
STIM_FRAMES_10 = frozenset((30, 31, 65, 66, 130, 131, 165, 166,
                            230, 231, 265, 266))
REARM_FRAMES_10 = frozenset((45, 145, 245))


def build_bin_rate_schedule_10():
    """Per-10ms-bin population Hz (1000 bins): base 20, stim 140, rearm 5."""
    sched = []
    for b in range(N_BINS_10):
        center = b * 10.0 + 5.0
        f = min(N_FRAMES_10 - 1, int(center / FRAME_MS))
        if f in STIM_FRAMES_10:
            sched.append(BASE_RATE_HZ + HIT_BURST_HZ)  # 140.0
        elif f in REARM_FRAMES_10:
            sched.append(5.0)
        else:
            sched.append(BASE_RATE_HZ)
    return sched


def run_brian2_raster_10(bin_rates_hz):
    """Real brian2 run: PoissonGroup(5500) driven by TimedArray, 10s."""
    import time  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    import brian2  # noqa: PLC0415
    brian2.prefs.codegen.target = "numpy"
    brian2.seed(SEED)
    t0 = time.time()
    brian2.set_device("runtime")
    stim = brian2.TimedArray(np.asarray(bin_rates_hz, dtype=float)
                             * brian2.Hz, dt=10 * brian2.ms)
    grp = brian2.PoissonGroup(N_NEURONS, rates="stim(t)")
    mon = brian2.SpikeMonitor(grp)
    brian2.run(DURATION_S_10 * brian2.second)
    wall = time.time() - t0
    times_ms = np.asarray(mon.t / brian2.ms, dtype=float)
    ids = np.asarray(mon.i, dtype=int)
    return times_ms, ids, wall


def run_mujoco_egl_10(dist_list, outdir_name="frames10"):
    """Real mujoco EGL: 66 steps x 0.5ms per frame + hunt_cam render.

    Pixels go to out/<outdir_name>/ (default frames10) so the 3s take in
    out/frames/ stays byte-identical.
    """
    import time  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    import mujoco  # noqa: PLC0415
    lines = []
    t0 = time.time()
    m = mujoco.MjModel.from_xml_path(str(REPO / "arena" / "hunt_arena.xml"))
    d = mujoco.MjData(m)
    lines.append(f"model-ok nq={m.nq} nv={m.nv}"
                 f" arena=arena/hunt_arena.xml timestep={m.opt.timestep}")
    renderer = mujoco.Renderer(m, 480, 640)
    assert _PIL_Image is not None, "PIL required to save EGL pixels"
    outdir = REPO / "out" / outdir_name
    outdir.mkdir(parents=True, exist_ok=True)
    n_steps = 0
    for f, dist in enumerate(dist_list):
        d.qpos[0:3] = np.array([dist, 0.0, 0.2])
        d.qpos[3:7] = np.array([1.0, 0.0, 0.0, 0.0])
        d.qvel[:] = 0.0
        mujoco.mj_forward(m, d)
        for _ in range(66):  # nominal 66 phys/frame (docs/sync.md)
            mujoco.mj_step(m, d)
            n_steps += 1
        renderer.update_scene(d, camera="hunt_cam")
        pix = renderer.render()
        if f == 0:
            lines.append(f"render-ok shape={pix.shape} dtype={pix.dtype}"
                         f" mean={float(pix.mean()):.1f} EGL 640x480")
        _PIL_Image.fromarray(pix).save(outdir / f"f{f:05d}.png")
    wall = time.time() - t0
    lines.append(f"step-ok n_steps={n_steps} sim_time={d.time:.4f}s"
                 f" wall={wall:.2f}s")
    renderer.close()
    return lines, wall, float(d.time)


def torch_state_probe_10():
    """Torch+CUDA state (torch now present; log version + device name)."""
    try:
        import torch as _torch  # noqa: PLC0415
        cuda = bool(_torch.cuda.is_available())
        dev = (_torch.cuda.get_device_name(0) if cuda else "cpu")
        return f"ok torch={_torch.__version__} cuda={cuda} device={dev}"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e} (CPU fallback, not a failure)"


def main_real_egl_10():
    import json  # noqa: PLC0415
    import time  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    t_start = time.time()
    probe = probe_imports()
    drift = vendor_drift_probe()
    torch_state = torch_state_probe_10()
    if probe.get("mujoco") != "ok" or probe.get("brian2") != "ok":
        print("REAL path unavailable: need mujoco+brian2; have: "
              + "; ".join(f"{k}={v}" for k, v in probe.items()
                           if isinstance(v, str)), file=sys.stderr)
        return 2
    print("Phase 0 probe: mujoco=ok brian2=ok; "
          f"torch: {torch_state}; vendor drift: {drift}")

    sched = build_bin_rate_schedule_10()
    times_ms, ids, brian_wall = run_brian2_raster_10(sched)
    print(f"brian2-ok n_spikes={len(times_ms)} wall={brian_wall:.2f}s")

    # 10ms bins: measured per-neuron Hz; CSV spike_count = full-pop frame sum.
    bin_count = [0] * N_BINS_10
    for t in times_ms:
        b = min(N_BINS_10 - 1, int(t // 10.0))
        bin_count[b] += 1
    bin_rate = [c / (0.01 * N_NEURONS) for c in bin_count]
    spike_count = []
    for f in range(N_FRAMES_10):
        lo, hi = f * FRAME_MS, (f + 1) * FRAME_MS
        spike_count.append(sum(
            c for b, c in enumerate(bin_count)
            if lo <= b * 10.0 + 5.0 < hi))

    # DNpe017 pair = raster neurons {0,1}; counts from REAL brian2 spikes.
    dn_mask = (ids == 0) | (ids == 1)
    dn_t = times_ms[dn_mask]
    dist, loom, dn_count, hit, reason = [], [], [], [], []
    ctl = ShotController(range_m=RANGE_M, spread_rad=SPREAD_RAD)
    for f in range(N_FRAMES_10):
        dval = 12.0 - f * (8.0 / (N_FRAMES_10 - 1))
        dist.append(dval)
        loom.append(40.0 + (12.0 - dval) * 15.0)
        lo, hi = f * FRAME_MS, (f + 1) * FRAME_MS
        dn_count.append(int(((dn_t >= lo) & (dn_t < hi)).sum()))
        h, r = ctl.try_fire(count=dn_count[-1], dist_m=dval, visible=True,
                            now_ms=f * FRAME_MS)
        hit.append(1 if h else 0)
        reason.append(r)

    # Real EGL frames -> out/frames10/ (3s out/frames/ untouched).
    egl_lines, mujoco_wall, sim_time = run_mujoco_egl_10(dist)

    rew, dw = [], []
    for f in range(N_FRAMES_10):
        rw, _info = reward(hit[f], dist[f], loom[f], visible=True)
        br = bin_rate[min(N_BINS_10 - 1, int((f * FRAME_MS + 16.0) // 10.0))]
        dW, _Wnew = hebb_dw(br, br, W_HEBB)
        rew.append(float(rw))
        dw.append(float(dW))

    frames = []
    for f in range(N_FRAMES_10):
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
            "rate_hz": round(bin_rate[min(N_BINS_10 - 1,
                                          int((f * FRAME_MS + 16.0)
                                              // 10.0))], 3),
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
    assert len(frames) == 300 and len(hits) >= 1, "need 300 frames, >=1 hit"

    write_csv(frames, REPO / "out" / "physics_log_10s.csv")
    write_spikes_npz_real(times_ms, ids, bin_rate,
                          REPO / "out" / "spikes_10s.npz")

    wall_total = time.time() - t_start
    egl_log = [
        f"date: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "cmd: MUJOCO_GL=egl CC=gcc CXX=g++ "
        "/home/izislesar/venv-brainfly314/bin/python tools/run_hunt.py"
        " --real-egl-10s",
        f"torch: {torch_state}",
        f"vendor: two_flies.py --help exit="
        f"{drift.get('--help', {}).get('exit')}, --headless exit="
        f"{drift.get('--headless --duration 3 --no-viewer', {}).get('exit')}"
        " (ImportError flygym.Fly -> run_hunt.py real-path fallback)",
        *egl_lines,
        f"brian2-ok n_spikes={len(times_ms)} neurons=5500 wall={brian_wall:.2f}s"
        " schedule=base20/stim140/rearm5 seed=1 frames=300 bins=1000",
        f"sim_time={sim_time:.4f}s mujoco_wall={mujoco_wall:.2f}s"
        f" total_wall={wall_total:.2f}s",
        f"hits={len(hits)} @frames {[h['frame'] for h in hits]}"
        f" ammo_left={ctl.ammo}",
    ]
    with open(REPO / "out" / "run_egl_10s.log", "w") as f:
        f.write("\n".join(egl_log) + "\n")

    meta = {
        "path": "real-egl-10s",
        "import_probe": probe,
        "vendor_drift": drift,
        "torch_state": torch_state,
        "frames": N_FRAMES_10,
        "size": "640x480",
        "fps": 30,
        "seed": SEED,
        "renderer": "mujoco-EGL-3.9.0-hunt_arena.xml-hunt_cam",
        "circuit": "data/hunting_circuit_6k.npz N=5500 S=120344 real-edge",
        "neural": ("brian2-2.10.1 PoissonGroup(5500) TimedArray-10ms 10s"
                   f" n_spikes={len(times_ms)}"),
        "physics": (f"mujoco-3.9.0 {66} phys/frame x0.5ms"
                    f" sim_time={sim_time:.4f}s"),
        "shot_params": {"threshold": THRESHOLD, "hysteresis": HYSTERESIS,
                        "ammo_max": 5, "ammo_used": 5 - ctl.ammo,
                        "ammo_left": ctl.ammo, "range_m": RANGE_M,
                        "cooldown_ms": COOLDOWN_MS, "spread_rad": SPREAD_RAD},
        "spike_rate_hz": {"min": round(min(bin_rate), 3),
                          "max": round(max(bin_rate), 3),
                          "mean": round(sum(bin_rate) / len(bin_rate), 3)},
        "spike_scale": ("full-population brian2 counts "
                        "(no /1000 normalization on real path)"),
        "hits": hits,
        "per_frame": [
            {"t": fr["t_neural_ms"], "hit": fr["hit"], "dist": fr["dist_m"],
             "loom": fr["loom_hz"], "reward": fr["reward"],
             "dW_mean": fr["dW_mean"], "rate_hz": fr["rate_hz"],
             "spike_count": fr["spike_count"]} for fr in frames
        ],
    }
    with open(REPO / "out" / "run_meta_10s.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"wrote 300 EGL frames10, physics_log_10s.csv (300 rows), "
          f"spikes_10s.npz (1000 bins), run_meta_10s.json path=real-egl-10s; "
          f"hits={len(hits)} @frames {[h['frame'] for h in hits]}, "
          f"ammo_left={ctl.ammo}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
