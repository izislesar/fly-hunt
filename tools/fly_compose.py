"""C3 hunt adapter (Task 5): compose the REAL NeuroMechFly + moose-box + loom.

Vendor drift resolution (verified live 2026-09-16, venv-brainfly314, flygym 2.1.0):
  BROKEN : ``from flygym import Fly`` -> ImportError (top-level __init__ exports
           only assets_dir/anatomy/compose/flybody/Simulation/Renderer/...).
  CORRECT: ``from flygym.compose import NeuroMechFly`` (``Fly`` is a deprecated
           alias of the same class -> DeprecationWarning; use NeuroMechFly).
  Vec3/Rotation3D live in ``flygym.utils.math``; Vec3 is a jaxtyping alias, so
  spawn positions are passed as plain sequences, rotations as Rotation3D quats.
  Ground contact sensors are broken in 2.1 (compile error "unrecognized name
  'nmf/lf_coxa' of sensorized object") -> add_fly(..., add_ground_contact_sensors=False).
  World units are MILLIMETRES (SCALE=1000); arena/hunt_arena.xml values are
  converted m->mm here. hunt_arena.xml and fly-brain/ are NEVER touched.

Scene (mm): FlatGroundWorld(half_size=15000) + fly + static moose-box
(0.4x0.3x0.4 m @ x=5 m) + MOCAP loom sphere (r=0.15 m, z=1.5 m) + sun + fill.
Cameras are defined here at runtime (arena hunt_cam stares at the floor).
Tracking rule (spec C3/Momus #7): lerp 0.2/frame toward the fly target.
"""

from __future__ import annotations

import numpy as np
import mujoco
from flygym.compose import FlatGroundWorld, NeuroMechFly
from flygym.utils.math import Rotation3D

M_PER_MM = 1000.0
W, H = 640, 480

# Actor layout mirrored from arena/hunt_arena.xml, converted to mm.
MOOSE_POS = (5000.0, 0.0, 205.0)      # moose-box centre (arena: 5 0 0.2 m)
MOOSE_HALF = (200.0, 150.0, 200.0)    # 0.4 x 0.3 x 0.4 m box
LOOM_R = 150.0                        # looming ball r=0.15 m
LOOM_Z = 1500.0                       # ball height 1.5 m
FLY_SPAWN = (0.0, 0.0, 0.6)           # vendor spawn height (two_flies.py)

TRACK_LERP = 0.2  # camera tracking lerp per frame (spec C3)


def look_quat(pos: np.ndarray, target: np.ndarray) -> tuple:
    """MuJoCo (w,x,y,z) quat aiming a -Z-forward camera at target (+Z up)."""
    fwd = np.asarray(target, float) - np.asarray(pos, float)
    fwd /= np.linalg.norm(fwd)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up)
    n = np.linalg.norm(right)
    if n < 1e-9:  # looking straight up/down: pick x-axis as right
        right = np.array([1.0, 0.0, 0.0])
    else:
        right /= n
    cam_up = np.cross(right, fwd)
    r = np.column_stack([right, cam_up, -fwd])
    from scipy.spatial.transform import Rotation as R

    x, y, z, w = R.from_matrix(r).as_quat()
    return (w, x, y, z)


def track_camera(prev_pos: np.ndarray, fly_pos: np.ndarray,
                 offset: np.ndarray) -> np.ndarray:
    """One lerp step of the tracking camera (Task 6 reuses this per frame)."""
    goal = np.asarray(fly_pos, float) + np.asarray(offset, float)
    return (1.0 - TRACK_LERP) * np.asarray(prev_pos, float) + TRACK_LERP * goal


