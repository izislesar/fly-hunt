"""C3 full take (Task 6): 300 EGL tracking frames, G2-frozen pipeline.

Frozen G2 setup (byte-for-byte from tools/fly_probe.py probe_close):
  adapter fly_compose.build_hunt_scene + colorized NeuroMechFly + sun + fill,
  tune_visuals (zfar=1e5, haze=0, dimmed headlight), settle_fly static neutral
  pose, tracking cam offset (32,-26,22) fovy 20, 40x lerp-0.2 convergence from
  (-4000,-6000,2500) aimed at the settled thorax. NO exposure/camera retune.

Per-frame take state (from the 10 s sim, out/physics_log_10s.csv):
  fly qpos = settled snapshot every frame (probes proved the sim fly static);
  loom mocap = (dist_m * 1000, 0, 1500) — dist 12->4 m linear over 300 frames.
  Loom/moose sit ~135 deg off the close-up axis (behind camera); frames are
  honestly near-static — the take's motion lives in the brain panel.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import fly_compose as fc  # noqa: E402
from fly_probe import measure_fly  # noqa: E402  (Task 5 bbox method, frozen)

OUT = REPO / "out" / "frames10"
W, H = fc.W, fc.H
N_FRAMES = 300

# Frozen probe_close constants (tools/fly_probe.py PROBES["close"]).
OFFSET = np.array([32.0, -26.0, 22.0])
FOVY = 20.0
LOOM_Z = 1500.0
CROP = 170
CAM_START = np.array([-4000.0, -6000.0, 2500.0])


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

    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    dists = load_take_dists()

    world, fly = fc.build_hunt_scene()
    model, data = world.compile()
    fc.tune_visuals(model)
    q_settled, fly_xyz = fc.settle_fly(model, data)
    print(f"model-ok fly-settled thorax_xyz_mm={np.round(fly_xyz, 2).tolist()}",
          flush=True)

    # Tracking camera: 40x lerp-0.2 convergence (exact probe pipeline), then
    # frozen — fly is static so the goal never moves (no cuts, always locked).
    prev = CAM_START.copy()
    for _ in range(40):
        prev = fc.track_camera(prev, fly_xyz, OFFSET)
    campos, target = prev, fly_xyz
    fc.add_runtime_camera(world, "track", campos, target, FOVY)
    model2, data2 = world.compile()  # recompile picks up the new camera
    fc.tune_visuals(model2)
    quat = fc.look_quat(campos, target)
    renderer = mujoco.Renderer(model2, H, W)

    for i in range(N_FRAMES):
        data2.qpos[:] = q_settled
        data2.mocap_pos[0] = [dists[i] * 1000.0, 0.0, LOOM_Z]
        mujoco.mj_forward(model2, data2)
        renderer.update_scene(data2, camera="track")
        pix = renderer.render()
        PIL.Image.fromarray(pix).save(OUT / f"f{i:05d}.png")
        if i in (0, N_FRAMES // 2, N_FRAMES - 1):
            cu, cv, _ = fc.project_point(campos, target, quat, FOVY, fly_xyz)
            m = measure_fly(pix, cu, cv, CROP)
            print(f"frame={i} proj=({cu:.0f},{cv:.0f}) "
                  f"bbox={m['w']}x{m['h']} maxside={m['max_side']} "
                  f"darkfrac={m['dark_frac']:.2f} bands={m['bands']} "
                  f"uniq={len(np.unique(pix.reshape(-1, 3), axis=0))}",
                  flush=True)

    print(f"wall_s={time.time() - t0:.1f} n={N_FRAMES}", flush=True)


if __name__ == "__main__":
    main()
