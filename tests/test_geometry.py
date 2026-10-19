import numpy as np
import pytest

from slipsurface.geometry import simple_slope


def test_simple_slope_shape():
    g = simple_slope(height=10, ratio_h_to_v=2, toe_x=15, left_bench=15, right_bench=20,
                     depth_below_toe=10)
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
