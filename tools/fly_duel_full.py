"""D2 full take (Task 2, hunt-diorama-max): 300 duel EGL frames, D1-frozen pipeline.

Byte-for-byte reuse: build_duel_scene / tune_duel_visuals / bind_rifle /
render_supersampled / smoke_contacts / project_rifle_bbox / project_moose_bbox /
white_fraction / CAM_START / LOOM_STAGE / light+sky+rifle constants are ALL
imported from tools/fly_duel.py (Task 1, human-approved) — NOT copied here,
NOT retuned. arena/hunt_arena.xml and fly-brain/ are NEVER touched.

Only delta vs the probes: the loop runs 300 frames over the 10 s take, with
the loom mocap driven per-frame from out/physics_log_10s.csv dist_m
(identical take source + mapping as tools/fly_full.py); fly qpos = settled
snapshot every frame (the take fly is static, fly_full precedent); the duel
camera is computed by the IDENTICAL 40x convergence then frozen.

Output: out/duel/f%05d.png — 640x480 (1280x960 supersample, LANCZOS, shadows
ON). The 3 staging probes (probe_*.png) are never overwritten or deleted.
"""

from __future__ import annotations

import csv
import hashlib
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import fly_compose as fc  # noqa: E402
import fly_duel as fd  # noqa: E402  (Task 1 frozen pipeline, human-approved)
from fly_probe import measure_fly  # noqa: E402  (G2 bbox method, frozen)

OUT = REPO / "out" / "duel"
W, H = fc.W, fc.H  # 640 x 480 shipped frames
N_FRAMES = 300
SAMPLES = (0, 150, 299)
CROP_DUEL = 170  # probe_duel used crop=170 (non-stage branch)


def load_take_dists() -> list:
    """dist_m per frame 0..299 from the sim take CSV (moose_pos x-component)."""
    dists = []
    with open(REPO / "out" / "physics_log_10s.csv") as f:
        rdr = csv.reader(f)
        next(rdr)  # header carries type annotations; moose_pos is col 4
        for row in rdr:
            dists.append(float(row[4].split(";")[0]))
    assert len(dists) == N_FRAMES, f"expected {N_FRAMES} rows, got {len(dists)}"
    return dists


