"""Run a project: critical surface per selected method (or a user surface)."""

from __future__ import annotations

import datetime as _dt
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import numpy as np

from slipsurface.geometry import CircularSurface, PolylineSurface, SlopeGeometry
from slipsurface.lem import METHODS, analyze, method_name
from slipsurface.optimizer import SearchCancelled, SearchResult, SearchSettings, search
from slipsurface.project import EFFORT, Project


@dataclass
class AnalysisResults:
    project: Project
    geometry: SlopeGeometry
    results: dict[str, SearchResult] = field(default_factory=dict)  # method key -> result
    errors: dict[str, str] = field(default_factory=dict)
    elapsed: float = 0.0
    finished: str = ""

    @property
    def methods(self) -> list[str]:
        return list(self.results)

    def global_minimum(self) -> tuple[str, SearchResult] | None:
        ok = [(k, r) for k, r in self.results.items() if np.isfinite(r.fos)]
        return min(ok, key=lambda kr: kr[1].fos) if ok else None


def extend_to_ground(geom: SlopeGeometry, pts) -> np.ndarray:
    """Extend a user polyline along its end segments until each end is above
    the ground (hand-drawn ends often stop a hair below the surface)."""
    pts = np.asarray(pts, dtype=float)
    pts = pts[np.argsort(pts[:, 0], kind="stable")]  # by x only: same-x points keep order
    span = geom.x_max - geom.x_min
    out = [p for p in pts]
    for end, nxt, limit in ((0, 1, geom.x_min), (-1, -2, geom.x_max)):
        p0, p1 = pts[end], pts[nxt]
        if p0[1] > geom.ground_y(p0[0]) + 1e-9:
            continue
        d = p0 - p1
        if abs(d[0]) < 1e-12:
            continue
        d = d / abs(d[0])  # unit step in x, outward
        for step in np.linspace(0, span, 400)[1:]:
            q = p0 + d * step
            if (end == 0 and q[0] < limit) or (end == -1 and q[0] > limit):
                break
            if q[1] > geom.ground_y(q[0]):
                if end == 0:
                    out.insert(0, q)
                else:
                    out.append(q)
                break
    return np.asarray(out)


def _kv_cases(p: Project) -> list[float]:
    """Vertical coefficients to solve. Positive kv is upward."""
    kv = float(p.seismic.kv)
    if p.seismic.both_vertical and kv != 0.0:
        return [kv, -kv]
    return [kv]


def _at_kv(p: Project, kv: float) -> Project:
    if float(p.seismic.kv) == kv:
        return p
    trial = p.copy()
    trial.seismic.kv = kv
    return trial


def governing_kv_lines(p: Project, results: dict) -> list[str]:
    """One Turkish line per method when both vertical directions were solved."""
    if not (p.seismic.both_vertical and p.seismic.kv != 0.0):
        return []
    lines = []
    for key, res in results.items():
        gkv = getattr(res, "kv", None)
        if gkv is None:
            continue
        sense = "yukarı" if gkv > 0 else ("aşağı" if gkv < 0 else "sıfır")
        lines.append(f"Kritik düşey - {method_name(key)}: kv = {gkv:g} ({sense})")
    return lines


def search_settings(p: Project, method: str) -> SearchSettings:
    s = p.surfaces
    pop, it = EFFORT.get(s.effort, EFFORT["normal"])
    return SearchSettings(
        method=method,
        surface_type=(
            ("spline" if s.noncircular_shape == "spline" else "polyline")
            if s.surface_type == "noncircular"
            else "circular"
        ),
        n_slices=p.methods.n_slices,
        popsize=pop,
        maxiter=it,
        seed=s.seed,
        n_ctrl=s.n_ctrl,
        convex_only=s.convex_only,
        check_admissibility=p.advanced.check_admissibility,
        left_range=(float(s.left_range[0]), float(s.left_range[1])) if s.left_range else None,
        right_range=(float(s.right_range[0]), float(s.right_range[1])) if s.right_range else None,
        slice_opts=p.slice_options(),
        solver_kw=p.solver_kw(),
    )


