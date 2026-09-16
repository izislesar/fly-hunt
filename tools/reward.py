"""Task 10: closed-form reward + dopamine gate + Hebbian KC->MBON plasticity.

Frozen formula (DO NOT retune):
    dist_norm = clip(dist_m / 20.0, 0, 1)
    loom_norm = clip(loom_Hz / 200.0, 0, 1)
    reward = clip(1.0*hit - 0.3*dist_norm + 0.2*(1-loom_norm)*hit, 0, 1)
    hit in {0, 1}

Dopamine: amp 0.8, dur 200ms, target PPL101 -> KC->MBON plasticity gate.
    miss (hit=0) -> reward 0, no pulse.
    no-see (loom missing / visible=False) -> reward 0, no pulse.

Hebb (KC->MBON only, closed-form, no full retraining):
    dW = 1e-4 * r_i * r_j - 1e-7 * W, clip W to [0, 2]
    r = 10ms binned rate in Hz.

Stdlib + numpy (numpy optional, pure-python fallback).
"""

from typing import Any

try:
    import numpy as _np_mod  # type: ignore
    _np: Any = _np_mod
    _HAS_NP = True
except Exception:
    _np = None  # type: ignore
    _HAS_NP = False


def _clip(x, lo, hi):  # type: ignore[no-untyped-def]
    if _HAS_NP:
        return float(_np.clip(x, lo, hi))  # type: ignore[union-attr]
    return max(lo, min(hi, float(x)))


# Frozen constants
DIST_SCALE_M = 20.0
LOOM_SCALE_HZ = 200.0
COEF_HIT = 1.0
COEF_DIST = -0.3
COEF_LOOM = 0.2
DOPAMINE_AMP = 0.8
DOPAMINE_DUR_MS = 200.0
DOPAMINE_TARGET = "PPL101 -> KC->MBON plasticity gate"
HEBB_ETA = 1e-4
HEBB_DECAY = 1e-7
W_MIN, W_MAX = 0.0, 2.0


def reward(hit, dist_m, loom_Hz, visible=True):
    """Closed-form reward in [0, 1].

    Args:
        hit: int in {0, 1} (Task 9 hit_bool semantics).
        dist_m: float, moose distance in meters (from sync CSV moose_pos).
        loom_Hz: float or None; looming-ball rate in Hz. None == no-see.
        visible: bool; False == no-see -> 0.

    Returns:
        (reward, info_dict) with dist_norm, loom_norm, raw, clipped flag.
    """
    hit = int(hit)
    if hit not in (0, 1):
        raise ValueError("hit must be 0 or 1")
    # no-see -> 0 (loom missing or not visible)
    if (not visible) or (loom_Hz is None):
        return 0.0, {
            "dist_norm": _clip(float(dist_m) / DIST_SCALE_M, 0, 1),
            "loom_norm": None,
            "raw": 0.0,
            "clipped": False,
            "no_see": True,
        }
    dist_norm = _clip(float(dist_m) / DIST_SCALE_M, 0, 1)
    loom_norm = _clip(float(loom_Hz) / LOOM_SCALE_HZ, 0, 1)
    raw = COEF_HIT * hit + COEF_DIST * dist_norm + COEF_LOOM * (1 - loom_norm) * hit
    clipped = _clip(raw, 0, 1)
    return clipped, {
        "dist_norm": dist_norm,
        "loom_norm": loom_norm,
        "raw": raw,
        "clipped": bool(raw != clipped),
        "no_see": False,
    }


def dopamine_pulse(reward_value):
    """Dopamine pulse gating KC->MBON plasticity.

    Returns dict with amp/dur/target when reward > 0, else no-pulse.
    """
    if reward_value is None or float(reward_value) <= 0.0:
        return {"pulse": False, "amp": 0.0, "dur_ms": 0.0,
                "target": DOPAMINE_TARGET}
    return {"pulse": True, "amp": DOPAMINE_AMP, "dur_ms": DOPAMINE_DUR_MS,
            "target": DOPAMINE_TARGET}


def hebb_dw(r_pre_hz, r_post_hz, W):
    """Hebbian update dW = 1e-4*r_i*r_j - 1e-7*W. Works scalar or array-like.

    Returns (dW, W_new_clipped). W clipped to [0, 2].
    r inputs are 10ms-binned rates in Hz.
    """
    if _HAS_NP:
        r_pre = _np.asarray(r_pre_hz, dtype=float)  # type: ignore[union-attr]
        r_post = _np.asarray(r_post_hz, dtype=float)  # type: ignore[union-attr]
        W_ = _np.asarray(W, dtype=float)  # type: ignore[union-attr]
        dW = HEBB_ETA * r_pre * r_post - HEBB_DECAY * W_
        W_new = _np.clip(W_ + dW, W_MIN, W_MAX)  # type: ignore[union-attr]
        return dW, W_new
    # pure-python scalar fallback
    dW = HEBB_ETA * float(r_pre_hz) * float(r_post_hz) - HEBB_DECAY * float(W)
    W_new = max(W_MIN, min(W_MAX, float(W) + dW))
    return dW, W_new


def clip_w(W):
    """Clip weights to [0, 2]."""
    if _HAS_NP:
        return _np.clip(_np.asarray(W, dtype=float), W_MIN, W_MAX)  # type: ignore[union-attr]
    if isinstance(W, (list, tuple)):
        return [max(W_MIN, min(W_MAX, float(x))) for x in W]
    return max(W_MIN, min(W_MAX, float(W)))
