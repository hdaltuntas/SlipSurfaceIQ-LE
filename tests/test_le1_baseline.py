"""LE-1 regression tests: reliability baseline, GUI close-hang fix, and input/schema guards."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from slipsurface.geometry import CircularSurface, Region, SlopeGeometry  # noqa: E402
from slipsurface.loads import FacingType, SupportType  # noqa: E402
from slipsurface.materials import (  # noqa: E402
    BartonBandis,
    CNIRockMass,
    HardeningSoil,
    HoekBrown,
    HoekBrownDirect,
    MohrCoulomb,
    PowerCurve,
    Sanisand,
)
from slipsurface.project import FORMAT, Project, acads_1a_project  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_interpret_undo_resets_result_notes_dirty_and_closes_without_prompt(app, monkeypatch):
    """Regression for 2026.7.1 CI hang: undoing an Interpret note back to the
    saved state must clear _result_notes_dirty so closeEvent never blocks on a
    modal 'Unsaved Changes' prompt."""
    from slipsurface.ui.modeler import ModelerWindow

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: pytest.fail("Unexpected Unsaved Changes modal dialog on clean project"),
    )
    p = acads_1a_project()
    p.result_annotations = [{"kind": "text", "pts": [[5.0, 5.0]], "text": "Saved"}]
    win = ModelerWindow(p)
    try:
        assert not win._result_notes_dirty
        assert " *" not in win.windowTitle()

        # Simulate Interpret adding a second note -> project becomes dirty
        win._result_annotations_changed(
            [
                {"kind": "text", "pts": [[5.0, 5.0]], "text": "Saved"},
                {"kind": "text", "pts": [[15.0, 10.0]], "text": "Temp"},
            ]
        )
        assert win._result_notes_dirty
        assert " *" in win.windowTitle()

        # Simulate Interpret pressing Ctrl+Z back to the saved state -> clean again
        win._result_annotations_changed([{"kind": "text", "pts": [[5.0, 5.0]], "text": "Saved"}])
        assert not win._result_notes_dirty
        assert " *" not in win.windowTitle()
        assert win._confirm_discard() is True
    finally:
        win.doc.mark_clean()
        win.close()
        app.processEvents()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        42,
        "slipsurface-le",
        {"format": FORMAT, "version": None},
        {"format": FORMAT, "version": "abc"},
        {"format": FORMAT, "version": True},
        {"format": FORMAT, "version": 0},
        {"format": FORMAT, "version": -1},
        {"format": FORMAT, "version": 3.5},
        {"format": FORMAT, "version": 99},
    ],
)
def test_from_dict_rejects_malformed_root_and_version_values(payload):
    with pytest.raises(ValueError):
        Project.from_dict(payload)  # type: ignore[arg-type]


def test_from_dict_handles_null_top_level_sections_cleanly():
    base = acads_1a_project().to_dict()
    base["display"] = None
    base["surfaces"] = None
    base["loads"] = None
    loaded = Project.from_dict(base)
    assert loaded.has_geometry
    assert loaded.loads == []
    assert loaded.display["show_grid"] in (True, False)


def test_validate_catches_invalid_geometry_points_and_user_surface():
    p = acads_1a_project()
    p.external = [[0.0]]  # malformed 1D vertex
    with pytest.raises(ValueError, match="External boundary"):
        p.validate()

    p = acads_1a_project()
    p.surfaces.surface_type = "user"
    p.surfaces.user_circle = None
    p.surfaces.user_surface = [[10.0, 5.0]]  # fewer than 2 points
    with pytest.raises(ValueError, match="User surface"):
        p.validate()

    p.surfaces.user_surface = [[10.0, 5.0], [10.0, 8.0]]  # duplicate x
    with pytest.raises(ValueError, match="increasing x"):
        p.validate()


def test_validate_catches_invalid_support_facing_and_pattern_parameters():
    # Negative mesh yield strength on facing
    p = acads_1a_project()
    p.facing_types = [FacingType("BadFacing", mesh_fy=-100.0)]
    with pytest.raises(ValueError, match="BadFacing"):
        p.validate()

    # Zero-width facing
    p = acads_1a_project()
    p.facing_types = [FacingType("Shotcrete")]
    p.facings = [{"x1": 25.0, "x2": 25.0, "type": "Shotcrete"}]
    with pytest.raises(ValueError, match="Facing"):
        p.validate()

    # Invalid geosynthetic friction angle >= 90 deg
    p = acads_1a_project()
    p.support_types = [SupportType("Geo", kind="geosynthetic", interface_friction=95.0)]
    with pytest.raises(ValueError, match="Geo"):
        p.validate()

    # Zero-length support
    p = acads_1a_project()
    p.support_types = [SupportType("Anchor 1")]
    p.supports = [{"a": [25.0, 5.0], "b": [25.0, 5.0], "type": "Anchor 1"}]
    with pytest.raises(ValueError, match="Support 1"):
        p.validate()

    # Negative bolt-pattern offset
    p = acads_1a_project()
    p.support_types = [SupportType("Anchor 1")]
    p.support_patterns = [
        {
            "p1": [20.0, 0.0],
            "p2": [40.0, 10.0],
            "type": "Anchor 1",
            "spacing": 2.0,
            "length": 8.0,
            "offset": -1.0,
        }
    ]
    with pytest.raises(ValueError, match="Bolt pattern 1"):
        p.validate()


def test_direct_api_constructors_validate_bounds_and_finiteness():
    with pytest.raises(ValueError):
        CircularSurface(10.0, 20.0, 0.0)
    with pytest.raises(ValueError):
        CircularSurface(10.0, 20.0, -5.0)
    with pytest.raises(ValueError):
        CircularSurface(float("nan"), 20.0, 10.0)

    with pytest.raises(ValueError):
        MohrCoulomb("bad_sat", 20.0, gamma_sat=-5.0)
    with pytest.raises(ValueError):
        MohrCoulomb("bad_hu", 20.0, hu=-0.5)
    with pytest.raises(ValueError):
        MohrCoulomb("nan_c", 20.0, c=float("nan"), phi=30.0)

    # d=2.0 previously divided by zero in 28 - 14*d without raising ValueError
    with pytest.raises(ValueError):
        HoekBrown("hb_div0", 25.0, sigma_ci=20_000.0, gsi=50.0, mi=10.0, d=2.0)
    with pytest.raises(ValueError):
        HoekBrown("hb_neg", 25.0, sigma_ci=-100.0, gsi=50.0, mi=10.0, d=0.0)
    with pytest.raises(ValueError):
        HoekBrownDirect("hbd_nan", 25.0, sigma_ci=float("nan"))
    with pytest.raises(ValueError):
        HardeningSoil("hs_nan", 20.0, e50_ref=float("inf"))
    with pytest.raises(ValueError):
        Sanisand("ss_nan", 20.0, m_c=float("nan"))
    with pytest.raises(ValueError):
        PowerCurve("pc_nan", 20.0, pc_a=float("nan"))
    with pytest.raises(ValueError):
        BartonBandis("bb_nan", 24.0, jcs=float("nan"))
    with pytest.raises(ValueError):
        CNIRockMass("cni_nan", 24.0, sigma_cm=float("nan"))

    geom = acads_1a_project().build_geometry()
    with pytest.raises(ValueError, match="water_table"):
        SlopeGeometry(
            geom.surface,
            [Region(r.polygon, r.material) for r in geom.regions],
            water_table=[[20.0, 5.0], [10.0, 5.0]],  # decreasing x
        )