def run_analysis(
    p: Project,
    progress: Callable[[int, int, str, int, float], bool | None] | None = None,
    status: dict | None = None,
) -> AnalysisResults:
    """`progress(i, n, method, generation, best)` returning True cancels.

    `status` (optional) is updated in place with the search state of the
    current method (see optimizer.search) plus `method`, `index`, `n_methods`,
    `n_slices` and `done` (finished methods: key -> FoS or error text)."""
    stat = status if status is not None else {}
    stat.update(done={}, n_slices=p.methods.n_slices)
    t0 = time.perf_counter()
    geom = p.build_geometry()
    mats = p.build_materials()
    methods = [m for m in p.methods.methods if m in METHODS]
    if not methods:
        raise ValueError("Proje Ayarları → Yöntemler: en az bir yöntem seçin.")
    out = AnalysisResults(p.copy(), geom)
    n = len(methods)
    cases = _kv_cases(p)

    def keep(method: str, found: SearchResult, kv: float) -> None:
        found.kv = kv
        prev = out.results.get(method)
        if prev is None or found.fos < prev.fos:
            out.results[method] = found
        kept = out.results[method]
        stat["done"][method] = kept.fos
        stat["best"] = kept.fos

    def finish_cases(method: str, failures: list[tuple[float, str]]) -> None:
        if not failures:
            return
        # A minimum over only the successful directions is not the governing
        # result of the requested analysis. Preserve every failed direction.
        out.results.pop(method, None)
        message = (
            "; ".join(f"kv = {kv:g}: {reason}" for kv, reason in failures)
            if len(cases) > 1
            else failures[0][1]
        )
        out.errors[method] = message
        stat["done"][method] = message
        stat["best"] = float("nan")

    if p.surfaces.surface_type == "user":
        if p.surfaces.user_circle is not None:
            surf = CircularSurface(*p.surfaces.user_circle)
        else:
            pts = p.surfaces.user_surface
            if not pts or len(pts) < 2:
                raise ValueError("Kullanıcı tanımlı yüzey veya verilen daire bulunamadı.")
            surf = PolylineSurface(extend_to_ground(geom, pts))
        for i, m in enumerate(methods):
            stat.update(method=m, index=i, n_methods=n, stage="user", surface_type="user")
            if progress and progress(i, n, m, 0, np.nan):
                raise SearchCancelled()
            if m == "bishop" and not isinstance(surf, CircularSurface):
                out.errors[m] = "Bishop yalnızca dairesel yüzeyler için geçerlidir."
                stat["done"][m] = out.errors[m]
                continue
            failures: list[tuple[float, str]] = []
            for kv in cases:
                if progress and progress(i, n, m, 0, stat.get("best", np.nan)):
                    raise SearchCancelled()
                trial = _at_kv(p, kv)
                stat["kv"] = kv
                res, s = analyze(
                    geom, surf, mats, method=m, opts=trial.slice_options(), **trial.solver_kw()
                )
                if s is None or not res.ok:
                    failures.append((kv, res.message or "çözüm yok"))
                    continue
                if trial.advanced.check_admissibility and not res.admissible:
                    failures.append((kv, res.issue or "Kabul edilebilir olmayan çözüm."))
                    continue
                keep(
                    m,
                    SearchResult(
                        surf,
                        res.fos,
                        res,
                        s,
                        1,
                        [],
                        "verilen daire"
                        if isinstance(surf, CircularSurface)
                        else "kullanıcı yüzeyi",
                        m,
                    ),
                    kv,
                )
            finish_cases(m, failures)
    else:
        for i, m in enumerate(methods):
            stat.update(method=m, index=i, n_methods=n)
            if p.surfaces.surface_type == "noncircular" and m == "bishop":
                out.errors[m] = (
                    "Bishop yalnızca dairesel yüzeyler için geçerlidir; "
                    "dairesel olmayan aramada atlandı."
                )
                stat["done"][m] = out.errors[m]
                continue

            failures = []
            for kv in cases:
                trial = _at_kv(p, kv)
                stat["kv"] = kv

                def prog(gen, best, i=i, m=m):
                    return progress(i, n, m, gen, best) if progress else None

                try:
                    found = search(geom, mats, search_settings(trial, m), prog, stat)
                except SearchCancelled:
                    raise
                except (RuntimeError, ValueError) as exc:
                    failures.append((kv, str(exc)))
                    continue
                keep(m, found, kv)
            finish_cases(m, failures)

    out.elapsed = time.perf_counter() - t0
    out.finished = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return out


