"""Slip-centre FS contour map (Slide2 "grid" view) for circular searches.

Every admissible circle the search evaluated is a sample (xc, yc, r, FS).
The centres are binned on a regular grid; each cell keeps the minimum FS of
the circles centred in it (as a Slide2 slip-centre grid reports the lowest FS
over all radii). Empty cells next to filled ones take the nearest value, the
grid is interpolated bilinearly and drawn in discrete FS bands with red
contour lines between the bands.

The field is smoothed (Gaussian), upsampled bicubically and its outline is
anti-aliased; the band boundaries and the outline are drawn as vector iso-lines
(marching squares) so the map stays smooth at any zoom.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtGui import QColor, QImage

# sequential FS palette, low (dark brown/red) -> high (green), 24 bands
PALETTE = [
    "#6c6546",
    "#635037",
    "#5a3b29",
    "#50261a",
    "#47110c",
    "#450703",
    "#5f2b11",
    "#784f1f",
    "#92732d",
    "#ac963c",
    "#b6a83e",
    "#aa9f30",
    "#9e9622",
    "#918d14",
    "#858406",
    "#708000",
    "#558000",
    "#3b8000",
    "#208000",
    "#058000",
    "#007500",
    "#006800",
    "#005b00",
    "#004d00",
]
N_BANDS = len(PALETTE)
LINE = (230, 30, 30)


def _nice_max(v: float) -> float:
    if not math.isfinite(v) or v <= 0:
        return 1.0
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * e >= v:
            return m * e
    return 10 * e


def build_grid(centres: np.ndarray | None, n: int = 26) -> dict | None:
    """Binned minimum-FS grid around the densest part of the centre cloud."""
    if centres is None or len(centres) < 20:
        return None
    c = centres[np.isfinite(centres[:, 3])]
    if len(c) < 20:
        return None
    crit = c[np.argmin(c[:, 3])]
    # the search samples far-away centres (flat, huge circles) too: keep the
    # central 90 % of the cloud and always the critical centre
    x0, x1 = np.percentile(c[:, 0], [5, 95])
    y0, y1 = np.percentile(c[:, 1], [5, 95])
    x0, x1 = min(x0, crit[0]), max(x1, crit[0])
    y0, y1 = min(y0, crit[1]), max(y1, crit[1])
    if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
        return None
    side = max(x1 - x0, y1 - y0) / n
    nx = max(4, int(math.ceil((x1 - x0) / side)))
    ny = max(4, int(math.ceil((y1 - y0) / side)))
    ix = np.floor((c[:, 0] - x0) / side).astype(int)
    iy = np.floor((c[:, 1] - y0) / side).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    grid = np.full((ny, nx), np.inf)
    np.minimum.at(grid, (iy[ok], ix[ok]), c[ok, 3])
    filled = np.isfinite(grid)
    if filled.sum() < 4:
        return None
    from scipy import ndimage

    mask = ndimage.binary_fill_holes(ndimage.binary_closing(filled, iterations=2) | filled)
    _, (jy, jx) = ndimage.distance_transform_edt(~filled, return_indices=True)
    full = grid[jy, jx]
    # colour scale 0 .. ~6.4 x the minimum (as in Slide2's default FS legend), so
    # the critical zone is dark red and flat or nearly vertical circles, whose FS
    # is huge and meaningless, saturate in the top band
    fmin = max(float(crit[3]), 1e-3)
    vmax = _nice_max(6.4 * fmin)
    full = np.minimum(full, 1.2 * vmax)
    # smooth the scattered sampled minimum into a continuous field (never below
    # the critical value); the soft mask gives a rounded outline
    full = np.maximum(ndimage.gaussian_filter(full, 1.3, mode="nearest"), crit[3])
    soft = ndimage.gaussian_filter(mask.astype(float), 1.0, mode="constant")
    return {
        "x0": x0,
        "y0": y0,
        "side": side,
        "nx": nx,
        "ny": ny,
        "values": full,
        "mask": mask,
        "soft_mask": soft,
        "vmax": vmax,
        "crit": (float(crit[0]), float(crit[1]), float(crit[3])),
    }


def band_of(v, vmax: float):
    return np.clip(np.floor(np.asarray(v) / vmax * N_BANDS), 0, N_BANDS - 1).astype(int)


def _fine_fields(g: dict, upsample: int):
    """Smooth (bicubic) upsampled FS and mask fields, cached in the grid dict."""
    key = ("fine", upsample)
    if key not in g:
        from scipy import ndimage

        v = ndimage.zoom(g["values"], upsample, order=3, mode="nearest", grid_mode=True)
        m = ndimage.zoom(g["soft_mask"], upsample, order=3, mode="grid-constant", grid_mode=True)
        # keep only the main region (cubic overshoot leaves small specks)
        lab, n = ndimage.label(m >= 0.5)
        if n > 1:
            sizes = ndimage.sum(np.ones_like(m), lab, index=np.arange(1, n + 1))
            main = lab == 1 + int(np.argmax(sizes))
            m = np.where(ndimage.binary_dilation(main, iterations=3), m, 0.0)
        g[key] = (np.maximum(v, g["crit"][2]), m)
    return g[key]


def render_image(g: dict, upsample: int = 16) -> QImage:
    """RGBA image of the banded map (row 0 = top), anti-aliased at the outline."""
    v, m = _fine_fields(g, upsample)
    bands = band_of(v, g["vmax"])
    pal = np.array([QColor(c).getRgb()[:3] for c in PALETTE], dtype=np.uint8)
    rgb = pal[bands]
    alpha = (np.clip((m - 0.5) * 20.0 + 0.5, 0.0, 1.0) * 255).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])[::-1].copy()  # flip: image row 0 = top
    h, w = rgba.shape[:2]
    img = QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888)
    return img.copy()  # own the buffer


def _march(f: np.ndarray, level: float, valid: np.ndarray | None = None) -> np.ndarray:
    """Marching squares: iso-line segments of `f` at `level` as an (n, 4) array
    (i0, j0, i1, j1) in fractional array indices (row, column)."""
    a, b = f[:-1, :-1], f[:-1, 1:]  # (i, j), (i, j+1)
    c, d = f[1:, 1:], f[1:, :-1]  # (i+1, j+1), (i+1, j)
    ii, jj = np.mgrid[0 : a.shape[0], 0 : a.shape[1]].astype(float)

    def cross(p, q):
        return (p - level) * (q - level) < 0

    def t(p, q):
        return (level - p) / np.where(q - p == 0, 1e-12, q - p)

    edges = [  # (crosses, row, col) for edges a-b, b-c, d-c, a-d
        (cross(a, b), ii, jj + t(a, b)),
        (cross(b, c), ii + t(b, c), jj + 1),
        (cross(d, c), ii + 1, jj + t(d, c)),
        (cross(a, d), ii + t(a, d), jj),
    ]
    count = sum(e[0].astype(int) for e in edges)
    if valid is not None:
        count = np.where(
            valid[:-1, :-1] & valid[1:, 1:] & valid[:-1, 1:] & valid[1:, :-1], count, 0
        )
    segs = []
    sel2 = count == 2
    if sel2.any():
        pts = []
        for e in edges:
            on = e[0] & sel2
            pts.append((on, e[1], e[2]))
        # first and second crossing of each cell, in edge order
        first_i = np.full(a.shape, np.nan)
        first_j = np.full(a.shape, np.nan)
        second_i = np.full(a.shape, np.nan)
        second_j = np.full(a.shape, np.nan)
        for on, ri, rj in pts:
            take_first = on & np.isnan(first_i)
            take_second = on & ~take_first
            first_i = np.where(take_first, ri, first_i)
            first_j = np.where(take_first, rj, first_j)
            second_i = np.where(take_second, ri, second_i)
            second_j = np.where(take_second, rj, second_j)
        segs.append(np.column_stack([first_i[sel2], first_j[sel2], second_i[sel2], second_j[sel2]]))
    sel4 = count == 4  # saddle: pair a-b with b-c, d-c with a-d
    if sel4.any():
        e0, e1, e2, e3 = edges
        segs.append(np.column_stack([e0[1][sel4], e0[2][sel4], e1[1][sel4], e1[2][sel4]]))
        segs.append(np.column_stack([e2[1][sel4], e2[2][sel4], e3[1][sel4], e3[2][sel4]]))
    return np.vstack(segs) if segs else np.zeros((0, 4))


def contour_segments(g: dict, upsample: int = 16) -> np.ndarray:
    """World-coordinate segments (x0, y0, x1, y1) of every band boundary and of
    the outline of the mapped region, for vector (anti-aliased) drawing."""
    if "segments" in g:
        return g["segments"]
    v, m = _fine_fields(g, upsample)
    inside = m >= 0.5
    out = [_march(m, 0.5)]
    step = g["vmax"] / N_BANDS
    for k in range(1, N_BANDS):
        level = k * step
        if v.min() < level < v.max():
            out.append(_march(v, level, inside))
    seg = np.vstack(out)
    # array index (row i, column j) -> world: pixel centres of the zoomed grid
    f = upsample
    s = g["side"]
    x = lambda j: g["x0"] + (j + 0.5) / f * s  # noqa: E731
    y = lambda i: g["y0"] + (i + 0.5) / f * s  # noqa: E731
    g["segments"] = np.column_stack([x(seg[:, 1]), y(seg[:, 0]), x(seg[:, 3]), y(seg[:, 2])])
    return g["segments"]


def legend_labels(vmax: float) -> list[str]:
    """Labels at every second band boundary, the last one with '+'."""
    n = N_BANDS // 2
    out = [f"{vmax * k / n:.3f}".rstrip("0").rstrip(".") for k in range(n + 1)]
    out[-1] += "+"
    return out
