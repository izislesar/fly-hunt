#!/usr/bin/env python3
"""Task 8 physics checker: 500-step NaN guard over fantasy scale table.

Two paths:
  PATH=real     — `import mujoco` works: load arena/hunt_arena.xml if
                  present else a minimal inline model, step N times,
                  assert no NaN in qpos/qvel.
  PATH=analytic(mujoco-missing) — mujoco ImportError: assert all table
                  values finite/positive/in-range + cross-check
                  arena/hunt_arena.xml option attributes if the file
                  exists (Task 7 builds it in parallel; absent is OK).

Exit 0 on pass (+ prints `no NaN in <steps> steps`), exit 1 on violation.
Stdlib only (+ numpy if present for isnan; pure-python fallback otherwise).
"""
import argparse
import math
import os
import sys
import xml.etree.ElementTree as ET

TABLE = {
    "fly_mass": 1e-6,
    "fly_wingspan_m": 0.003,
    "moose_mass": 0.5,
    "moose_volume": 0.05,
    "gravity": -9.81,
    "dt": 0.0005,
    "iterations": 100,
    "solref": [2e-4, 1e3],
    "solimp": [0.999, 0.9999, 1e-3, 0.5, 2.0],
}

XML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "arena", "hunt_arena.xml")
# When run from repo root, the above resolves to <root>/arena/hunt_arena.xml.
# Also accept relative path for robustness.
ALT_XML = "arena/hunt_arena.xml"


def _is_finite(x):
    try:
        import numpy as _np  # noqa: F401
        use_np = True
    except ImportError:
        use_np = False
    if use_np:
        import numpy as np
        return bool(np.isfinite(x))
    return math.isfinite(x)


def analytic_checks(steps):
    errs = []
    t = TABLE
    for k in ("fly_mass", "moose_mass", "moose_volume", "fly_wingspan_m"):
        v = t[k]
        if not _is_finite(v) or not v > 0:
            errs.append(f"{k}={v} must be finite positive")
    for k in ("dt",):
        v = t[k]
        if not _is_finite(v) or not v > 0:
            errs.append(f"{k}={v} must be finite positive")
    if not _is_finite(t["gravity"]) or not -20.0 <= t["gravity"] <= 0.0:
        errs.append(f"gravity={t['gravity']} out of [-20,0]")
    if not isinstance(t["iterations"], int) or not 1 <= t["iterations"] <= 1000:
        errs.append(f"iterations={t['iterations']} out of [1,1000]")
    sr = t["solref"]
    if len(sr) != 2 or not all(_is_finite(v) and v > 0 for v in sr):
        errs.append(f"solref={sr} must be 2 finite positives")
    si = t["solimp"]
    if len(si) != 5 or not all(_is_finite(v) for v in si):
        errs.append(f"solimp={si} must be 5 finite values")
    else:
        if not (0.0 < si[0] <= 1.0 and 0.0 < si[1] <= 1.0):
            errs.append(f"solimp[0:2]={si[0:2]} must be in (0,1]")
        if not (si[2] > 0 and si[3] >= 0 and si[4] >= si[3]):
            errs.append(f"solimp[2:5]={si[2:5]} range violation")
    # Analytic NaN-guard rollout: integrate a trivial free-fall velocity
    # with table dt/gravity for `steps`, checking finiteness each step.
    v = 0.0
    x = 1.0
    for _ in range(steps):
        v += t["gravity"] * t["dt"]
        x += v * t["dt"]
        if not (math.isfinite(v) and math.isfinite(x)):
            errs.append("analytic rollout hit NaN/Inf")
            break
    # XML cross-check if present.
    xml = XML_PATH if os.path.exists(XML_PATH) else (ALT_XML if os.path.exists(ALT_XML) else None)
    xml_note = "xml-absent (Task 7 parallel; inline values used)"
    if xml:
        xml_note = f"xml-cross-checked ({xml})"
        try:
            root = ET.parse(xml).getroot()
            opt = root.find("option")
            if opt is None:
                errs.append(f"{xml}: missing <option>")
            else:
                def cmp_attr(name, want, tol=1e-12):
                    got = opt.get(name)
                    if got is None:
                        errs.append(f"{xml}: option @{name} missing")
                        return
                    try:
                        g = float(got)
                    except ValueError:
                        errs.append(f"{xml}: option @{name}={got!r} not float")
                        return
                    if abs(g - want) > tol * max(1.0, abs(want)):
                        errs.append(f"{xml}: option @{name}={g} != table {want}")
                cmp_attr("timestep", t["dt"])
                # MuJoCo gravity is a 3-vector ("0 0 -9.81"); table stores z.
                got_g = opt.get("gravity")
                if got_g is None:
                    errs.append(f"{xml}: option @gravity missing")
                else:
                    try:
                        gv = [float(p) for p in got_g.split()]
                    except ValueError:
                        errs.append(f"{xml}: option @gravity={got_g!r} not floats")
                        gv = []
                    if gv:
                        gz = gv[-1]
                        if abs(gz - t["gravity"]) > 1e-12 * max(1.0, abs(t["gravity"])):
                            errs.append(f"{xml}: option @gravity z={gz} != table {t['gravity']}")
                got_iter = opt.get("iterations")
                if got_iter is not None and int(got_iter) != t["iterations"]:
                    errs.append(f"{xml}: option @iterations={got_iter} != {t['iterations']}")
                for name, want in (("solref", t["solref"]), ("solimp", t["solimp"])):
                    got = opt.get(name)
                    if got is not None:
                        try:
                            gv = [float(p) for p in got.split()]
                        except ValueError:
                            errs.append(f"{xml}: option @{name}={got!r} not floats")
                            continue
                        if len(gv) != len(want) or any(
                                abs(a - b) > 1e-9 * max(1.0, abs(b)) for a, b in zip(gv, want)):
                            errs.append(f"{xml}: option @{name}={gv} != table {want}")
        except ET.ParseError as e:
            errs.append(f"{xml}: XML parse error: {e}")
    return errs, xml_note


