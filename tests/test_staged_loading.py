"""B-bar excess pore pressure, the SHANSEP OCR profile and the separate
analysis process, checked against hand calculations."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from slipsurface.analysis import run_analysis  # noqa: E402
from slipsurface.geometry import CircularSurface  # noqa: E402
from slipsurface.lem import analyze  # noqa: E402
from slipsurface.lem.slicing import make_slices  # noqa: E402
from slipsurface.materials import Shansep  # noqa: E402
from slipsurface.project import MaterialSpec, Project, _mk  # noqa: E402

FILL_GAMMA, CLAY_GAMMA, CLAY_TOP = 20.0, 17.0, 10.0
CIRCLE = CircularSurface(34.0, 22.0, 17.0)  # through the fill into the clay


def embankment(bbar=0.0, loading=True, clay=None) -> Project:
    """4 m fill (crest y = 14, x <= 26, 1:2 face to x = 34) on 10 m of clay."""
    clay = clay or MaterialSpec("Clay", "MC", CLAY_GAMMA, CLAY_GAMMA, False, 5.0, 24.0)
    clay.bbar = bbar
    fill = MaterialSpec("Fill", "MC", FILL_GAMMA, FILL_GAMMA, False, 0.0, 35.0)
    fill.excess_load = loading
    p = _mk(
        "Embankment on clay",
        [clay, fill],
        [[0, 0], [60, 0], [60, 10], [34, 10], [26, 14], [0, 14]],
        bounds=[[[0, 10], [34, 10]]],
        assigns=[((10, 12), "Fill"), ((30, 5), "Clay")],
        methods=["bishop", "spencer"],
        n_slices=40,
    )
    p.general.failure_direction = "left_to_right"
    p.groundwater.method = "none"
    return p


def slices(p: Project):
    return make_slices(p.build_geometry(), CIRCLE, p.build_materials(), opts=p.slice_options())


def fill_height(s) -> np.ndarray:
    return np.maximum(s.y_top - CLAY_TOP, 0.0)


def test_excess_pore_pressure_is_bbar_times_the_fill_weight():
    s = slices(embankment(bbar=0.6))
    in_clay = np.array([s.materials[i].name == "Clay" for i in s.mat_idx])
    assert in_clay.any() and (~in_clay).any()
    expected = np.where(in_clay, 0.6 * FILL_GAMMA * fill_height(s), 0.0)
    # the fill column is sampled at n_sub points: allow that resolution
    assert np.allclose(s.u_excess, expected, atol=0.6 * FILL_GAMMA * 14 / 40)
    assert np.allclose(s.u, s.u_excess)  # dry model: nothing else
    under_crest = in_clay & (s.xr <= 26.0)
    assert np.allclose(s.u_excess[under_crest], 0.6 * FILL_GAMMA * 4.0, rtol=0.03)


@pytest.mark.parametrize("method", ["bishop", "spencer", "janbu_simplified"])
def test_switched_off_bbar_changes_nothing_and_bbar_lowers_the_factor(method):
    def fos(p):
        res, _ = analyze(
            p.build_geometry(), CIRCLE, p.build_materials(), method=method, opts=p.slice_options()
        )
        assert res.ok
        return res.fos

    base = fos(embankment(bbar=0.0, loading=False))
    assert fos(embankment(bbar=0.0, loading=True)) == base  # no B-bar material
    assert fos(embankment(bbar=0.7, loading=False)) == base  # nothing loads it
    half, full = fos(embankment(bbar=0.5)), fos(embankment(bbar=1.0))
    assert full < half < base


def test_excess_pressure_adds_to_the_water_table_pressure():
    p = embankment(bbar=0.5)
    p.groundwater.method = "water_table"
    p.water_table = [[0, 9.0], [60, 9.0]]
    s = slices(p)
    q = embankment(bbar=0.0)
    q.groundwater.method, q.water_table = "water_table", p.water_table
    assert np.allclose(s.u - s.u_excess, slices(q).u)


def test_shansep_under_a_fill_uses_the_pre_loading_stress_with_bbar_one():
    clay = MaterialSpec("Clay", "SH", CLAY_GAMMA, CLAY_GAMMA, shansep_s=0.25, shansep_m=0.8)
    s = slices(embankment(bbar=1.0, clay=clay))
    in_clay = np.array([s.materials[i].name == "Clay" for i in s.mat_idx])
    before = CLAY_GAMMA * (CLAY_TOP - s.y_base)  # overburden of the clay alone
    assert np.allclose(s.sigma_v_eff[in_clay], before[in_clay], atol=FILL_GAMMA * 14 / 40)
    assert np.all(s.u == 0)  # total-stress strength: no pore pressure in the equations
    drained = slices(embankment(bbar=0.0, clay=clay))  # fully consolidated under the fill
    assert np.all(drained.sigma_v_eff[in_clay] >= s.sigma_v_eff[in_clay] - 1e-9)
    assert drained.sigma_v_eff[in_clay].max() > s.sigma_v_eff[in_clay].max() + 20


def test_ocr_profile_is_linear_between_the_elevations_and_constant_outside():
    m = Shansep("c", 17, s_ratio=0.22, m_exp=0.8, ocr=4.0, ocr_bottom=1.0, y_top=10.0, y_bottom=0.0)
    assert np.allclose(m.ocr_at(np.array([12.0, 10.0, 5.0, 0.0, -3.0])), [4, 4, 2.5, 1, 1])
    su = m.strength(np.zeros(1), sigma_v=np.array([50.0]), y=np.array([5.0]))[0][0]
    assert su == pytest.approx(0.22 * 50.0 * 2.5**0.8)
    with pytest.raises(ValueError, match="base elevation"):
        m.strength(np.zeros(1), sigma_v=np.array([50.0]))
    constant = Shansep("c", 17, ocr=2.0)  # no profile: as before
    assert constant.ocr_at(np.array([5.0])) == 2.0 and not constant.uses_elevation
    with pytest.raises(ValueError, match="top elevation"):
        Shansep("c", 17, y_top=0.0, y_bottom=5.0)


def test_ocr_profile_reaches_the_slice_strength_and_raises_the_factor():
    from slipsurface.lem.bishop import slice_strength

    def clay(**kw):
        return MaterialSpec("Clay", "SH", CLAY_GAMMA, CLAY_GAMMA, shansep_s=0.25, **kw)

    flat = embankment(clay=clay(ocr=1.0))
    crust = embankment(clay=clay(ocr=5.0, ocr_bottom=1.0, ocr_y_top=10.0, ocr_y_bottom=4.0))
    s = slices(crust)
    i = int(np.flatnonzero([s.materials[k].name == "Clay" for k in s.mat_idx])[0])
    ocr = 5.0 + np.clip((10.0 - s.y_base[i]) / 6.0, 0, 1) * (1.0 - 5.0)
    assert slice_strength(s, i)[0] == pytest.approx(0.25 * s.sigma_v_eff[i] * ocr**0.8)
    f_flat = run_analysis(_fixed(flat)).results["spencer"].fos
    f_crust = run_analysis(_fixed(crust)).results["spencer"].fos
    assert f_crust > f_flat


def _fixed(p: Project) -> Project:
    p.methods.methods = ["spencer"]
    p.surfaces.surface_type = "user"
    p.surfaces.user_circle = [CIRCLE.xc, CIRCLE.yc, CIRCLE.r]
    return p


def test_file_version_marks_models_an_older_program_would_solve_differently(tmp_path):
    plain = embankment()
    plain.materials[1].excess_load = False
    assert plain.to_dict()["version"] == 3
    staged = embankment(bbar=0.5)
    assert staged.to_dict()["version"] == 4
    profile = embankment(
        clay=MaterialSpec("Clay", "SH", 17, 17, ocr=3.0, ocr_y_top=10.0, ocr_y_bottom=2.0)
    )
    assert profile.to_dict()["version"] == 4
    path = tmp_path / "m.slp.json"
    staged.save(path)
    back = Project.load(path)
    assert back.materials[0].bbar == 0.5 and back.materials[1].excess_load
    assert back.to_dict() == staged.to_dict()
    with pytest.raises(ValueError, match="B-bar"):
        embankment(bbar=1.5).validate()
    newer = staged.to_dict() | {"version": 5}
    with pytest.raises(ValueError, match="newer version"):
        Project.from_dict(newer)


def test_materials_dialog_edits_bbar_and_the_loading_flag():
    from PySide6.QtWidgets import QApplication

    from slipsurface.ui.dialogs.materials import MaterialsDialog

    QApplication.instance() or QApplication([])
    dlg = MaterialsDialog(embankment(bbar=0.4).materials)
    assert dlg.bbar.value() == 0.4 and not dlg.excess_load.isChecked()
    dlg.bbar.setValue(0.9)
    dlg.list.setCurrentRow(1)
    assert dlg.excess_load.isChecked() and dlg.bbar.value() == 0.0
    dlg.excess_load.setChecked(False)
    mats = dlg.result_materials()
    assert mats[0].bbar == 0.9 and not mats[1].excess_load


# ------------------------------------------------------------ separate process
def test_analysis_in_a_separate_process_gives_the_same_results():
    from slipsurface.compute_process import ProcessAnalysis

    p = embankment(bbar=0.5)
    p.surfaces.effort = "fast"
    job = ProcessAnalysis(p)
    job.start()
    events = list(job.events())
    kinds = [k for k, _ in events]
    assert kinds[-1] == "result" and set(kinds[:-1]) <= {"progress"}
    got, ref = events[-1][1], run_analysis(p)
    assert {k: v.fos for k, v in got.results.items()} == {k: v.fos for k, v in ref.results.items()}
    assert got.project.to_dict() == ref.project.to_dict()
    assert np.array_equal(got.results["bishop"].centres, ref.results["bishop"].centres)
    status = [payload[5] for kind, payload in events if kind == "progress"]
    assert status and "stage" in status[-1]


def test_separate_process_reports_errors_and_stops_on_request():
    import time

    from slipsurface.compute_process import ProcessAnalysis

    broken = embankment()
    broken.methods.methods = []
    job = ProcessAnalysis(broken)
    job.start()
    kind, text = list(job.events())[-1]
    assert kind == "error" and "at least one method" in text

    slow = embankment()
    slow.surfaces.effort = "fine"
    slow.methods.methods = ["spencer", "gle", "janbu_corrected", "bishop"]
    job = ProcessAnalysis(slow)
    job.start()
    started = time.monotonic()
    last = None
    for kind, _ in job.events():
        last = kind
        if kind == "progress":
            job.request_stop()
    assert last == "cancelled" and time.monotonic() - started < 60


def test_worker_relays_the_process_to_qt_signals(monkeypatch):
    from PySide6.QtWidgets import QApplication

    from slipsurface.ui import worker as w

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("SLIPSURFACE_COMPUTE", "process")
    assert w.use_process()
    p = embankment()
    p.surfaces.effort = "fast"
    p.methods.methods = ["bishop"]
    job = w.AnalysisWorker(p)
    seen = {"progress": 0, "finished": None, "failed": None}
    job.progress.connect(lambda *a: seen.__setitem__("progress", seen["progress"] + 1))
    job.finished.connect(lambda r: seen.__setitem__("finished", r))
    job.failed.connect(lambda m: seen.__setitem__("failed", m))
    job.run()  # direct call: signals are delivered synchronously
    assert seen["failed"] is None and seen["progress"] > 0
    assert seen["finished"].results["bishop"].fos == run_analysis(p).results["bishop"].fos
    monkeypatch.setenv("SLIPSURFACE_COMPUTE", "thread")
    assert not w.use_process()