def report_text(r: AnalysisResults, tr: Callable[[str], str] = lambda s: s) -> str:
    """Plain-text analysis report (Info Viewer). `tr` translates the words that
    are embedded inside padded columns (the UI passes its translator)."""
    p = r.project
    L = [
        "SlipSurfaceIQ LE — Analiz Raporu",
        "=" * 60,
        f"Proje        : {p.summary.title}",
        f"Analiz       : {p.summary.analysis}",
        f"Hazırlayan   : {p.summary.author}",
        f"Kurum        : {p.summary.company}",
        f"Oluşturulma  : {p.summary.date_created}",
        f"Analiz zamanı: {r.finished} ({r.elapsed:.1f} s)",
        "",
    ]
    for c in p.summary.comments:
        if c:
            L.append(f"Not: {c}")
    g = p.general
    L += [
        "Proje ayarları",
        "-" * 60,
        "Birimler           : Metrik (kN, kPa, m)",
        f"Göçme yönü         : "
        f"{tr('Sağdan sola' if g.failure_direction == 'right_to_left' else 'Soldan sağa')}",
        f"Dilim sayısı       : {p.methods.n_slices}",
        f"Tolerans / maks. it: {p.methods.tolerance} / {p.methods.max_iter}",
        f"Arayüz fonksiyonu  : {p.methods.interslice} (GLE)",
        f"Yeraltı suyu       : {p.groundwater.method}, γw = {p.groundwater.gamma_w}",
        f"Sismik             : {p.seismic.clause()}",
        f"Yüzey tipi         : {p.surfaces.surface_type}",
        "",
    ]
    for line in governing_kv_lines(p, r.results):
        L.insert(-1, line)
    L += ["Malzemeler", "-" * 60]
    from slipsurface.materials.catalog import model_name, parameter_text

    for m in p.materials:
        gs = m.gamma_sat if m.use_sat else m.gamma
        L.append(
            f"{m.name:18s} {tr(model_name(m.model)):26s} γ={m.gamma:g}  γsat={gs:g}  "
            f"{parameter_text(m)}"
        )
    if p.tension_crack:
        xs = [q[0] for q in p.tension_crack]
        L += [
            "",
            "Gerilme çatlağı",
            "-" * 60,
            f"Çatlak çizgisi x = {min(xs):.2f} – {max(xs):.2f}, "
            f"çatlak suyu: %{100 * p.groundwater.crack_water:.0f} dolu",
        ]
    if p.loads:
        L += ["", "Dış yükler", "-" * 60]
        for i, ld in enumerate(p.loads, 1):
            if ld["kind"] == "distributed":
                (x1, _), (x2, _) = ld["points"]
                yon = "düşey" if ld.get("orientation", "vertical") == "vertical" else "yüzeye dik"
                L.append(
                    f"{i:2d}. Yayılı yük  x = {x1:.2f} – {x2:.2f}  q = {ld['q'][0]:g} – "
                    f"{ld['q'][1]:g} kPa ({yon})"
                )
            else:
                x, y = ld["point"]
                L.append(
                    f"{i:2d}. Tekil yük   ({x:.2f}, {y:.2f})  P = {ld['magnitude']:g} kN/m, "
                    f"açı {ld.get('angle', 270):g}°"
                )
    if p.supports or p.support_patterns:
        from slipsurface.loads import SUPPORT_KINDS

        L += ["", "Destek tipleri", "-" * 60]
        for t in p.support_types:
            L.append(
                f"{t.name:16s} {tr(SUPPORT_KINDS[t.kind]):30s} aralık {t.spacing:g} m  "
                f"çekme {t.tensile:g} kN  "
                f"{tr('pasif' if t.application == 'passive' else 'aktif')}"
            )
        L += ["", "Destekler", "-" * 60]
        for i, sp in enumerate(p.supports, 1):
            L.append(
                f"{i:2d}. {sp['type']:16s} A=({sp['a'][0]:.2f}, {sp['a'][1]:.2f})  "
                f"B=({sp['b'][0]:.2f}, {sp['b'][1]:.2f})"
            )
    L += [
        "",
        "Sonuçlar (yöntem başına kritik yüzey)",
        "-" * 60,
        f"{tr('Yöntem'):26s} {'FS':>7s}  {'λ':>7s}  {tr('çıkış x'):>8s}  "
        f"{tr('giriş x'):>8s}  {tr('yüzey')}",
    ]
    for k, res in r.results.items():
        s = res.surface
        lam = f"{res.lem.lam:7.3f}" if res.lem.lam == res.lem.lam else "      –"
        geo = (
            f"merkez ({cast(CircularSurface, s).xc:.2f}, "
            f"{cast(CircularSurface, s).yc:.2f}), R={cast(CircularSurface, s).r:.2f}"
            if hasattr(s, "r")
            else type(s).__name__
        )
        L.append(
            f"{method_name(k):26s} {res.fos:7.3f}  {lam}  {res.slices.x_exit:8.2f}  "
            f"{res.slices.x_entry:8.2f}  {geo}"
        )
    for k, e in r.errors.items():
        L.append(f"{method_name(k):26s}   –      ({e})")
    if p.tension_crack:
        L += ["", "Kritik yüzeylerde gerilme çatlağı", "-" * 60]
        for k, res in r.results.items():
            ck = res.slices.crack
            if ck is None:
                L.append(f"{method_name(k):26s} kritik yüzey çatlak çizgisini kesmiyor")
            else:
                L.append(
                    f"{method_name(k):26s} x = {ck['x']:.2f}  derinlik = {ck['depth']:.2f} m  "
                    f"su = {ck['hw']:.2f} m  itki V = {ck['Pw']:.2f} kN/m"
                )
    if p.facings:
        L += ["", "Kaplamalar (püskürtme beton + hasır çelik)", "-" * 60]
        for ft in p.facing_types:
            L.append(
                f"{ft.name:18s} t = {ft.thickness:g} m  γ = {ft.gamma:g}  "
                f"τ = {ft.tau:g} kPa  hasır {ft.mesh} (As = {ft.mesh_as:g} mm²/m, "
                f"fy = {ft.mesh_fy:g} MPa)  kapasite = {ft.capacity:.1f} kN/m"
            )
        for f in p.facings:
            L.append(
                f"  {f['type']}: x = {min(f['x1'], f['x2']):.2f} – {max(f['x1'], f['x2']):.2f}"
            )
    if p.support_patterns:
        L += ["", "Bulon paternleri", "-" * 60]
        for i, pt in enumerate(p.support_patterns, 1):
            L.append(
                f"{i:2d}. {pt['type']}: x = {pt['p1'][0]:.2f} – {pt['p2'][0]:.2f}, aralık "
                f"{pt['spacing']:g} m, ilk {pt.get('offset', 0):g} m, eğim {pt.get('angle', 15):g}°, "
                f"boy {pt['length']:g} m"
            )
    if p.supports or p.support_patterns or p.facings:
        L += ["", "Kritik yüzeylerde mobilize destek kuvvetleri [kN/m]", "-" * 60]
        for k, res in r.results.items():
            sf = res.slices.support_forces
            if not sf:
                L.append(f"{method_name(k):26s} kritik yüzeyi kesen destek / kaplama yok")
            for f in sf:
                L.append(
                    f"{method_name(k):26s} {f.label}: T_cap = {f.T:8.2f}  "
                    f"T_mob = {f.mobilized(res.fos):8.2f}  "
                    f"(L_iç = {f.L_in:.2f} m, L_dış = {f.L_out:.2f} m, {tr(f.governing)}, "
                    f"{tr('pasif' if f.passive else 'aktif')})"
                )
    gm = r.global_minimum()
    if gm:
        L += ["", f"Global minimum: {method_name(gm[0])} FS = {gm[1].fos:.3f}"]
    return "\n".join(L)
