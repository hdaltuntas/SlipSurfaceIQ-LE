import numpy as np
import pytest

from slipsurface.geometry import simple_slope


def test_simple_slope_shape():
    g = simple_slope(
        height=10, ratio_h_to_v=2, toe_x=15, left_bench=15, right_bench=20, depth_below_toe=10
    )
    assert g.meta["toe"] == (15.0, 0.0)
    assert g.meta["crest"] == (35.0, 10.0)
    assert g.bounds == (0.0, -10.0, 55.0, 10.0)
    assert g.meta["angle_deg"] == pytest.approx(26.565, abs=1e-3)
    # area = rectangle 55x20 minus triangle below crest-face (20*10/2) minus left strip 15x10
    assert g.domain.area == pytest.approx(55 * 20 - 0.5 * 20 * 10 - 15 * 10)


def test_ground_y_interpolation():
    g = simple_slope()
    toe_x, _ = g.meta["toe"]
    crest_x, h = g.meta["crest"]
    assert g.ground_y(toe_x - 5) == 0.0
    assert g.ground_y((toe_x + crest_x) / 2) == pytest.approx(h / 2)
    assert g.ground_y(crest_x + 5) == h
    np.testing.assert_allclose(g.ground_y(np.array([toe_x, crest_x])), [0.0, h])


def test_invalid_inputs():
    with pytest.raises(ValueError):
        simple_slope(height=-1)


@pytest.mark.parametrize(
    "water_table",
    [
        [[10, 0]],
        [[0, 0, 1], [20, 1, 1]],
        [[0, 0], [20, float("nan")]],
        [[0, 0], [float("inf"), 1]],
        [[10, 0], [10, 1]],
    ],
)
def test_boundary_geometry_rejects_invalid_water_table(water_table):
    from slipsurface.geometry.builder import boundary_geometry

    external = [[0, -5], [20, -5], [20, 5], [0, 5]]
    with pytest.raises(ValueError, match="YASS"):
        boundary_geometry(external, water_table=water_table)


def test_boundary_geometry_extends_valid_water_table():
    from slipsurface.geometry.builder import boundary_geometry

    external = [[0, -5], [20, -5], [20, 5], [0, 5]]
    geom = boundary_geometry(external, water_table=[[5, 0], [15, 2]])
    np.testing.assert_allclose(geom.water_table, [[0, 0], [5, 0], [15, 2], [20, 2]])
    assert boundary_geometry(external, water_table=[]).water_table is None


def test_layer_starting_at_a_concave_toe_vertex_splits_the_domain():
    # ACADS EX1(b): layer 1 starts at the toe (30, 25), a concave corner of the
    # external boundary. Its end used to be pushed ~tol inside the domain, so
    # the top and bottom layers merged into one region (and one material).
    from slipsurface.geometry.builder import build_regions

    ext = [[20, 20], [70, 20], [70, 35], [50, 35], [30, 25], [20, 25]]
    lines = [[[30, 25], [40, 27], [50, 29], [54, 31], [70, 31]], [[40, 27], [52, 24], [70, 24]]]
    assigns = [(60, 33, "S1"), (60, 27, "S2"), (40, 22, "S3")]
    domain, regions, _ = build_regions(ext, lines, assigns, "S0")
    areas = {r.material: r.polygon.area for r in regions}
    assert areas == pytest.approx({"S1": 144.0, "S2": 158.0, "S3": 248.0})
    assert sum(areas.values()) == pytest.approx(domain.area)


def test_layer_end_near_a_concave_vertex_snaps_onto_it():
    from slipsurface.geometry.builder import build_regions

    ext = [[20, 20], [70, 20], [70, 35], [50, 35], [30, 25], [20, 25]]
    line = [[30.02, 24.99], [50, 29], [70, 31]]  # within the snap tolerance of (30, 25)
    _, regions, _ = build_regions(ext, [line], [], "S")
    assert len(regions) == 2


def test_acads_1b_matches_published_factors_of_safety():
    from slipsurface.analysis import run_analysis
    from slipsurface.project import acads_1b_project

    p = acads_1b_project()
    p.methods.methods = ["bishop", "spencer"]
    res = run_analysis(p)
    # Slide2 verification problem #2 (ACADS EX1(b)): Bishop 1.405, Spencer 1.375
    assert res.results["bishop"].fos == pytest.approx(1.405, abs=0.015)
    assert res.results["spencer"].fos == pytest.approx(1.375, abs=0.015)
