"""ACADS EX1(a) benchmark — coarse grid search + slice plot (no GUI).

    python examples/acads_1a.py            -> prints FoS, saves acads_1a.png
"""

import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from slipsurface.geometry import CircularSurface, simple_slope  # noqa: E402
from slipsurface.lem import analyze_circle, ordinary  # noqa: E402
from slipsurface.materials import MohrCoulomb  # noqa: E402

geom = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
mats = {"Zemin 1": MohrCoulomb("Zemin 1", gamma=20, c=3, phi=19.6)}

t0 = time.perf_counter()
best = (np.inf, None)
n = 0
for xc in np.arange(15, 40, 1.0):
    for yc in np.arange(12, 40, 1.0):
        for r in np.arange(5, 45, 0.5):
            res, _ = analyze_circle(geom, CircularSurface(xc, yc, r), mats)
            n += 1
            if res.ok and res.fos < best[0]:
                best = (res.fos, CircularSurface(xc, yc, r))
dt = time.perf_counter() - t0

fos, surf = best
res, s = analyze_circle(geom, surf, mats)
print(f"{n} surfaces in {dt:.1f} s ({dt / n * 1e3:.2f} ms each)")
print(f"Bishop   FoS = {fos:.3f}   (ACADS ref 1.00, Slide2 0.987)")
print(f"Ordinary FoS = {ordinary(s).fos:.3f}")
print(f"Centre ({surf.xc:.1f}, {surf.yc:.1f}), R = {surf.r:.1f}, slices = {s.n}")

fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
poly = np.asarray(geom.regions[0].polygon.exterior.coords)
ax.fill(poly[:, 0], poly[:, 1], color="#d9c49a", ec="#5a4a2a")
for x0, _x1 in zip(s.xl, s.xr, strict=False):
    ax.plot([x0, x0], [surf.y(x0), geom.ground_y(x0)], color="#7a5c2e", lw=0.6)
ax.plot(*s.base_points().T, color="#c0392b", lw=2)
ax.plot(surf.xc, surf.yc, "+", color="#c0392b", ms=10)
ax.set_aspect("equal")
ax.set_title(f"ACADS 1(a) — Simplified Bishop FoS = {fos:.3f}")
ax.grid(ls=":")
fig.savefig("acads_1a.png", dpi=130)
