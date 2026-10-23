"""Slip-centre FS map for circular searches.

Every admissible circle the search evaluated is one sample (xc, yc, r, FS).
Samples are binned; a cell stores the lowest FS among circles whose centre
fell in that cell. The stored grid keeps unsampled cells empty.

The picture blends neighbouring samples so the colour and the contour lines
are smooth. A wide gap, where the search placed no centre, stays transparent.
The blend cannot fall outside the sampled FS range.

This is not a radius grid. A centre that was tried at only one radius can
look safer than the radius that would actually govern there.
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
    # Include the closed upper edge in the last cell. Filter by coordinates
    # first so clamping cannot fold far-away outliers into the border cells.
    ok = (c[:, 0] >= x0) & (c[:, 0] <= x1) & (c[:, 1] >= y0) & (c[:, 1] <= y1)
    ix = np.clip(ix, 0, nx - 1)
    iy = np.clip(iy, 0, ny - 1)
    grid = np.full((ny, nx), np.inf)
    np.minimum.at(grid, (iy[ok], ix[ok]), c[ok, 3])
    filled = np.isfinite(grid)
    if int(filled.sum()) < 4:
        return None
    # colour scale 0 .. ~6.4 x the minimum, so the critical zone is dark red
    # and very high, meaningless FS values saturate in the top band
    fmin = max(float(crit[3]), 1e-3)
    vmax = _nice_max(6.4 * fmin)
    values = np.where(filled, np.minimum(grid, 1.2 * vmax), np.nan)
    return {
        "x0": x0,
        "y0": y0,
        "side": side,
        "nx": nx,
        "ny": ny,
        "values": values,
        "mask": filled,
        "soft_mask": filled.astype(float),
        "vmax": vmax,
        "crit": (float(crit[0]), float(crit[1]), float(crit[3])),
        "sampled_only": True,
    }


def band_of(v, vmax: float):
    return np.clip(np.floor(np.asarray(v) / vmax * N_BANDS), 0, N_BANDS - 1).astype(int)


# Gaussian width in cell units. Wide enough to erase the block mosaic,
# narrow enough that a gap of several cells stays clear.
_SMOOTH_SIGMA = 1.05
# Fine-grid weight below this is transparent. The band just above it is the
# anti-aliased outline.
_VISIBLE = 0.22


def _resample(field: np.ndarray, upsample: int) -> np.ndarray:
    """Bilinear samples at the centre of every fine pixel.

    Coarse index iy is the centre of cell iy, so fine pixel i maps to
    (i + 0.5) / upsample - 0.5. Order 1 stays inside the neighbouring values.
    """
    from scipy.ndimage import map_coordinates

    ny, nx = field.shape
    y = (np.arange(ny * upsample) + 0.5) / upsample - 0.5
    x = (np.arange(nx * upsample) + 0.5) / upsample - 0.5
    yy, xx = np.meshgrid(y, x, indexing="ij")
    return map_coordinates(field, np.stack([yy, xx]), order=1, mode="nearest")


def _display_field(g: dict) -> tuple[np.ndarray, np.ndarray]:
    """Smoothed FS and sample weight on the coarse grid.

    Normalized convolution uses only sampled cells, then clips to the sampled
    range so the picture cannot undercut the minimum the search found.
    """
    key = "display"
    if key not in g:
        from scipy.ndimage import gaussian_filter

        mask = g["mask"].astype(float)
        sampled = np.where(g["mask"], g["values"], 0.0)
        weight = gaussian_filter(mask, _SMOOTH_SIGMA, mode="constant", cval=0.0)
        total = gaussian_filter(sampled, _SMOOTH_SIGMA, mode="constant", cval=0.0)
        lo = float(np.nanmin(g["values"]))
        hi = float(np.nanmax(g["values"]))
        field = np.full(mask.shape, float(g["crit"][2]), dtype=float)
        hit = weight > 1e-8
        field[hit] = np.clip(total[hit] / weight[hit], lo, hi)
        g[key] = (field, weight)
    return g[key]


def _fine_fields(g: dict, upsample: int):
    """Smooth FS and sample-weight on the drawing grid."""
    key = ("fine", upsample)
    if key not in g:
        field, weight = _display_field(g)
        lo = float(np.nanmin(g["values"]))
        hi = float(np.nanmax(g["values"]))
        g[key] = (
            np.clip(_resample(field, upsample), lo, hi),
            np.clip(_resample(weight, upsample), 0.0, 1.0),
        )
    return g[key]


def render_image(g: dict, upsample: int = 16) -> QImage:
    """RGBA image of the banded map (row 0 = top), anti-aliased at the outline."""
    v, m = _fine_fields(g, upsample)
    bands = band_of(v, g["vmax"])
    pal = np.array([QColor(c).getRgb()[:3] for c in PALETTE], dtype=np.uint8)
    rgb = pal[bands]
    # soft edge: weight rises from clear to opaque across a fraction of a cell
    alpha = (np.clip((m - _VISIBLE) / 0.35, 0.0, 1.0) * 255).astype(np.uint8)
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
    inside = m >= _VISIBLE + 0.08
    out = [_march(m, _VISIBLE + 0.08)]
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
