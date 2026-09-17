"""C1 fly-eye PiP (hunt-clarity-pass Task 1): head-mounted doc camera, 300 frames.

Reuses the frozen duel pipeline (tools/fly_duel.py: build/tune/bind/render,
light v1, sky repaint, rifle prop) + the D2 take loom trajectory
(out/physics_log_10s.csv dist_m, same mapping as tools/fly_duel_full.py).
Static neutral fly pose; thorax convention fc.thorax_xpos (settled xyz
~[0.5, 0.0, 1.9] mm); heading yaw from fd.thorax_yaw. arena/hunt_arena.xml
and fly-brain/ are NEVER touched. No physics, camera-only.

Eye camera (logged): pos = live thorax + yaw-rotated HEAD_OFFSET
(fwd +2.0 mm, up +0.8 mm — head approx ahead/above thorax), target =
pos + horizontal-forward*4000 with z -= 60 (~0.86 deg downward tilt so
the ground reads in the lower frame), fovy=60. Faces +x heading toward
the moose box (5000,0,205) / loom axis.

Render: 1280x960 EGL -> LANCZOS 640x480 (fd.render_supersampled) ->
LANCZOS 160x120. Output out/flyeye/e%05d.png (gitignored, duel policy).

Usage: fly_eye.py [--probe N] [--start S --end E]
  --probe N   render single frame N to out/flyeye/probe_eye_N.png + stats
  default     render [start,end) of the 300-frame take to e%05d.png
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import fly_compose as fc  # noqa: E402
import fly_duel as fd  # noqa: E402  (frozen D1 pipeline, human-approved)

OUT = REPO / "out" / "flyeye"
EW, EH = 160, 120
EYE_FOVY = 60.0
HEAD_OFFSET = np.array([2.0, 0.0, 0.8])  # thorax-frame: fwd +2mm, up +0.8mm
AIM_DIST = 4000.0   # look-ahead distance along heading (mm)
AIM_DROP = 60.0     # downward tilt component (mm) ~0.86 deg
N_FRAMES = 300
SAMPLES = (0, 150, 299)
MOOSE_RGB = np.array([0.35, 0.25, 0.15]) * 255.0
BALL_RGB = np.array([0.05, 0.05, 0.08]) * 255.0


def load_take_dists() -> list:
    """dist_m per frame 0..299 (identical source+mapping as fly_duel_full)."""
    dists = []
    with open(REPO / "out" / "physics_log_10s.csv") as f:
        rdr = csv.reader(f)
        next(rdr)
        for row in rdr:
            dists.append(float(row[4].split(";")[0]))
    assert len(dists) == N_FRAMES, f"expected {N_FRAMES}, got {len(dists)}"
    return dists


def eye_pose(thorax: np.ndarray, yaw: float):
    """Eye pos + target from live thorax + heading yaw. Returns (pos, tgt)."""
    c, s = np.cos(yaw), np.sin(yaw)
    off = np.array([HEAD_OFFSET[0] * c - HEAD_OFFSET[1] * s,
                    HEAD_OFFSET[0] * s + HEAD_OFFSET[1] * c,
                    HEAD_OFFSET[2]])
    pos = thorax + off
    fwd = np.array([c, s, 0.0])
    tgt = pos + fwd * AIM_DIST
    tgt[2] -= AIM_DROP
    return pos, tgt


def frame_stats(pix: np.ndarray) -> dict:
    """Mean-color + edge + actor-fraction stats for the honest verdict."""
    f = pix.astype(float)
    mean = f.reshape(-1, 3).mean(axis=0)
    std = f.reshape(-1, 3).std(axis=0)
    uniq = len(np.unique(pix.reshape(-1, 3), axis=0))
    # Luminance gradient edge energy (Sobel-ish via np.gradient).
    lum = f[..., 0] * 0.299 + f[..., 1] * 0.587 + f[..., 2] * 0.114
    gy, gx = np.gradient(lum)
    edge = float(np.sqrt(gx ** 2 + gy ** 2).mean())
    edge_frac = float((np.sqrt(gx ** 2 + gy ** 2) > 12.0).mean())
    white = float((f.min(axis=2) > 245.0).mean())
    sky = float(((f[..., 2] > f[..., 0] + 20) & (f[..., 2] > 100)).mean())
    # Lit checker renders desaturated gray (~114,109,106), NOT raw green
    # albedo: ground = non-sky (B <= R+10 excludes steel-blue sky).
    ground = float((f[..., 2] <= f[..., 0] + 10).mean())
    moose = float((np.abs(f - MOOSE_RGB).max(axis=2) < 45.0).mean())
    ball = float((f.max(axis=2) < 45.0).mean())
    return {"mean": mean, "std": std, "uniq": uniq, "edge": edge,
            "edge_frac": edge_frac, "white": white, "sky": sky,
            "ground": ground, "moose": moose, "ball": ball}


def verdict(st: dict) -> str:
    """Honest readability verdict from stats (logged, never silent)."""
    bits = []
    if st["moose"] > 0.0005:
        bits.append(f"moose-box {st['moose']*100:.2f}%")
    if st["ball"] > 0.001:
        bits.append(f"dark-ball {st['ball']*100:.2f}%")
    if st["ground"] > 0.05:
        bits.append(f"ground {st['ground']*100:.1f}%")
    if st["sky"] > 0.05:
        bits.append(f"sky {st['sky']*100:.1f}%")
    seen = "+".join(bits) if bits else "NOTHING-RECOGNIZABLE"
    ok = (st["moose"] > 0.0005 or st["ball"] > 0.001
          or st["ground"] > 0.05) and st["sky"] < 0.95
    return f"{'READABLE' if ok else 'UNUSABLE'}({seen})"


def log_sample(tag, pix, path) -> dict:
    st = frame_stats(pix)
    md5 = hashlib.md5(Path(path).read_bytes()).hexdigest()
    print(f"sample={tag} shape={pix.shape[1]}x{pix.shape[0]} "
          f"mean=({st['mean'][0]:.1f},{st['mean'][1]:.1f},{st['mean'][2]:.1f}) "
          f"std=({st['std'][0]:.1f},{st['std'][1]:.1f},{st['std'][2]:.1f}) "
          f"uniq={st['uniq']} edge={st['edge']:.2f} "
          f"edgefrac={st['edge_frac']:.4f} white={st['white']:.4f} "
          f"sky={st['sky']:.3f} ground={st['ground']:.3f} "
          f"moose={st['moose']:.4f} ball={st['ball']:.4f} "
          f"verdict={verdict(st)} md5={md5[:12]}", flush=True)
    return st


def main():
    import mujoco
    import PIL.Image

    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", type=int, default=None)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=N_FRAMES)
    args = ap.parse_args()

    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    dists = load_take_dists()

    world, fly = fd.build_duel_scene()
    model, data = world.compile()
    fd.tune_duel_visuals(model)
    q_settled, fly_xyz = fc.settle_fly(model, data)
    print(f"fly-settled thorax_xyz_mm={np.round(fly_xyz, 2).tolist()}",
          flush=True)

    # Eye camera from the LIVE thorax + heading (rifle-binding convention).
    fd.place(model, data, q_settled)  # forward first: fresh thorax xpos
    thorax = fc.thorax_xpos(model, data)
    yaw = fd.thorax_yaw(model, data)
    epos, etgt = eye_pose(thorax, yaw)
    tilt = float(np.rad2deg(np.arctan2(epos[2] - etgt[2],
                                       np.linalg.norm(etgt[:2] - epos[:2]))))
    print(f"eye thorax={np.round(thorax, 2).tolist()} "
          f"yaw={np.rad2deg(yaw):.1f}deg pos={np.round(epos, 2).tolist()} "
          f"tgt={np.round(etgt, 2).tolist()} fovy={EYE_FOVY} "
          f"downtilt={tilt:.2f}deg headoff={HEAD_OFFSET.tolist()}",
          flush=True)
    fc.add_runtime_camera(world, "fly_eye", epos, etgt, EYE_FOVY)
    model2, data2 = world.compile()
    fd.tune_duel_visuals(model2)

    def render_frame(i):
        data2.qpos[:] = q_settled
        data2.mocap_pos[0] = [dists[i] * 1000.0, 0.0, fc.LOOM_Z]
        mujoco.mj_forward(model2, data2)
        bind = fd.bind_rifle(model2, data2)
        mujoco.mj_forward(model2, data2)
        big, pix640, flags = fd.render_supersampled(model2, data2, "fly_eye")
        assert big.shape == (fd.RH, fd.RW, 3), big.shape
        assert pix640.shape == (fc.H, fc.W, 3), pix640.shape
        small = np.asarray(
            PIL.Image.fromarray(pix640).resize((EW, EH), PIL.Image.LANCZOS))
        return small, flags, bind

    if args.probe is not None:
        i = args.probe
        small, flags, bind = render_frame(i)
        path = OUT / f"probe_eye_{i}.png"
        PIL.Image.fromarray(small).save(path)
        print(f"probe frame={i} flags={flags} bind={bind['dist']:.2f}mm "
              f"loom_x={dists[i]*1000.0:.0f}mm", flush=True)
        st = log_sample(f"probe{i}", small, path)
        print(f"probe-verdict frame={i} {verdict(st)} wall={time.time()-t0:.1f}s",
              flush=True)
        return

    assert 0 <= args.start < args.end <= N_FRAMES, (args.start, args.end)
    print(f"range=[{args.start},{args.end})", flush=True)
    samples = {}
    for i in range(args.start, args.end):
        small, flags, bind = render_frame(i)
        assert bind["dist"] < 10.0, f"prop detached frame {i}"
        path = OUT / f"e{i:05d}.png"
        PIL.Image.fromarray(small).save(path)
        if i in SAMPLES:
            samples[i] = log_sample(i, small, path) | {"flags": flags}
        elif i % 50 == 0:
            print(f"frame={i} bind={bind['dist']:.2f}mm", flush=True)

    # Determinism spot: rebuild + re-render sample 150 (EGL +-1 LSB caveat,
    # retry budget 4 — same gate form as D1/D2).
    spot = 150
    want = hashlib.md5((OUT / f"e{spot:05d}.png").read_bytes()).hexdigest()
    same, tries, pix_b = False, [], None
    import tempfile
    for _ in range(4):
        w_b, _ = fd.build_duel_scene()
        m0, d0 = w_b.compile()
        fd.tune_duel_visuals(m0)
        d0.qpos[:] = q_settled
        d0.mocap_pos[0] = [dists[spot] * 1000.0, 0.0, fc.LOOM_Z]
        mujoco.mj_forward(m0, d0)
        th_b = fc.thorax_xpos(m0, d0)
        # NOTE: thorax_yaw needs xmat -> forward already done above.
        yw_b = fd.thorax_yaw(m0, d0)
        ep_b, et_b = eye_pose(th_b, yw_b)
        fc.add_runtime_camera(w_b, "fly_eye", ep_b, et_b, EYE_FOVY)
        m_c, d_c = w_b.compile()
        fd.tune_duel_visuals(m_c)
        d_c.qpos[:] = q_settled
        d_c.mocap_pos[0] = [dists[spot] * 1000.0, 0.0, fc.LOOM_Z]
        mujoco.mj_forward(m_c, d_c)
        fd.bind_rifle(m_c, d_c)
        mujoco.mj_forward(m_c, d_c)
        _, pix640_b, _ = fd.render_supersampled(m_c, d_c, "fly_eye")
        pix_b = np.asarray(
            PIL.Image.fromarray(pix640_b).resize((EW, EH), PIL.Image.LANCZOS))
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            PIL.Image.fromarray(pix_b).save(tmp.name)
            got = hashlib.md5(open(tmp.name, "rb").read()).hexdigest()
        tries.append(got[:12])
        if got == want:
            same = True
            break
    dd = (np.asarray(PIL.Image.open(OUT / f"e{spot:05d}.png")).astype(int)
          - pix_b.astype(int))
    print(f"determinism eye150-rerender byte-identical={same} tries={tries} "
          f"last-nzdiff={int((dd != 0).any(axis=2).sum())} "
          f"last-maxabs={int(abs(dd).max())}", flush=True)

    ok = all(verdict(s).startswith("READABLE") for s in samples.values())
    print(f"GATES samples-readable:{ok} deterministic:{same} "
          f"n_files={len(list(OUT.glob('e*.png')))} wall={time.time()-t0:.1f}s",
          flush=True)
    if not (ok and same):
        sys.exit(2)


if __name__ == "__main__":
    main()
