#!/usr/bin/env python3
"""Offline-first hunting-circuit selector (Task 5).

Builds data/hunting_circuit_6k.npz with N=5500 neurons (seed 0) from LOCAL
data only. No network access.

Per-type quotas (sum = 5500, plan Scope):
  LC4 104 + LPLC2 210 + T2/T3-vis 800 + ORN 500 + PN 300 + KC 2000 +
  MBON 96 + DAN 100 (PAM+PPL101) + DN 150 (DNpe017, DNp20, GF 2,
  DNa01/02 4, DNp09, rest generic DN) + SEZ-GRN 700 + JO 540 = 5500

Type source (offline, documented fallback chain):
  1. Vendor FlyWire annotations (fly-brain/data/flywire_annotations.tsv,
     read-only reference) joined against the Completeness CSV pool, so every
     selected ID is a real v783 neuron present in data/2025_Completeness_783.csv.
  2. The connectivity parquet (data/2025_Connectivity_783.parquet) carries NO
     type columns -- footer-verified schema is
     [Presynaptic_ID, Postsynaptic_ID, Presynaptic_Index, Postsynaptic_Index,
     Connectivity, Excitatory, Excitatory x Connectivity] -- so per-type
     quotas CANNOT come from the parquet. This mapping fallback is recorded
     in out/circuit.json `sampling_notes`, never silent.
  3. Parquet edge reader: pyarrow (>=25.0.1, venv ~/venv-brainfly314)
     inner-joins Presynaptic_ID/Postsynaptic_ID pairs to the selected 5500
     IDs in chunked 100k-row batches (budget RSS guard). weights_init =
     clip(`Excitatory x Connectivity`, 0, 2) float32 (inhibitory signed<=0
     -> 0 under the excitatory-only W convention, clip [0,2] per reward
     spec). Natural join kept whole when <= EDGE_CAP (300k); larger joins
     are seed-0 uniform subsampled to EDGE_CAP. No synthetic fallback:
     missing pyarrow is fail-closed. Re-running `--seed 0 --target 5500`
     reproduces the REAL-edge npz deterministically (IDs sorted, edges
     lexsorted).

DN 150 composition: DNpe017 x2 + DNp20 x2 + GF(DNp01/Giant Fiber) x2 +
DNa01 x2 + DNa02 x2 + DNp09 x2 = 12 named, rest 138 generic DN* pool.
DAN 100 composition: PPL101 x2 (all that exist) + PAM* x98.
SEZ-GRN 700 composition: gustatory cell_class x408 (all) + 292 from
SEZ-region GNG-associated cell_sub_class pool (AN_*_GNG*), documented.

Determinism: np.random.default_rng(seed); pools sorted before sampling.

Output npz keys (allow_pickle=False loadable; downstream Tasks 10/13):
  neuron_ids (int64, N), neuron_types (<U8 short labels, N),
  cell_type_detail (<U32 full annotation cell_type, N),
  edges (int64, Mx2 local indices), weights_init (float32, M),
  meta_json (0-d unicode JSON: seed/target/N/quotas/notes).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent

# Exact quotas from plan Scope; sum must equal target (default 5500).
QUOTAS = {
    "LC4": 104,
    "LPLC2": 210,
    "T2/T3-vis": 800,
    "ORN": 500,
    "PN": 300,
    "KC": 2000,
    "MBON": 96,
    "DAN": 100,
    "DN": 150,
    "SEZ-GRN": 700,
    "JO": 540,
}

EDGE_CAP = 300_000  # keep-all natural join at/below this; else seed-0 subsample
EDGE_CHUNK = 100_000  # chunked parquet batch guard (RSS)

PARQUET_COLUMNS = [
    "Presynaptic_ID",
    "Postsynaptic_ID",
    "Presynaptic_Index",
    "Postsynaptic_Index",
    "Connectivity",
    "Excitatory",
    "Excitatory x Connectivity",
]


def fail_closed(msg):
    print(f"FAIL-closed: {msg}", file=sys.stderr)
    return 1


def sample(rng, pool, k, what):
    pool = sorted(set(int(x) for x in pool))
    if len(pool) < k:
        print(f"FAIL-closed: pool {what} has {len(pool)} < quota {k}",
              file=sys.stderr)
        raise SystemExit(1)
    idx = rng.choice(len(pool), size=k, replace=False)
    return [pool[i] for i in idx]


def main():
    ap = argparse.ArgumentParser(description="Select offline hunting circuit.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--target", type=int, default=5500)
    ap.add_argument("--completeness", default=str(
        REPO_ROOT / "data" / "2025_Completeness_783.csv"))
    ap.add_argument("--annotations", default=str(
        REPO_ROOT / "fly-brain" / "data" / "flywire_annotations.tsv"))
    ap.add_argument("--parquet", default=str(
        REPO_ROOT / "data" / "2025_Connectivity_783.parquet"))
    ap.add_argument("--output", default=str(
        REPO_ROOT / "data" / "hunting_circuit_6k.npz"))
    args = ap.parse_args()

    if sum(QUOTAS.values()) != args.target:
        return fail_closed(
            f"quotas sum {sum(QUOTAS.values())} != target {args.target}")

    comp_path = Path(args.completeness)
    ann_path = Path(args.annotations)
    pq_path = Path(args.parquet)
    if not comp_path.exists():
        return fail_closed(f"missing local completeness csv: {comp_path}")
    if not ann_path.exists():
        return fail_closed(f"missing local annotations tsv: {ann_path}")
    if not pq_path.exists():
        return fail_closed(f"missing local connectivity parquet: {pq_path}")

    try:
        import pandas as pd  # noqa: F401  (pre-installed only; no pip install)
    except ImportError:
        return fail_closed("pandas not installed and pip installs forbidden")

    import pandas as pd

    rng = np.random.default_rng(args.seed)

    comp_ids = set(pd.read_csv(comp_path, usecols=[0]).iloc[:, 0]
                   .astype("int64").tolist())
    ann = pd.read_csv(ann_path, sep="\t",
                      usecols=["root_id", "cell_type", "hemibrain_type",
                               "cell_class", "cell_sub_class"],
                      low_memory=False)
    ann["root_id"] = ann["root_id"].astype("int64")
    ann = ann[ann["root_id"].isin(comp_ids)].copy()  # real v783 pool only
    ct = ann["cell_type"].fillna("").astype(str)
    hb = ann["hemibrain_type"].fillna("").astype(str)
    cc = ann["cell_class"].fillna("").astype(str)
    csc = ann["cell_sub_class"].fillna("").astype(str)

    def ids(mask):
        return ann.loc[mask, "root_id"].tolist()

    selected = []  # (neuron_id, short_label, detail)
    notes = {}

    # LC4 / LPLC2 (visual projection, looming pathway)
    for label, prefix, k in (("LC4", "LC4", QUOTAS["LC4"]),
                             ("LPLC2", "LPLC2", QUOTAS["LPLC2"])):
        pool = ids(ct.str.startswith(prefix))
        got = sample(rng, pool, k, label)
        for nid in got:
            row = ann.loc[ann["root_id"] == nid].iloc[0]
            selected.append((nid, label, str(row["cell_type"])))
        notes[label] = f"{len(pool)} in pool, sampled {k}"

    # T2/T3-vis
    t2t3 = ids(ct.isin(["T2", "T3", "T2a"]))
    got = sample(rng, t2t3, QUOTAS["T2/T3-vis"], "T2/T3-vis")
    for nid in got:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "T2/T3-vis", str(row["cell_type"])))
    notes["T2/T3-vis"] = (f"{len(t2t3)} in pool (T2/T2a/T3), "
                          f"sampled {QUOTAS['T2/T3-vis']}")

    # ORN / PN (olfactory)
    orn = ids(ct.str.startswith("ORN"))
    got = sample(rng, orn, QUOTAS["ORN"], "ORN")
    for nid in got:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "ORN", str(row["cell_type"])))
    notes["ORN"] = f"{len(orn)} ORN_* in pool, sampled {QUOTAS['ORN']}"
    pn = ids(cc.eq("ALPN"))
    got = sample(rng, pn, QUOTAS["PN"], "PN")
    for nid in got:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "PN", str(row["cell_type"])))
    notes["PN"] = f"{len(pn)} ALPN in pool, sampled {QUOTAS['PN']}"

    # KC (mushroom body Kenyon cells)
    kc = ids(cc.eq("Kenyon_Cell"))
    got = sample(rng, kc, QUOTAS["KC"], "KC")
    for nid in got:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "KC", str(row["cell_type"])))
    notes["KC"] = f"{len(kc)} Kenyon_Cell in pool, sampled {QUOTAS['KC']}"

    # MBON (all 96)
    mbon = ids(cc.eq("MBON"))
    got = sample(rng, mbon, QUOTAS["MBON"], "MBON")
    for nid in got:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "MBON", str(row["cell_type"])))
    notes["MBON"] = f"{len(mbon)} MBON in pool, took all {len(got)}"

    # DAN 100 = PPL101 (2, all) + PAM* (98)
    ppl101 = ids(ct.eq("PPL101"))
    pam = ids(ct.str.startswith("PAM"))
    dan_ids = list(ppl101) + sample(
        rng, [x for x in pam if x not in set(ppl101)],
        QUOTAS["DAN"] - len(ppl101), "DAN-PAM")
    for nid in dan_ids:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "DAN", str(row["cell_type"])))
    notes["DAN"] = (f"PPL101 x{len(ppl101)} (all) + PAM x{len(dan_ids) - len(ppl101)} "
                    f"sampled from {len(pam)}; cell_class DAN total "
                    f"{int(cc.eq('DAN').sum())}")

    # DN 150: 12 named + 138 generic DN*
    named = {}
    for key, mask in (("DNpe017", ct.eq("DNpe017")),
                      ("DNp20", ct.eq("DNp20")),
                      ("DNp09", ct.eq("DNp09")),
                      ("DNa01", ct.eq("DNa01")),
                      ("DNa02", ct.eq("DNa02")),
                      ("GF", hb.eq("Giant Fiber"))):
        named[key] = ids(mask)
    named_ids = []
    for key, lst in named.items():
        named_ids.extend(lst)
    notes["DN_named"] = {k: sorted(int(x) for x in v)
                         for k, v in named.items()}
    generic_dn = ids(ct.str.startswith("DN") & ~ct.isin(
        ["DNpe017", "DNp20", "DNp09", "DNa01", "DNa02"])
        & ~hb.eq("Giant Fiber"))
    # GF rows are cell_type DNp01; excluded above via hb mask
    rest = sample(rng, [x for x in generic_dn if x not in set(named_ids)],
                  QUOTAS["DN"] - len(named_ids), "DN-generic")
    for nid in list(named_ids) + rest:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "DN", str(row["cell_type"])))
    notes["DN"] = (f"named 12 (DNpe017x{len(named['DNpe017'])}, "
                   f"DNp20x{len(named['DNp20'])}, GFx{len(named['GF'])}, "
                   f"DNa01x{len(named['DNa01'])}, DNa02x{len(named['DNa02'])}, "
                   f"DNp09x{len(named['DNp09'])}) + generic DN* x{len(rest)} "
                   f"from {len(generic_dn)}")

    # SEZ-GRN 700 = gustatory (408, all) + GNG-associated SEZ pool (292)
    gust = ids(cc.eq("gustatory"))
    gng = ids(csc.str.contains("GNG", na=False) & ~cc.eq("gustatory"))
    sez_ids = list(gust) + sample(
        rng, [x for x in gng if x not in set(gust)],
        QUOTAS["SEZ-GRN"] - len(gust), "SEZ-GRN-GNG")
    for nid in sez_ids:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "SEZ-GRN", str(row["cell_type"])))
    notes["SEZ-GRN"] = (f"gustatory cell_class x{len(gust)} (all; includes "
                        f"sugar/pharyngeal GRNs) + SEZ-region GNG-associated "
                        f"x{len(sez_ids) - len(gust)} sampled from "
                        f"{len(gng)} (cell_type GRN alone only 71 rows: "
                        f"insufficient, hence documented fallback)")

    # JO (Johnston's organ)
    jo = ids(ct.str.startswith("JO-"))
    got = sample(rng, jo, QUOTAS["JO"], "JO")
    for nid in got:
        row = ann.loc[ann["root_id"] == nid].iloc[0]
        selected.append((nid, "JO", str(row["cell_type"])))
    notes["JO"] = f"{len(jo)} JO-* in pool, sampled {QUOTAS['JO']}"

    assert len(selected) == args.target, (len(selected), args.target)
    sel_ids = [s[0] for s in selected]
    assert len(set(sel_ids)) == args.target, "duplicate neuron IDs selected"

    # Deterministic global order: sort by neuron id for stable downstream use
    selected.sort(key=lambda t: t[0])
    neuron_ids = np.array([s[0] for s in selected], dtype=np.int64)
    neuron_types = np.array([s[1] for s in selected])
    cell_detail = np.array([s[2] for s in selected])

    # Parquet evidence: magic bytes + size + sha256 (types still come from
    # vendor annotations TSV joined to completeness CSV pool -- parquet has
    # no type columns).
    import hashlib
    pq_bytes = pq_path.stat().st_size
    with open(pq_path, "rb") as f:
        head = f.read(4)
        f.seek(-4, 2)
        tail = f.read(4)
    parquet_ok = (head == b"PAR1" and tail == b"PAR1")
    sha = hashlib.sha256()
    with open(pq_path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            sha.update(blk)
    parquet_sha = sha.hexdigest()
    try:
        import pyarrow  # noqa: F401
        import pyarrow.parquet as _pq
        engine = f"pyarrow {pyarrow.__version__}"
    except ImportError:
        return fail_closed("pyarrow not installed; real edges unreadable "
                           "(no synthetic fallback)")

    # REAL edges: inner-join parquet pairs to selected IDs, chunked 100k
    # batches per budget guard. Deterministic: same IDs (seed-0 quotas above)
    # + lexsorted edge order; cap subsample uses the same seed-0 RNG stream.
    id2idx = {int(nid): i for i, nid in enumerate(neuron_ids.tolist())}
    sel = set(id2idx)
    pf = _pq.ParquetFile(str(pq_path))
    parquet_rows = pf.metadata.num_rows
    pre_parts, post_parts, signed_parts = [], [], []
    n_matched = 0
    for batch in pf.iter_batches(
            batch_size=EDGE_CHUNK,
            columns=["Presynaptic_ID", "Postsynaptic_ID",
                     "Excitatory x Connectivity"]):
        d = batch.to_pydict()
        pre = np.asarray(d["Presynaptic_ID"], dtype=np.int64)
        post = np.asarray(d["Postsynaptic_ID"], dtype=np.int64)
        m = (np.fromiter((int(x) in sel for x in pre.tolist()),
                         dtype=bool, count=len(pre))
             & np.fromiter((int(x) in sel for x in post.tolist()),
                           dtype=bool, count=len(post)))
        if not m.any():
            continue
        pre_parts.append(np.vectorize(id2idx.__getitem__)(pre[m]))
        post_parts.append(np.vectorize(id2idx.__getitem__)(post[m]))
        signed_parts.append(
            np.asarray(d["Excitatory x Connectivity"], dtype=np.int64)[m])
        n_matched += int(m.sum())
    pre_all = (np.concatenate(pre_parts).astype(np.int64) if pre_parts
               else np.zeros(0, dtype=np.int64))
    post_all = (np.concatenate(post_parts).astype(np.int64) if post_parts
                else np.zeros(0, dtype=np.int64))
    signed_all = (np.concatenate(signed_parts).astype(np.int64)
                  if signed_parts else np.zeros(0, dtype=np.int64))
    if n_matched == 0:
        return fail_closed("parquet join yielded 0 edges for selected IDs")
    cap_rule = f"keep-all natural join (S={n_matched})"
    if n_matched > EDGE_CAP:
        keep = rng.choice(n_matched, size=EDGE_CAP, replace=False)
        keep.sort()
        pre_all, post_all, signed_all = (pre_all[keep], post_all[keep],
                                         signed_all[keep])
        cap_rule = (f"cap {EDGE_CAP} seed-0 uniform subsample of natural "
                    f"join S_nat={n_matched}")
    edges = np.column_stack([pre_all, post_all]).astype(np.int64)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges = edges[order]
    signed_all = signed_all[order]
    weights = np.clip(signed_all, 0, 2).astype(np.float32)
    w_stats = {"min": float(weights.min()), "max": float(weights.max()),
               "mean": float(weights.mean()),
               "zeros": int((weights == 0).sum()),
               "finite": bool(np.isfinite(weights).all())}

    meta = {
        "seed": args.seed,
        "target": args.target,
        "N": int(args.target),
        "quotas": QUOTAS,
        "n_syn_stored": int(len(edges)),
        "parquet": {
            "path": "data/2025_Connectivity_783.parquet",
            "bytes": pq_bytes,
            "magic_ok": bool(parquet_ok),
            "columns": PARQUET_COLUMNS,
            "rows": int(parquet_rows),
            "sha256": parquet_sha,
            "note": ("No type columns in parquet (footer-verified); "
                     "types come from vendor annotations TSV joined to "
                     "completeness CSV pool."),
        },
        "parquet_sha": parquet_sha,
        "edge_engine": engine,
        "edge_source": {
            "method": ("inner-join Presynaptic_ID/Postsynaptic_ID to "
                       "selected 5500 FlyWire IDs, chunked 100k-row batches"),
            "parquet_rows": int(parquet_rows),
            "matched": int(n_matched),
            "rule": cap_rule,
            "final_S": int(len(edges)),
        },
        "weight_rule": ("clip(Excitatory x Connectivity, 0, 2) float32; "
                        "inhibitory signed<=0 -> 0 (excitatory-only W "
                        "convention, clip [0,2])"),
        "weight_stats": w_stats,
        "edges_real": True,
        "edges_synthetic": False,
        "built_with": engine,
        "backup": "out/hunting_circuit_6k.synthetic.bak.npz",
        "sampling_notes": notes,
        "vendor_ref": ("fly-brain/ SHA 27cec28d (read-only): "
                       "brain_body_bridge.py DN_NEURONS/STIMULI + "
                       "data/flywire_annotations.tsv; sg(1) ast-grep not "
                       "installed -> used grep -rn for DNpe017/DNp20/DNp09 "
                       "confirmation instead."),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path,
             neuron_ids=neuron_ids,
             neuron_types=neuron_types,
             cell_type_detail=cell_detail,
             edges=edges,
             weights_init=weights,
             meta_json=np.asarray(json.dumps(meta, default=str)))
    rss_gb = (args.target * 10 * 8 + len(edges) * 8 + 1.5e9) / 1e9
    print(f"wrote {out_path} N={args.target} syn={len(edges)} "
          f"rss_est={rss_gb:.4f}GB seed={args.seed}")
    for label in QUOTAS:
        n = int((neuron_types == label).sum())
        print(f"  {label}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
