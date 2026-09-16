"""Task 10 checker: validates closed-form reward + dopamine + Hebb clip.

Acceptance:
    python tools/check_reward.py --hit 1 --dist 5 --loom 50
        -> exit 0, 0 < reward <= 1, dW_mean logged.

Writes:
    out/reward.json      (hit/miss/no-see cases + dW_mean + log_line)
    out/fail_reward.log  (clip evidence: over-range probe raw 1.2 -> clipped 1.0)

Log line contract for Task 12 (exact columns):
    t,hit,dist,loom,reward,dW_mean   (t = frame time in ms)
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reward import (  # noqa: E402
    DOPAMINE_AMP,
    DOPAMINE_DUR_MS,
    DOPAMINE_TARGET,
    dopamine_pulse,
    hebb_dw,
    reward,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "out")

# KC->MBON block used for dW_mean (synthetic small matrix, documented):
# full circuit: 2000 KC -> 96 MBON. Checker samples kc_fanin=32 KC inputs
# per MBON (seeded RNG) -> W shape (96, 32). r = 10ms binned rates in Hz.
N_MBON = 96
KC_FANIN_SAMPLED = 32
KC_TOTAL = 2000
RNG_SEED = 10


def compute_dw_mean(seed=RNG_SEED):
    """Synthetic KC->MBON block dW mean. Returns (dW_mean, dims_note)."""
    try:
        import numpy as np

        rng = np.random.default_rng(seed)
        r_pre = rng.uniform(5.0, 200.0, size=(N_MBON, KC_FANIN_SAMPLED))
        r_post = rng.uniform(5.0, 200.0, size=(N_MBON, KC_FANIN_SAMPLED))
        W = rng.uniform(0.0, 0.5, size=(N_MBON, KC_FANIN_SAMPLED)).astype(float)
        dW, W_new = hebb_dw(r_pre, r_post, W)  # type: ignore[misc]
        assert bool((W_new >= 0).all() and (W_new <= 2).all()), "W escaped [0,2]"  # type: ignore[union-attr]
        return float(np.mean(dW)), (
            f"W shape ({N_MBON},{KC_FANIN_SAMPLED}): {N_MBON} MBON x "
            f"{KC_FANIN_SAMPLED} sampled KC fan-in of {KC_TOTAL} KC; "
            f"r = 10ms binned rate Hz; seed {seed}"
        )
    except ImportError:
        import random

        rnd = random.Random(seed)
        acc, n = 0.0, 0
        wmin, wmax = 2.0, -2.0
        for _ in range(N_MBON * KC_FANIN_SAMPLED):
            ri = rnd.uniform(5.0, 200.0)
            rj = rnd.uniform(5.0, 200.0)
            w = rnd.uniform(0.0, 0.5)
            dW, w_new = hebb_dw(ri, rj, w)
            acc += dW
            n += 1
            wmin = min(wmin, w_new)
            wmax = max(wmax, w_new)
        assert 0.0 <= wmin and wmax <= 2.0, "W escaped [0,2]"
        return acc / n, (
            f"W {N_MBON}x{KC_FANIN_SAMPLED} pure-python fallback: {N_MBON} MBON x "
            f"{KC_FANIN_SAMPLED} sampled KC fan-in of {KC_TOTAL} KC; "
            f"r = 10ms binned rate Hz; seed {seed}"
        )


def main():
    ap = argparse.ArgumentParser(description="Task 10 reward checker")
    ap.add_argument("--hit", type=int, default=1, help="hit_bool in {0,1}")
    ap.add_argument("--dist", type=float, default=5.0, help="dist_m meters")
    ap.add_argument("--loom", type=float, default=50.0, help="loom_Hz")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    t_ms = 0.0  # frame time ms for single-shot check (Task 12 logs per-frame t)

    # --- CLI hit case (acceptance) ---
    r_hit, info_hit = reward(args.hit, args.dist, args.loom, visible=True)
    dop_hit = dopamine_pulse(r_hit)
    dW_mean, dims_note = compute_dw_mean()

    if int(args.hit) == 1:
        assert 0.0 < r_hit <= 1.0, (
            f"acceptance FAIL: hit case reward={r_hit} not in (0,1]"
        )

    # --- miss case -> 0, no pulse ---
    r_miss, info_miss = reward(0, args.dist, args.loom, visible=True)
    dop_miss = dopamine_pulse(r_miss)
    assert r_miss == 0.0, f"miss must be 0, got {r_miss}"
    assert dop_miss["pulse"] is False, "miss must not pulse"

    # --- no-see case (loom missing / visible=False) -> 0, no pulse ---
    r_nosee, info_nosee = reward(1, args.dist, None, visible=False)
    dop_nosee = dopamine_pulse(r_nosee)
    assert r_nosee == 0.0, f"no-see must be 0, got {r_nosee}"
    assert dop_nosee["pulse"] is False, "no-see must not pulse"
    assert dop_hit["pulse"] is True, "hit must pulse"
    assert dop_hit["amp"] == DOPAMINE_AMP and dop_hit["dur_ms"] == DOPAMINE_DUR_MS

    # --- over-range clip probe: hit=1 dist=0 loom=0 -> raw 1.2 -> clipped 1.0 ---
    r_clip, info_clip = reward(1, 0.0, 0.0, visible=True)
    assert abs(info_clip["raw"] - 1.2) < 1e-9, f"probe raw != 1.2: {info_clip['raw']}"
    assert r_clip == 1.0 and info_clip["clipped"] is True, "clip path broken"

    def loom_str(v):
        return "None" if v is None else str(float(v))

    log_line = f"{t_ms},{int(args.hit)},{float(args.dist)},{float(args.loom)},{r_hit},{dW_mean}"

    payload = {
        "task": 10,
        "formula": "reward=clip(1.0*hit-0.3*dist_norm+0.2*(1-loom_norm)*hit,0,1); "
                   "dist_norm=clip(dist_m/20.0,0,1); loom_norm=clip(loom_Hz/200.0,0,1)",
        "dopamine": {"amp": DOPAMINE_AMP, "dur_ms": DOPAMINE_DUR_MS,
                     "target": DOPAMINE_TARGET},
        "hebb": {"formula": "dW=1e-4*r_i*r_j-1e-7*W, clip W [0,2]; r = 10ms binned rate Hz",
                 "dims": dims_note},
        "cases": {
            "hit": {"hit": int(args.hit), "dist": float(args.dist),
                    "loom": float(args.loom), "reward": r_hit,
                    "dist_norm": info_hit["dist_norm"],
                    "loom_norm": info_hit["loom_norm"], "raw": info_hit["raw"],
                    "clipped": info_hit["clipped"], "dopamine": dop_hit},
            "miss": {"hit": 0, "dist": float(args.dist),
                     "loom": float(args.loom), "reward": r_miss,
                     "dopamine": dop_miss},
            "no_see": {"hit": 1, "dist": float(args.dist), "loom": None,
                       "reward": r_nosee, "dopamine": dop_nosee},
        },
        "clip_probe": {"hit": 1, "dist": 0.0, "loom": 0.0,
                       "raw": info_clip["raw"], "reward": r_clip,
                       "clipped": info_clip["clipped"]},
        "dW_mean": dW_mean,
        "log_line": log_line,
        "log_columns": "t,hit,dist,loom,reward,dW_mean",
        "t_note": "t = frame time in ms (0.0 for single-shot check; Task 12 logs per-frame t)",
    }
    with open(os.path.join(OUT_DIR, "reward.json"), "w") as f:
        json.dump(payload, f, indent=2)

    fail_lines = [
        "Task 10 QA-fail gate: clip evidence (exit-range probe must clip, never escape [0,1])",
        f"probe: hit=1 dist=0 loom=0 -> raw={info_clip['raw']} -> reward={r_clip} clipped:{str(info_clip['clipped']).lower()}",
        "expected: raw=1.2 clipped to 1.0 (coef 1.0 + 0.2*(1-0)*1 = 1.2, dist term 0)",
        "result: clip path WORKS (no out-of-[0,1] escape observed; all live rewards clipped by reward())",
        f"acceptance case: --hit {int(args.hit)} --dist {float(args.dist)} --loom {loom_str(args.loom)} -> reward={r_hit} in (0,1] OK",
        f"miss->0 evidence: reward={r_miss} pulse={dop_miss['pulse']}",
        f"no-see->0 evidence: reward={r_nosee} pulse={dop_nosee['pulse']}",
    ]
    with open(os.path.join(OUT_DIR, "fail_reward.log"), "w") as f:
        f.write("\n".join(fail_lines) + "\n")

    print(log_line)
    print(f"reward={r_hit} dW_mean={dW_mean} pulse={dop_hit['pulse']} "
          f"amp={dop_hit['amp']} dur_ms={dop_hit['dur_ms']}")
    print("PASS: 0<reward<=1, miss/no-see=0, clip probe raw=1.2->1.0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