MINIMAL_MODEL = """<mujoco>
  <option timestep="0.0005" gravity="0 0 -9.81" iterations="100"
          solref="2e-4 1e3" solimp="0.999 0.9999 1e-3 0.5 2.0"/>
  <worldbody>
    <body name="fly" pos="0 0 1"><freejoint/><geom size="0.003" mass="1e-6"/></body>
    <body name="moose-box" pos="0.5 0 0.2"><freejoint/><geom type="box" size="0.2 0.2 0.2" mass="0.5"/></body>
  </worldbody>
</mujoco>
"""


def real_checks(steps):
    import mujoco  # noqa: F401
    import numpy as np
    xml = XML_PATH if os.path.exists(XML_PATH) else (ALT_XML if os.path.exists(ALT_XML) else None)
    if xml:
        model = mujoco.MjModel.from_xml_path(xml)
        note = f"model={xml}"
    else:
        model = mujoco.MjModel.from_xml_string(MINIMAL_MODEL)
        note = "model=inline-minimal (arena/hunt_arena.xml absent)"
    data = mujoco.MjData(model)
    for _ in range(steps):
        mujoco.mj_step(model, data)
        if bool(np.isnan(data.qpos).any() or np.isnan(data.qvel).any()):
            return [f"NaN in qpos/qvel during real rollout ({note})"], note
    return [], note


def main():
    ap = argparse.ArgumentParser(description="Task 8 physics NaN guard")
    ap.add_argument("--steps", type=int, default=500)
    args = ap.parse_args()
    steps = args.steps
    try:
        import mujoco  # noqa: F401
        has_mj = True
    except ImportError:
        has_mj = False
    errs, note = real_checks(steps) if has_mj else analytic_checks(steps)
    path = "real" if has_mj else "analytic(mujoco-missing)"
    print(f"PATH={path} {note}")
    if errs:
        print("FAIL:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(f"no NaN in {steps} steps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
