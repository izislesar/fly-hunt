#!/usr/bin/env python3
"""DNpe017 shot model checker — Task 9.

Frozen params: threshold=3 spikes/10ms bin on DNpe017, hysteresis=2,
ammo=5, range=20.0m, cooldown=500ms, spread=0.02rad raycast cone.
CLI overrides ONLY --range / --spread (others frozen, documented).
Stdlib only. Deterministic (seeded RNG seed=1).
"""
import argparse
import json
import random
from pathlib import Path

# EXACT frozen params (do not change)
THRESHOLD = 3          # spikes per 10ms bin on DNpe017
HYSTERESIS = 2         # re-arm requires count <= THRESHOLD - HYSTERESIS (=1)
AMMO_MAX = 5
RANGE_M = 20.0
COOLDOWN_MS = 500
SPREAD_RAD = 0.02
SEED = 1
BIN_MS = 10


class ShotController:
    def __init__(self, range_m=RANGE_M, spread_rad=SPREAD_RAD):
        self.range_m = range_m
        self.spread_rad = spread_rad
        self.ammo = AMMO_MAX
        self.armed = True
        self.last_shot_ms = -10 ** 12
        self.rng = random.Random(SEED)

    def _cone_check(self):
        # Raycast cone sample: angular error ~ N(0, spread); target on-axis (0).
        # Inside cone if |err| <= 3*spread (99.7%). Deterministic via seed.
        err = self.rng.gauss(0.0, self.spread_rad)
        return abs(err) <= 3 * self.spread_rad, err

    def try_fire(self, count, dist_m, visible, now_ms):
        # Order: cooldown -> visibility -> range -> trigger/hysteresis -> cone/ammo
        if now_ms - self.last_shot_ms < COOLDOWN_MS:
            return False, "cooldown"
        if not visible:
            return False, "no-visibility"
        if dist_m > self.range_m:
            return False, "out-of-range"
        if self.ammo <= 0:
            return False, "no-ammo"
        if not self.armed:
            # Hysteresis re-arm gate
            if count <= THRESHOLD - HYSTERESIS:
                self.armed = True
            else:
                return False, "hysteresis-not-rearmed"
        if count < THRESHOLD:
            return False, "below-threshold"
        inside, _err = self._cone_check()
        if not inside:
            return False, "cone-miss"
        # FIRE
        self.ammo -= 1
        self.last_shot_ms = now_ms
        self.armed = False
        return True, "hit"


def main():
    ap = argparse.ArgumentParser(description="DNpe017 shot checker (Task 9)")
    ap.add_argument("--range", type=float, default=RANGE_M,
                    help="range override in meters (default 20.0)")
    ap.add_argument("--spread", type=float, default=SPREAD_RAD,
                    help="spread override in rad (default 0.02)")
    args = ap.parse_args()

    ctl = ShotController(range_m=args.range, spread_rad=args.spread)

    scenarios = []

    # Scenario 1: 5m visible suprathreshold -> HIT True
    hit1, reason1 = ctl.try_fire(count=THRESHOLD, dist_m=5.0, visible=True, now_ms=0)
    scenarios.append({"name": "hit-5m", "dist_m": 5.0, "visible": True,
                      "dnpe017_count": THRESHOLD, "hit": hit1, "reason": reason1})

    # Sub-check: cooldown — immediate second shot blocked
    hit_cd, reason_cd = ctl.try_fire(count=5, dist_m=5.0, visible=True, now_ms=100)
    cooldown_ok = (hit_cd is False and reason_cd == "cooldown")

    # Sub-check: hysteresis — count at threshold-1 after fire does not retrigger
    # (t=600ms is past cooldown, but armed==False and count=2 > 1 so no re-arm)
    hit_hy, reason_hy = ctl.try_fire(count=THRESHOLD - 1, dist_m=5.0, visible=True, now_ms=600)
    hysteresis_ok = (hit_hy is False and reason_hy == "hysteresis-not-rearmed")

    # Scenario 2: 25m visible -> MISS False, out-of-range
    hit2, reason2 = ctl.try_fire(count=5, dist_m=25.0, visible=True, now_ms=1000)
    scenarios.append({"name": "miss-25m", "dist_m": 25.0, "visible": True,
                      "dnpe017_count": 5, "hit": hit2, "reason": reason2})

    # Case 3: no-visibility (occluded) -> no shot
    hit3, reason3 = ctl.try_fire(count=5, dist_m=5.0, visible=False, now_ms=1500)
    scenarios.append({"name": "occluded-5m", "dist_m": 5.0, "visible": False,
                      "dnpe017_count": 5, "hit": hit3, "reason": reason3})

    params = {"threshold": THRESHOLD, "hysteresis": HYSTERESIS,
              "ammo": AMMO_MAX, "range_m": args.range,
              "cooldown_ms": COOLDOWN_MS, "spread_rad": args.spread,
              "bin_ms": BIN_MS, "seed": SEED,
              "note": "only --range/--spread overridable; others frozen"}
    out = {"params": params, "scenarios": scenarios,
           "ammo_left": ctl.ammo,
           "checks": {"cooldown_ok": cooldown_ok, "hysteresis_ok": hysteresis_ok}}

    outdir = Path("out")
    outdir.mkdir(exist_ok=True)
    with open(outdir / "shot.json", "w") as f:
        json.dump(out, f, indent=2)

    # fail_shot.log: no-shot evidence + not-triggered note for in-range path
    with open(outdir / "fail_shot.log", "w") as f:
        f.write(f"out-of-range case: dist=25.0m > range={args.range}m -> "
                f"no shot, hit={hit2}, reason={reason2}\n")
        f.write(f"no-visibility case: occluded flag visible=False at dist=5.0m -> "
                f"no shot, hit={hit3}, reason={reason3}\n")
        f.write(f"in-range path: dist=5.0m visible with count={THRESHOLD} -> "
                f"TRIGGERED (not a failure), hit={hit1}, reason={reason1}\n")
        f.write(f"cooldown sub-check: second shot at +100ms blocked -> "
                f"hit={hit_cd} reason={reason_cd} ok={cooldown_ok}\n")
        f.write(f"hysteresis sub-check: count={THRESHOLD - 1} after fire "
                f"does not retrigger -> hit={hit_hy} reason={reason_hy} "
                f"ok={hysteresis_ok}\n")

    print(f"scenario hit-5m: hit={hit1} reason={reason1}")
    print(f"scenario miss-25m: hit={hit2} reason={reason2}")
    print(f"scenario occluded-5m: hit={hit3} reason={reason3}")
    print(f"cooldown check: ok={cooldown_ok} (hit={hit_cd} reason={reason_cd})")
    print(f"hysteresis check: ok={hysteresis_ok} (hit={hit_hy} reason={reason_hy})")
    print(f"ammo_left={ctl.ammo}")

    ok = (hit1 is True and hit2 is False and reason2 == "out-of-range"
          and hit3 is False and reason3 == "no-visibility"
          and cooldown_ok and hysteresis_ok)
    if not ok:
        print("FAIL: shot checks did not pass")
        raise SystemExit(1)
    print("PASS: all shot checks passed")


if __name__ == "__main__":
    main()