def main():
    import mujoco
    import PIL.Image

    # Resume support: `fly_duel_full.py [START [END]]` renders [START, END).
    # Same frozen pipeline, same take dists — missing frames only.
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else N_FRAMES
    assert 0 <= start < end <= N_FRAMES, (start, end)
    print(f"range=[{start},{end})", flush=True)

    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    dists = load_take_dists()

    world, fly = fd.build_duel_scene()
    model, data = world.compile()
    fd.tune_duel_visuals(model)
    print(f"model-ok nq={model.nq} nv={model.nv} ngeom={model.ngeom} "
          f"off={model.vis.global_.offwidth}x{model.vis.global_.offheight}",
          flush=True)
    q_settled, fly_xyz = fc.settle_fly(model, data)
    print(f"fly-settled thorax_xyz_mm={np.round(fly_xyz, 2).tolist()}",
          flush=True)

    # Contact smoke check (same gate as probes: prop visual-only).
    bind0 = fd.place(model, data, q_settled)
    smoke = fd.smoke_contacts(model, data)
    print(f"smoke rifle_barrel contype={smoke['rifle_barrel']['contype']} "
          f"conaff={smoke['rifle_barrel']['conaffinity']} "
          f"rifle_stock contype={smoke['rifle_stock']['contype']} "
          f"conaff={smoke['rifle_stock']['conaffinity']} ncon={smoke['ncon']}",
          flush=True)
    for _g in ("rifle_barrel", "rifle_stock", "rifle_receiver"):
        assert smoke[_g]["contype"] == 0
        assert smoke[_g]["conaffinity"] == 0

    # Cameras: IDENTICAL block to fly_duel.main (40x convergence + cams dict).
    # Only duel_duel is used for the take; the camera is then frozen.
    prev = fd.CAM_START.copy()
    for _ in range(40):
        prev = fc.track_camera(prev, fly_xyz, np.array([34.0, -26.0, 12.0]))
    face_pos = prev
    moose_xyz = np.array(fd.MOOSE_POS)
    moose_low = moose_xyz - np.array([0.0, 0.0, 200.0])  # moose base
    cams = {
        "stage": (fly_xyz + np.array([-58.0, -6.5, 11.5]), moose_xyz, 45.0),
        "face": (face_pos, fly_xyz, 20.0),
        "duel": (fly_xyz + np.array([-38.0, -5.0, 4.0]), moose_low, 32.0),
    }
    for cname, (pos, tgt, fovy) in cams.items():
        fc.add_runtime_camera(world, f"duel_{cname}", pos, tgt, fovy)
    model2, data2 = world.compile()
    fd.tune_duel_visuals(model2)
    dpos, dtgt, dfovy = cams["duel"]
    dquat = fc.look_quat(dpos, dtgt)

    # 300-frame take loop: per-frame loom from the take + per-frame thorax
    # bind (same bind_rifle call the probes use) + frozen duel camera.
    dists_log = []
    bad_frames = []
    samples = {}
    for i in range(start, end):
        data2.qpos[:] = q_settled
        data2.mocap_pos[0] = [dists[i] * 1000.0, 0.0, fc.LOOM_Z]
        mujoco.mj_forward(model2, data2)
        bind = fd.bind_rifle(model2, data2)
        mujoco.mj_forward(model2, data2)
        dists_log.append(bind["dist"])
        if bind["dist"] >= 10.0:
            bad_frames.append(i)
        big, pix, flags = fd.render_supersampled(model2, data2, "duel_duel")
        assert big.shape == (fd.RH, fd.RW, 3), big.shape
        assert pix.shape == (H, W, 3), pix.shape
        path = OUT / f"f{i:05d}.png"
        PIL.Image.fromarray(pix).save(path)
        if i in SAMPLES:
            cu, cv, _ = fc.project_point(dpos, dtgt, dquat, dfovy, fly_xyz,
                                         width=W, height=H)
            m = measure_fly(pix, cu, cv, CROP_DUEL)
            prop = fd.project_rifle_bbox(model2, data2, bind, dpos, dtgt,
                                         dquat, dfovy)
            moose = fd.project_moose_bbox(dpos, dtgt, dquat, dfovy)
            wf = fd.white_fraction(pix)
            md5 = hashlib.md5(path.read_bytes()).hexdigest()
            fb = m["bbox"]
            overlap = "n/a"
            if fb is not None:
                px0, py0, px1, py1 = prop["bbox"]
                ix0, iy0 = max(fb[0], px0), max(fb[1], py0)
                ix1, iy1 = min(fb[2], px1), min(fb[3], py1)
                overlap = bool(ix1 >= ix0 and iy1 >= iy0)
            moose_in = (moose is not None
                        and moose[2] >= 0 and moose[3] >= 0
                        and moose[0] < W and moose[1] < H)
            samples[i] = {"fly": m, "prop": prop, "moose": moose, "wf": wf,
                          "md5": md5, "flags": flags, "overlap": overlap,
                          "moose_in": moose_in, "bind_dist": bind["dist"]}
            print(f"frame={i} proj=({cu:.0f},{cv:.0f}) "
                  f"flybbox={m['w']}x{m['h']} maxside={m['max_side']} "
                  f"bands={m['bands']} flybox={fb} "
                  f"propbox=({prop['bbox'][0]:.0f},{prop['bbox'][1]:.0f},"
                  f"{prop['bbox'][2]:.0f},{prop['bbox'][3]:.0f}) "
                  f"overlap={overlap} moosebox={moose} moose_in={moose_in} "
                  f"bind={bind['dist']:.2f}mm whitefrac={wf:.4f} "
                  f"md5={md5[:12]} flags={flags} "
                  f"uniq={len(np.unique(pix.reshape(-1, 3), axis=0))}",
                  flush=True)
        elif i % 50 == 0:
            print(f"frame={i} bind={bind['dist']:.2f}mm", flush=True)

    wall = time.time() - t0
    darr = np.array(dists_log)
    print(f"bind-health n={len(dists_log)} max={darr.max():.2f}mm "
          f"mean={darr.mean():.2f}mm min={darr.min():.2f}mm "
          f"bad(>=10mm)={bad_frames} wall={wall:.1f}s", flush=True)
    if bad_frames:
        print(f"PROP DETACHED on frames {bad_frames} — STOP, not shipping",
              flush=True)
        sys.exit(2)

    # Determinism spot: rebuild + re-render sample 150, byte-compare
    # (same ±1 LSB EGL dither caveat + retry budget 4 as Task 1).
    spot = 150
    want = hashlib.md5((OUT / f"f{spot:05d}.png").read_bytes()).hexdigest()
    same, tries, pix_b = False, [], None
    for _ in range(4):
        w_b, _ = fd.build_duel_scene()
        fc.add_runtime_camera(w_b, "duel_duel", dpos, dtgt, dfovy)
        m_c, d_c = w_b.compile()
        fd.tune_duel_visuals(m_c)
        d_c.qpos[:] = q_settled
        d_c.mocap_pos[0] = [dists[spot] * 1000.0, 0.0, fc.LOOM_Z]
        mujoco.mj_forward(m_c, d_c)
        fd.bind_rifle(m_c, d_c)
        mujoco.mj_forward(m_c, d_c)
        _, pix_b, _ = fd.render_supersampled(m_c, d_c, "duel_duel")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            PIL.Image.fromarray(pix_b).save(tmp.name)
            got = hashlib.md5(open(tmp.name, "rb").read()).hexdigest()
        tries.append(got[:12])
        if got == want:
            same = True
            break
    assert pix_b is not None
    dd = (np.asarray(PIL.Image.open(OUT / f"f{spot:05d}.png")).astype(int)
          - pix_b.astype(int))
    print(f"determinism frame{spot}-rerender byte-identical={same} "
          f"tries={tries} last-nzdiff={int((dd != 0).any(axis=2).sum())} "
          f"last-maxabs={int(abs(dd).max())}", flush=True)

    ok_samples = all(s["overlap"] is True and s["moose_in"]
                     and s["wf"] < 0.05 and s["fly"]["max_side"] >= 40
                     for s in samples.values())
    print(f"GATES samples-overlap+moose+wf<5%+fly>=40px:{ok_samples} "
          f"deterministic:{same} n_files={len(list(OUT.glob('f*.png')))} "
          f"wall={wall:.1f}s", flush=True)
    if not (ok_samples and same):
        sys.exit(2)


if __name__ == "__main__":
    main()
