"""Published ACADS EX1(b), EX1(d), EX4 and EX5 input-fidelity tests.

These models complete the ACADS (Giam & Donald, 1989) benchmark set as
reproduced in the Rocscience verification manuals (RS2/Slide2 VP #2, #4,
#9, #10). Published FoS values are reference-only and NOT hard-coded as
solver outputs; the tests verify faithful *inputs* and a real, finite,
admissible solution for every method.
"""

import pytest

from slipsurface.analysis import run_analysis
from slipsurface.project import (
    Project,
    acads_1c_project,
    acads_1d_project,
    acads_4_project,
    acads_5_project,
    example_project,
)

NAMES = {
    "1c": "ACADS EX1(b) — slope with tension crack",
    "1d": "ACADS EX1(d) — seismic kh = 0.15",
    "4": "ACADS EX4 — weak seam, water table, surcharge",
    "5": "ACADS EX5 — excavated slope with groundwater",
}
FILES = {
    "1c": "examples/acads_1c.slp.json",
    "1d": "examples/acads_1d.slp.json",
    "4": "examples/acads_4.slp.json",
    "5": "examples/acads_5.slp.json",
}


@pytest.mark.parametrize("key", ["1c", "1d", "4", "5"])
def test_preset_saved_file_and_menu_entry_agree(key, tmp_path):
    p = acads_project(key)
    p.validate()
    saved = Project.load(FILES[key])
    saved.validate()
    menu = example_project(NAMES[key])
    menu.validate()
    for a in (p, saved, menu):
        assert a.summary.title == NAMES[key]
    assert saved.analysis_inputs() == p.analysis_inputs()


def acads_project(key):
    return {
        "1c": acads_1c_project,
        "1d": acads_1d_project,
        "4": acads_4_project,
        "5": acads_5_project,
    }[key]()


def test_1c_tension_crack_inputs():
    p = acads_1c_project()
    assert p.tension_crack is not None
    x1, y1 = p.tension_crack[0]
    x2, y2 = p.tension_crack[1]
    assert x2 > x1 and y1 == pytest.approx(y2)
    # Craig (1997) depth: z0 = 2c/gamma / sqrt(Ka) = 3.814 m for c=32, phi=10
    assert y1 == pytest.approx(10 - 3.814, abs=1e-2)
    assert p.groundwater.crack_water == 1.0  # water-filled crack
    m = p.materials[0]
    assert m.c == 32.0 and m.phi == 10.0 and m.gamma == 20


def test_1d_is_1b_geometry_plus_seismic():
    from slipsurface.project import acads_1b_project

    b, d = acads_1b_project(), acads_1d_project()
    assert d.seismic.kh == 0.15
    assert d.external == b.external
    assert [m.name for m in d.materials] == [m.name for m in b.materials]
    assert d.material_boundaries == b.material_boundaries


def test_4_has_inclined_water_table_and_two_loads():
    p = acads_4_project()
    assert len(p.water_table) == 8
    assert p.water_table[0][0] == 20 and p.water_table[0][1] == 27.75
    assert len(p.loads) == 2
    q1, q2 = p.loads
    assert q1["q"] == [20, 20]
    assert q2["q"] == [20, 40]


def test_4_inclined_seam_matches_published_geometry_and_assignments():
    """RS2 Part 1 section 6 Figure 1: EX4 must not inherit EX3(a)'s seam."""
    from shapely.geometry import Point

    for p in (acads_4_project(), Project.load(FILES["4"])):
        assert p.external[:2] == [[20, 15], [84, 15]]
        assert p.material_boundaries == [
            [[20, 18.88], [84, 36.8]],
            [[20, 18.28], [84, 36.2]],
        ]
        geometry = p.build_geometry()
        assert len(geometry.regions) == 3
        for x in (25.0, 60.0, 80.0):
            middle = 18.58 + 0.28 * (x - 20)
            for y, material in ((middle, "Soil 2"), (middle - 1, "Soil 1"), (middle + 1, "Soil 1")):
                regions = [r for r in geometry.regions if r.polygon.contains(Point(x, y))]
                assert len(regions) == 1 and regions[0].material == material


def test_published_names_and_legacy_identifiers_preserve_geometry():
    from slipsurface.project import EXAMPLES, acads_1b_project

    assert "ACADS EX1(c) — non-homogeneous slope" in EXAMPLES
    assert "ACADS EX1(b) — slope with tension crack" in EXAMPLES
    layered = acads_1b_project()
    crack = acads_1c_project()
    assert "EX1(c)" in layered.summary.title
    assert "EX1(b)" in crack.summary.title
    assert Project.load("examples/acads_1b.slp.json").analysis_inputs() == layered.analysis_inputs()
    for name in ("ACADS EX1(b)", "ACADS EX1(c) — non-homogeneous slope"):
        assert example_project(name).analysis_inputs() == layered.analysis_inputs()
    for name in (
        "ACADS EX1(c) — slope with tension crack",
        "ACADS EX1(b) — slope with tension crack",
    ):
        assert example_project(name).analysis_inputs() == crack.analysis_inputs()


def test_5_direction_and_water_table():
    p = acads_5_project()
    assert p.general.failure_direction == "left_to_right"
    assert p.water_table[0] == [0, 6]
    m = p.materials[0]
    assert m.c == 11.0 and m.phi == 28.0


@pytest.mark.parametrize("key", ["1c", "1d", "4", "5"])
def test_saved_file_roundtrip_preserves_inputs(key):
    from slipsurface.project import acads_1c_project as f1
    from slipsurface.project import acads_1d_project as f2
    from slipsurface.project import acads_4_project as f3
    from slipsurface.project import acads_5_project as f4

    factory = {"1c": f1, "1d": f2, "4": f3, "5": f4}[key]
    fresh, saved = factory(), Project.load(FILES[key])
    assert saved.external == fresh.external
    assert saved.methods.methods == fresh.methods.methods
    assert saved.water_table == fresh.water_table


@pytest.mark.slow
@pytest.mark.parametrize("key", ["1c", "1d", "4", "5"])
def test_real_analysis_finite_and_admissible(key):
    p = acads_project(key)
    r = run_analysis(p)
    assert not r.errors, r.errors
    assert r.results
    for m, res in r.results.items():
        assert res.fos > 0 and res.fos == res.fos, (m, res.fos)
