"""C1 brain layout (one-time, CPU, cached) — Task 2 of brain-hunt-viz-10s plan.

Primary: spectral embedding via scipy.sparse.linalg.eigsh on the symmetric
normalized Laplacian (k=2 smallest nonzero eigenvectors), seed=7, budget 10 min.
Fallback: type-grouped radial (11 cluster centers on 600x440 ellipse, ordered by
live count desc from top, radius ~ sqrt(count), jitter sigma=0.35R, seed=7).
Edge layer: top 20000 by weights_init desc, zeros dropped, #5A6B9A a=0.08.

Outputs: out/brain_layout.npz, out/brain_edge_bg.png (640x480),
out/brain_thumb_320x240.png (evidence thumbnail).
"""
import time

import numpy as np
from PIL import Image, ImageDraw

W, H, MARGIN = 640, 480, 24
SEED = 7
BG = (0x0B, 0x10, 0x20)
EDGE_RGB = (0x5A, 0x6B, 0x9A)
EDGE_ALPHA = int(round(0.08 * 255))  # 20
EDGE_BUDGET = 20000
PALETTE = ["#FF6B6B", "#FFA94D", "#FFD43B", "#69DB7C", "#38D9A9", "#4DABF7",
           "#748FFC", "#B197FC", "#F783AC", "#63E6BE", "#E7F5FF"]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rel_lum(rgb):
    def c(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (c(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def fit_to_frame(xy):
    mins = xy.min(axis=0)
    maxs = xy.max(axis=0)
    span = np.maximum(maxs - mins, 1e-9)
    norm = (xy - mins) / span
    return MARGIN + norm * np.array([W - 2 * MARGIN, H - 2 * MARGIN])


def spectral_layout(n, edges, weights):
    import scipy.sparse as sp
    from scipy.sparse.linalg import eigsh
    t0 = time.time()
    mask = weights > 0
    A = sp.csr_matrix((weights[mask], (edges[mask, 0], edges[mask, 1])), shape=(n, n))
    A = (A + A.T) * 0.5  # symmetrize
    deg = np.asarray(A.sum(axis=1)).ravel()
    dinv = 1.0 / np.sqrt(np.maximum(deg, 1e-12))
    D = sp.diags(dinv)
    L = sp.eye(n) - D @ A @ D  # symmetric normalized Laplacian
    rng = np.random.default_rng(SEED)
    vals, vecs = eigsh(L, k=3, which="SM", v0=rng.standard_normal(n))
    order = np.argsort(vals)
    vals, vecs = vals[order], vecs[:, order]
    xy = vecs[:, 1:3]  # skip trivial eigenvector
    return fit_to_frame(xy), time.time() - t0, vals

def radial_layout(types, uniq, counts):
    rng = np.random.default_rng(SEED)
    desc = np.argsort(-counts)
    pos = np.zeros((len(types), 2))
    # Largest cluster fits without overlap: R_max = 70px on the ellipse.
    k_scale = 70.0 / np.sqrt(counts.max())
    radii = {uniq[i]: k_scale * np.sqrt(c) for i, c in enumerate(counts)}
    cx, cy = W / 2, H / 2
    for rank, idx in enumerate(desc):
        ang = -np.pi / 2 + 2 * np.pi * rank / len(desc)
        ex, ey = cx + 300 * np.cos(ang), cy + 220 * np.sin(ang)
        t = uniq[idx]
        R = radii[t]
        sel = np.where(types == t)[0]
        pos[sel, 0] = ex + rng.normal(0, 0.35 * R, size=len(sel))
        pos[sel, 1] = ey + rng.normal(0, 0.35 * R, size=len(sel))
    pos[:, 0] = np.clip(pos[:, 0], MARGIN, W - MARGIN)
    pos[:, 1] = np.clip(pos[:, 1], MARGIN, H - MARGIN)
    return pos


def main():
    d = np.load("data/hunting_circuit_6k.npz")
    types = d["neuron_types"]
    edges = d["edges"]
    weights = d["weights_init"].astype(float)
    n = len(types)
    uniq, counts = np.unique(types, return_counts=True)
    print("live types:", list(uniq), "counts:", list(counts))

    pal = (PALETTE * ((len(uniq) // len(PALETTE)) + 1))[:len(uniq)]
    ratios = [contrast(hex_to_rgb(p), BG) for p in pal]
    for t, p, r in zip(uniq, pal, ratios):
        print(f"contrast {t} {p} vs #0B1020 = {r:.2f}")
    assert all(r >= 3.0 for r in ratios), "palette contrast FAIL — STOP, do not ship"
    type_to_color = {t: pal[i] for i, t in enumerate(uniq)}
    colors = np.array([hex_to_rgb(type_to_color[t]) for t in types], dtype=np.uint8)

    method, wall = "spectral", 0.0
    try:
        pos, wall, vals = spectral_layout(n, edges, weights)
        print(f"spectral wall {wall:.1f}s eigvals {np.round(vals, 4)}")
        if wall > 600:
            raise TimeoutError(f"spectral budget exceeded: {wall:.1f}s > 600s")
    except Exception as e:
        print(f"spectral failed ({e}) → radial fallback")
        t0 = time.time()
        pos = radial_layout(types, uniq, counts)
        wall = time.time() - t0
        method = "radial-fallback"
    print(f"layout method={method} wall={wall:.1f}s")

    # thumbnail readability bar: ≥9/11 cluster centroids separable at 320x240
    thumb = pos / 2.0
    cents = np.array([thumb[types == t].mean(axis=0) for t in uniq])
    sep = 0
    for i in range(len(uniq)):
        nn = min(np.linalg.norm(cents[i] - cents[j]) for j in range(len(uniq)) if j != i)
        ok = nn >= 8.0
        sep += ok
        print(f"thumb {uniq[i]}: nn-dist {nn:.1f}px {'OK' if ok else 'CLOSE'}")
    print(f"thumbnail separable {sep}/{len(uniq)}")
    if method == "spectral" and sep < 9:
        print("spectral hairball → radial fallback")
        pos = radial_layout(types, uniq, counts)
        method = "radial-fallback"
        th2 = pos / 2.0
        c2 = np.array([th2[types == t].mean(axis=0) for t in uniq])
        sep2 = 0
        for i in range(len(uniq)):
            nn = min(np.linalg.norm(c2[i] - c2[j]) for j in range(len(uniq)) if j != i)
            sep2 += nn >= 8.0
        print(f"radial thumbnail separable {sep2}/{len(uniq)}")
        assert sep2 >= 9, "radial thumbnail FAIL"

    np.savez("out/brain_layout.npz", positions=pos.astype(np.float32), colors=colors,
             palette=np.array(pal), type_names=np.array(uniq),
             counts=counts.astype(np.int64), seed=np.int64(SEED), method=np.array(method))
    print("saved out/brain_layout.npz", pos.shape, method)

    # edge layer: top 20K by weights desc, zeros dropped
    # edge layer: top 20K by weights desc, zeros dropped.
    # Spec linewidth is 0.5px; PIL minimum is 1px, so render at 2x
    # supersample with width=1 (== 0.5px at target) then downscale.
    nz = np.where(weights > 0)[0]
    order = nz[np.argsort(-weights[nz])][:EDGE_BUDGET]
    print(f"edges used {len(order)}/{len(edges)} (zeros dropped: {int((weights == 0).sum())})")
    SS = 2
    img = Image.new("RGB", (W * SS, H * SS), BG)
    ov = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    pos_ss = pos * SS
    for e in order:
        a, b = edges[e]
        dr.line([tuple(pos_ss[a]), tuple(pos_ss[b])], fill=EDGE_RGB + (EDGE_ALPHA,), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    img = img.resize((W, H), Image.LANCZOS)
    img.save("out/brain_edge_bg.png")
    arr = np.asarray(img).astype(int)
    bg = np.array(BG)
    above = (np.abs(arr - bg) > 8).any(axis=2)
    cov = above.mean()
    print(f"edge coverage {cov * 100:.2f}% above bg+8 (need <40% and >0)")
    assert 0 < cov < 0.40, "edge coverage FAIL"
    img.resize((320, 240), Image.LANCZOS).save("out/brain_thumb_320x240.png")
    print("saved out/brain_edge_bg.png + out/brain_thumb_320x240.png")


if __name__ == "__main__":
    main()