def build_hunt_scene(loom_x: float = 12000.0):
    """Compose world+fly+moose+loom+lights. Returns (world, fly)."""
    from flygym import assets_dir

    fly = NeuroMechFly(name="nmf")
    fly.colorize(assets_dir / "model" / "neuromechfly" / "visuals.yaml")
    world = FlatGroundWorld(half_size=15000)
    world.add_fly(fly, list(FLY_SPAWN), Rotation3D("quat", [1, 0, 0, 0]),
                  add_ground_contact_sensors=False)
    wb = world.mjcf_root.worldbody
    # Moose-box (static): brown fantasy box, same volume class as arena XML.
    moose = wb.add_body(name="moose_box", pos=list(MOOSE_POS))
    moose.add_geom(name="moose_geom", type=mujoco.mjtGeom.mjGEOM_BOX,
                   size=list(MOOSE_HALF), rgba=(0.35, 0.25, 0.15, 1.0),
                   contype=0, conaffinity=0)
    # Looming ball (mocap: repositioned per probe without recompiling).
    loom = wb.add_body(name="looming_sphere", pos=[loom_x, 0.0, LOOM_Z],
                       mocap=True)
    loom.add_geom(name="looming_ball", type=mujoco.mjtGeom.mjGEOM_SPHERE,
                  size=[LOOM_R], rgba=(0.05, 0.05, 0.08, 1.0),
                  contype=0, conaffinity=0)
    # Sun (key) + fill (shadow-side lift so the fly is never a black blob).
    wb.add_light(name="sun", pos=[0, 0, 20000], dir=[0.4, 0.3, -1.0],
                 type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL, castshadow=False,
                 diffuse=[0.75, 0.7, 0.62], specular=[0.3, 0.3, 0.25])
    wb.add_light(name="fill", pos=[-5000, 4000, 8000], dir=[-0.5, 0.5, -1.0],
                 type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL, castshadow=False,
                 diffuse=[0.3, 0.33, 0.4], specular=[0.08, 0.08, 0.1])
    return world, fly


def dim_headlight(model, ambient: float = 0.2, diffuse: float = 0.25):
    """Tame EGL headlight so the colorized fly is never blown white."""
    model.vis.headlight.ambient[:] = [ambient] * 3
    model.vis.headlight.diffuse[:] = [diffuse] * 3


def tune_visuals(model, zfar: float = 100000.0):
    """Runtime visual fix for mm-scale worlds (model.vis only, spec untouched).

    FlatGroundWorld ships zfar=250 (model units = mm here), which clips
    EVERYTHING beyond 250 mm -> all-white wide frames; haze 0.3 with
    fogstart/fogend 3/10 would white-out distance cues as well.
    """
    dim_headlight(model)
    model.vis.map.zfar = float(zfar)
    model.vis.map.haze = 0.0


def add_runtime_camera(world, name: str, pos, target, fovy: float):
    """Define a free camera at runtime (arena XML untouched)."""
    world.mjcf_root.worldbody.add_camera(
        name=name, pos=list(map(float, pos)),
        quat=look_quat(np.asarray(pos, float), np.asarray(target, float)),
        fovy=float(fovy))


def project_point(pos, target, quat_wxyz, fovy_deg, point,
                  width=W, height=H):
    """Pinhole projection of a world point into pixel coords (verifies aim)."""
    from scipy.spatial.transform import Rotation as R

    w, x, y, z = quat_wxyz
    rmat = R.from_quat([x, y, z, w]).as_matrix()
    p_cam = rmat.T @ (np.asarray(point, float) - np.asarray(pos, float))
    tan_half = np.tan(np.deg2rad(fovy_deg) / 2.0)
    u = width / 2.0 + (p_cam[0] / -p_cam[2]) * (height / 2.0) / tan_half
    v = height / 2.0 - (p_cam[1] / -p_cam[2]) * (height / 2.0) / tan_half
    return u, v, p_cam[2]


THORAX_BODY = "nmf/c_thorax"  # set from Fly(name='nmf') + world prefix


def thorax_xpos(model, data) -> np.ndarray:
    """World position of the fly thorax (camera tracking anchor)."""
    import mujoco

    bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, THORAX_BODY)
    assert bid >= 0, f"thorax body {THORAX_BODY} not found"
    return data.xpos[bid].copy()


def settle_fly(model, data):
    """Static neutral pose (no stepping: spawn contacts explode the solver).

    Returns (qpos snapshot, thorax xyz). Stepping 500 physics steps launched
    the fly to z=129 mm on the first attempt (evidence in learnings); the
    neutral keyframe already stands the fly at thorax z=1.9 mm, feet on the
    ground. Probes are single frames, so a static pose is honest look-dev.
    """
    import mujoco

    key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "neutral")
    if key_id >= 0:
        data.qpos[:] = model.key_qpos[key_id]
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    return data.qpos.copy(), thorax_xpos(model, data)
