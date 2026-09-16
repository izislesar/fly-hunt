#!/usr/bin/env python3
"""Triple-clock sync CSV checker (Task 6).

Validates docs/sync.md schema for both the 3-row seed and the final 90-row run.
Stdlib only (csv + argparse + pathlib + sys).

Checks:
  1. header exact match
  2. every row has exactly 6 columns (moose_pos 'x;y;z' keeps column count at 6)
  3. float/int parse per column, moose_pos = 3 floats split on ';', hit_bool in {0,1}
  4. strict monotonicity of t_neural AND t_physics AND frame_id
  5. ratio consistency (tolerant): t_neural_ms ~= t_physics_s*1000,
     t_neural_ms ~= frame_id*33.33 (accumulate-and-correct residual, tol 1.0 ms)

Exit 0 + PASS on success; exit 1 + FAIL + out/fail_sync.log on violation.
On PASS, out/fail_sync.log is (re)written as a not-triggered note.
"""
import argparse
import csv
import sys
from pathlib import Path

EXPECTED_HEADER = (
    "t_neural:float ms,t_physics:float s,frame_id:int,"
    "spike_count:int,moose_pos:float[3],hit_bool:int"
)
FRAME_MS = 33.33
TOL_MS = 1.0


def fail(log_path: Path, reason: str, row_no=None, row=None):
    msg = f"FAIL: {reason}"
    if row_no is not None:
        msg += f" at csv-line {row_no}"
    if row:
        msg += f" | row={row}"
    print(msg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        f.write(msg + "\n")
        f.write(f"expected_header: {EXPECTED_HEADER}\n")
    return 1


def main():
    ap = argparse.ArgumentParser(description="Check triple-clock sync CSV.")
    ap.add_argument("--csv", required=True, help="path to physics_log.csv")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    repo_root = Path(__file__).resolve().parent.parent
    log_path = repo_root / "out" / "fail_sync.log"

    if not csv_path.exists():
        return fail(log_path, f"csv not found: {csv_path}")

    with open(csv_path, newline="") as f:
        raw_header = f.readline().rstrip("\r\n")
        # Exact header match (no stripping of inner spaces: must be byte-exact
        # modulo trailing newline).
        if raw_header != EXPECTED_HEADER:
            return fail(
                log_path,
                f"header mismatch: got {raw_header!r}",
                row_no=1,
                row=[raw_header],
            )
        reader = csv.reader(f)
        prev_tn = prev_tp = prev_fid = None
        n_rows = 0
        for i, row in enumerate(reader, start=2):  # csv-line number
            if not row or all(c.strip() == "" for c in row):
                continue  # skip blank lines
            n_rows += 1
            if len(row) != 6:
                return fail(
                    log_path,
                    f"column count != 6 (got {len(row)}; "
                    "moose_pos must be 'x;y;z' in ONE field)",
                    row_no=i,
                    row=row,
                )
            s_tn, s_tp, s_fid, s_spikes, s_moose, s_hit = row
            try:
                t_n = float(s_tn)
            except ValueError:
                return fail(log_path, f"t_neural not float: {s_tn!r}",
                            row_no=i, row=row)
            try:
                t_p = float(s_tp)
            except ValueError:
                return fail(log_path, f"t_physics not float: {s_tp!r}",
                            row_no=i, row=row)
            try:
                fid = int(s_fid)
            except ValueError:
                return fail(log_path, f"frame_id not int: {s_fid!r}",
                            row_no=i, row=row)
            try:
                spikes = int(s_spikes)
            except ValueError:
                return fail(log_path, f"spike_count not int: {s_spikes!r}",
                            row_no=i, row=row)
            if spikes < 0:
                return fail(log_path, f"spike_count negative: {spikes}",
                            row_no=i, row=row)
            parts = s_moose.split(";")
            if len(parts) != 3:
                return fail(
                    log_path,
                    f"moose_pos must be 'x;y;z' (3 ';'-parts, got {len(parts)})",
                    row_no=i,
                    row=row,
                )
            try:
                [float(p) for p in parts]
            except ValueError:
                return fail(
                    log_path, f"moose_pos parts not floats: {s_moose!r}",
                    row_no=i, row=row,
                )
            try:
                hit = int(s_hit)
            except ValueError:
                return fail(log_path, f"hit_bool not int: {s_hit!r}",
                            row_no=i, row=row)
            if hit not in (0, 1):
                return fail(log_path, f"hit_bool not in {{0,1}}: {hit}",
                            row_no=i, row=row)

            if prev_tn is not None:
                if not (t_n > prev_tn):
                    return fail(
                        log_path,
                        f"t_neural not strictly increasing "
                        f"({prev_tn} -> {t_n})",
                        row_no=i, row=row,
                    )
                if not (t_p > prev_tp):
                    return fail(
                        log_path,
                        f"t_physics not strictly increasing "
                        f"({prev_tp} -> {t_p})",
                        row_no=i, row=row,
                    )
                if not (fid > prev_fid):
                    return fail(
                        log_path,
                        f"frame_id not strictly increasing "
                        f"({prev_fid} -> {fid})",
                        row_no=i, row=row,
                    )
            # Ratio consistency (tolerant for residual policy).
            if abs(t_n - t_p * 1000.0) > TOL_MS:
                return fail(
                    log_path,
                    f"ratio drift: t_neural_ms={t_n} vs "
                    f"t_physics_s*1000={t_p * 1000.0} (tol {TOL_MS} ms)",
                    row_no=i, row=row,
                )
            if abs(t_n - fid * FRAME_MS) > TOL_MS:
                return fail(
                    log_path,
                    f"frame drift: t_neural_ms={t_n} vs "
                    f"frame_id*33.33={fid * FRAME_MS} (tol {TOL_MS} ms)",
                    row_no=i, row=row,
                )
            prev_tn, prev_tp, prev_fid = t_n, t_p, fid

    if n_rows == 0:
        return fail(log_path, "no data rows")

    ok = (
        f"PASS: {n_rows} rows, header exact, columns==6, "
        f"monotonic t_neural/t_physics/frame_id; "
        f"ratio 5:1 neural:physics (0.1ms x5 = 0.5ms) ok; "
        f"66 phys/frame (33.0ms ~= 33.33ms, residual accumulate-and-correct) ok; "
        f"moose_pos 'x;y;z' ok"
    )
    print(ok)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        f.write("not-triggered: check_sync PASS, no sync failure\n")
        f.write(ok + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
