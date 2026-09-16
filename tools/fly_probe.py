"""G2 probe renderer (Task 5): 3 EGL probes (wide/close/mid) + measurements.

Fly-bbox method (honest): project the settled fly-thorax centre into pixels
with the same pinhole math as the render camera, crop +/-CROP around it,
threshold dark pixels (fly cuticle is dark vs sky/ground), report the
connected bbox (largest dark component) in px + dark-pixel fraction inside
the crop (self-validates the aim: high fraction = crop is on the fly).
Histogram bands: 16-bin gray histogram over the bbox; bands = bins holding
>=1% of bbox pixels (sun+fill must give >=3 on the close probe).
Determinism: re-render the close probe from the same data -> md5 compare.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import fly_compose as fc  # noqa: E402

OUT = REPO / "out" / "frames10"
W, H = fc.W, fc.H

PROBES = {
    # name: (cam_start, cam_offset_from_fly, look_target, fovy, loom_x, loom_z, crop, aim)
    # aim='fly': tracking close-up on the fly; 'bisect': mid-action two-shot
    # (fly + diving loom share the frame; needs fovy 32 since real scales put
    # them ~22 deg apart — no single 20-deg framing can hold both, Momus #5).
    "wide": ([-4000.0, -6000.0, 2500.0], None, (2000.0, 0.0, 0.0),
             45.0, 12000.0, 1500.0, 60, "fixed"),
    "close": (None, (32.0, -26.0, 22.0), None, 20.0, 8000.0, 1500.0, 170, "fly"),
    "mid": (None, (-90.0, -65.0, 6.0), None, 32.0, 3500.0, 1300.0, 170, "bisect"),
}


def render_probe(model, data, cam_name):
    import mujoco

    renderer = mujoco.Renderer(model, H, W)
    renderer.update_scene(data, camera=cam_name)
    return renderer.render()


def measure_fly(pix, cu, cv, crop):
    """Dark-pixel bbox around projected centre (cu, cv). Returns dict."""
    x0, x1 = max(0, int(cu) - crop), min(W, int(cu) + crop)
    y0, y1 = max(0, int(cv) - crop), min(H, int(cv) + crop)
    crop_img = pix[y0:y1, x0:x1].astype(float)
    gray = crop_img.mean(axis=2)
    dark = gray < 60.0
    dark_frac = float(dark.mean()) if dark.size else 0.0
    if not dark.any():
        return {"w": 0, "h": 0, "max_side": 0, "dark_frac": dark_frac,
                "bands": 0, "bbox": None}
    ys, xs = np.nonzero(dark)
    # largest connected dark mass: column-mass filter (legs are thin, body solid)
    col_mass = dark.sum(axis=0)
    core = np.nonzero(col_mass >= 3)[0]
    if core.size == 0:
        x_lo, x_hi = int(xs.min()), int(xs.max())
    else:
        x_lo, x_hi = int(core.min()), int(core.max())
    band = dark[:, x_lo:x_hi + 1]
    row_mass = band.sum(axis=1)
    rows = np.nonzero(row_mass >= 2)[0]
    y_lo, y_hi = (int(rows.min()), int(rows.max())) if rows.size else (int(ys.min()), int(ys.max()))
    bw, bh = x_hi - x_lo + 1, y_hi - y_lo + 1
    box = pix[y0 + y_lo:y0 + y_hi + 1, x0 + x_lo:x0 + x_hi + 1].astype(float)
    hist, _ = np.histogram(box.mean(axis=2), bins=16, range=(0, 256))
    bands = int((hist >= 0.01 * box.shape[0] * box.shape[1]).sum())
    return {"w": bw, "h": bh, "max_side": max(bw, bh), "dark_frac": dark_frac,
            "bands": bands,
            "bbox": (x0 + x_lo, y0 + y_lo, x0 + x_hi, y0 + y_hi)}


def main():
    import mujoco

    OUT.mkdir(parents=True, exist_ok=True)
    world, fly = fc.build_hunt_scene()
    model, data = world.compile()
    fc.tune_visuals(model)
    print(f"model-ok nq={model.nq} nv={model.nv} ngeom={model.ngeom}", flush=True)
    q_settled, fly_xyz = fc.settle_fly(model, data)
    print(f"fly-settled thorax_xyz_mm={np.round(fly_xyz, 2).tolist()}", flush=True)

    results = {}
    for name, (start, offset, look, fovy, loom_x, loom_z, crop, aim) in PROBES.items():
        data.qpos[:] = q_settled  # identical fly pose in every probe
        data.mocap_pos[0] = [loom_x, 0.0, loom_z]
        loom_xyz = np.array([loom_x, 0.0, loom_z])
        if offset is not None:  # tracking cam: converge lerp from wide stance
            prev = np.array([-4000.0, -6000.0, 2500.0])
            for _ in range(40):
                prev = fc.track_camera(prev, fly_xyz, np.array(offset))
            campos = prev
            if aim == "bisect":  # aim between fly and loom so both land in frame
                u_fly = (fly_xyz - campos) / np.linalg.norm(fly_xyz - campos)
                u_loom = (loom_xyz - campos) / np.linalg.norm(loom_xyz - campos)
                target = campos + 1000.0 * (u_fly + u_loom)
            else:
                target = fly_xyz
        else:
            campos, target = np.array(start), np.array(look)
        cname = f"probe_{name}"
        fc.add_runtime_camera(world, cname, campos, target, fovy)
        model2, data2 = world.compile()  # recompile picks up the new camera
        fc.tune_visuals(model2)
        data2.qpos[:] = q_settled
        data2.mocap_pos[:] = data.mocap_pos[:]
        mujoco.mj_forward(model2, data2)
        pix = render_probe(model2, data2, cname)
        path = OUT / f"probe_{name}.png"
        import PIL.Image

        PIL.Image.fromarray(pix).save(path)
        quat = fc.look_quat(campos, target)
        cu, cv, depth = fc.project_point(campos, target, quat, fovy, fly_xyz)
        m = measure_fly(pix, cu, cv, crop)
        extra = ""
        if aim == "bisect":  # loom ball census: largest dark blob anywhere
            dark_all = pix.mean(axis=2) < 100.0
            ys_a, xs_a = np.nonzero(dark_all)
            if xs_a.size:
                extra = (f" loomblob={xs_a.max()-xs_a.min()+1}x"
                         f"{ys_a.max()-ys_a.min()+1} npx={xs_a.size}")
        md5 = hashlib.md5(path.read_bytes()).hexdigest()[:12]
        results[name] = (m, md5, (cu, cv), fovy)
        print(f"probe={name} png={path.name} proj=({cu:.0f},{cv:.0f}) "
              f"bbox={m['w']}x{m['h']} maxside={m['max_side']} "
              f"darkfrac={m['dark_frac']:.2f} bands={m['bands']}{extra} md5={md5}",
              flush=True)

    # Determinism: re-render close from the same settled state.
    data.qpos[:] = q_settled
    data.mocap_pos[0] = [8000.0, 0.0, fc.LOOM_Z]
    mujoco.mj_forward(model, data)
    world2, _ = fc.build_hunt_scene(loom_x=8000.0)
    prev = np.array([-4000.0, -6000.0, 2500.0])
    for _ in range(40):
        prev = fc.track_camera(prev, fly_xyz, np.array(PROBES["close"][1]))
    fc.add_runtime_camera(world2, "probe_close", prev, fly_xyz, 20.0)
    m_b, d_b = world2.compile()
    fc.tune_visuals(m_b)
    d_b.qpos[:] = q_settled
    d_b.mocap_pos[:] = data.mocap_pos[:]
    mujoco.mj_forward(m_b, d_b)
    pix_b = render_probe(m_b, d_b, "probe_close")
    import PIL.Image

    tmp = OUT / "probe_close_rerender.png"
    PIL.Image.fromarray(pix_b).save(tmp)
    same = hashlib.md5(tmp.read_bytes()).hexdigest() == \
        hashlib.md5((OUT / "probe_close.png").read_bytes()).hexdigest()
    tmp.unlink()
    print(f"determinism close-rerender byte-identical={same}", flush=True)

    m_close = results["close"][0]
    ok = m_close["max_side"] >= 40 and m_close["bands"] >= 3 and same
    print(f"GATES close>=40px:{m_close['max_side']} bands>=3:{m_close['bands']} "
          f"deterministic:{same} -> {'PASS' if ok else 'FAIL'}", flush=True)
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
