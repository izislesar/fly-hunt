"""Task 11 bridge verifier — API wiring check, NO behavioral scripts.

Fixed vendor path (read-only, never edited, never stubbed).
Checks expected API from plan Scope bridge bullet against actual vendor file:
  BrainBodyBridge(decoder, escape_threshold, groom_threshold)
  DNRateDecoder(window_ms=50.0, dt_ms=0.1, max_rate=200.0)
  methods def step / def reset / def spike / def torque
  DNpe017 reference, linear DN->joint map.

Exit 0 = all PASS. Exit 1 = at least one FAIL (see out/ADAPTATION.md).
Import probe: tries to import the vendor module read-only and instantiate
the decoder with defaults; on missing deps records the ImportError honestly
and falls back to AST/grep verification (no stubbing).
"""

import ast
import re
import sys
import traceback
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "fly-brain" / "brain_body_bridge.py"

results = []


def check(name, passed, detail=""):
    results.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main():
    print(f"vendor: {VENDOR}")
    if not VENDOR.exists():
        check("vendor file exists", False, str(VENDOR))
        print(f"\n{sum(1 for _, p, _ in results if p)}/{len(results)} passed")
        return 1
    check("vendor file exists", True, str(VENDOR))

    src = VENDOR.read_text()
    tree = ast.parse(src)

    classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    defs = [(n.name, n.lineno) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    def_lines = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            def_lines.setdefault(n.name, []).append(n.lineno)

    # --- DNRateDecoder defaults ---
    dec = classes.get("DNRateDecoder")
    check("class DNRateDecoder present", dec is not None,
          f"line {dec.lineno}" if dec is not None else "missing")
    dec_defaults_ok = False
    dec_detail = ""
    if dec is not None:
        init = next((n for n in dec.body if isinstance(n, ast.FunctionDef)
                     and n.name == "__init__"), None)
        if init is not None:
            args = init.args
            names = [a.arg for a in args.args]  # includes self
            dflt_vals = [ast.literal_eval(d) for d in args.defaults]
            dflt_names = names[len(names) - len(dflt_vals):]
            mapping = dict(zip(dflt_names, dflt_vals))
            dec_detail = f"line {init.lineno}, defaults={mapping}"
            dec_defaults_ok = (mapping.get("window_ms") == 50.0
                               and mapping.get("dt_ms") == 0.1
                               and mapping.get("max_rate") == 200.0)
    check("DNRateDecoder(window_ms=50.0, dt_ms=0.1, max_rate=200.0)",
          dec_defaults_ok, dec_detail or "no __init__ defaults match")

    # --- BrainBodyBridge __init__ params ---
    br = classes.get("BrainBodyBridge")
    check("class BrainBodyBridge present", br is not None,
          f"line {br.lineno}" if br is not None else "missing")
    params = []
    br_line = ""
    if br is not None:
        init = next((n for n in br.body if isinstance(n, ast.FunctionDef)
                     and n.name == "__init__"), None)
        if init is not None:
            br_line = f"line {init.lineno}"
            params = [a.arg for a in init.args.args if a.arg != "self"]
            params += [a.arg for a in init.args.kwonlyargs]
    for p in ("decoder", "escape_threshold", "groom_threshold"):
        check(f"BrainBodyBridge has param '{p}'", p in params,
              f"{br_line} params={params}" if params else "no __init__ found")

    # --- method presence (acceptance grep equivalents, exact def names) ---
    for m in ("step", "reset", "spike", "torque"):
        hit = def_lines.get(m, [])
        check(f"def {m} present", bool(hit),
              f"line(s) {hit}" if hit else "no exact 'def %s' in file" % m)
    # acceptance grep exit-0 equivalent: at least one of the four
    any_method = any(def_lines.get(m) for m in ("step", "reset", "spike", "torque"))
    check("acceptance grep 'def step|reset|spike|torque' exit 0 equivalent",
          any_method, f"found={sorted(k for k in ('step', 'reset', 'spike', 'torque') if def_lines.get(k))}")

    # --- DNpe017 reference in bridge file ---
    dnpe_in_bridge = "DNpe017" in src
    check("DNpe017 referenced in brain_body_bridge.py", dnpe_in_bridge,
          "found" if dnpe_in_bridge else
          "absent in bridge file (present in fly-brain/data/flywire_annotations.tsv)")

    # --- linear DN->joint map present (no behavior written, reference only) ---
    has_compute = "compute_drive" in def_lines
    has_drives = "left_drive" in src and "right_drive" in src
    proj = re.search(r"forward \* \(1\.0 .*effective_turn\) - backward", src)
    check("linear DN->joint map present (compute_drive -> [left_drive, right_drive])",
          has_compute and has_drives and proj is not None,
          f"compute_drive line {def_lines.get('compute_drive')}, "
          f"projection {'found' if proj else 'NOT found'}")

    # --- import probe (read-only; honest ImportError, no stubbing) ---
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("vendor_bridge", str(VENDOR))
        assert spec is not None and spec.loader is not None, "no spec for vendor file"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        dec_inst = mod.DNRateDecoder(window_ms=50.0, dt_ms=0.1, max_rate=200.0)
        ok = (dec_inst.window_steps == 500
              and abs(dec_inst.dt_s - 0.0001) < 1e-12
              and dec_inst.max_rate == 200.0)
        check("import probe: DNRateDecoder() with defaults instantiates",
              ok, f"window_steps={dec_inst.window_steps}, dt_s={dec_inst.dt_s}")
    except Exception as e:
        check("import probe: DNRateDecoder() with defaults instantiates",
              False, f"{type(e).__name__}: {e} (AST/grep fallback used, vendor NOT stubbed)")
        traceback.print_exc(limit=1)

    n_pass = sum(1 for _, p, _ in results if p)
    print(f"\n{n_pass}/{len(results)} passed")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
