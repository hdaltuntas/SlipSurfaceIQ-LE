"""Test-only model builders: the reference slopes that are not bundled examples.

The application ships only the ACADS examples; these models back the
regression and published-benchmark tests (Arai & Tagyo, Borges & Cardoso).
"""

from __future__ import annotations

from slipsurface.loads import FacingType, SupportType
from slipsurface.project import PALETTE, MaterialSpec, Project, _mk


def default_project() -> Project:
    """10 m high 2H:1V homogeneous slope."""
    return _mk(
        "Simple slope H=10 m, 2H:1V",
        [MaterialSpec("Soil 1", "MC", 18, 20, False, 10, 30, color=PALETTE[0])],
        [[0, -10], [55, -10], [55, 10], [35, 10], [15, 0], [0, 0]],
    )


def arai_tagyo_layered_project(noncircular: bool = False) -> Project:
    """Arai & Tagyo (1985) example 2 / Slide2 VP15: dry three-layer slope.

    A weak middle layer lies between stronger upper and lower layers.
    The same exact geometry is used for circular and non-circular searches.
    """
    shape = "noncircular" if noncircular else "circular"
    p = _mk(
        f"Arai & Tagyo (1985) — layered slope, {shape}",
        [
            MaterialSpec("Upper Layer", "MC", 18.82, 18.82, False, 29.4, 12.0, color=PALETTE[3]),
            MaterialSpec("Middle Layer", "MC", 18.82, 18.82, False, 9.8, 5.0, color=PALETTE[0]),
            MaterialSpec("Lower Layer", "MC", 18.82, 18.82, False, 294.0, 40.0, color=PALETTE[2]),
        ],
        [[0, 3], [96, 3], [96, 35], [72, 35], [48, 35], [24, 19], [18, 15], [0, 15]],
        bounds=[
            [[24, 19], [72, 35]],
            [[0, 3], [96, 35]],
        ],
        assigns=[
            ((48, 31), "Upper Layer"),
            ((48, 24), "Middle Layer"),
            ((48, 12), "Lower Layer"),
        ],
        methods=["janbu_simplified", "spencer"]
        if noncircular
        else ["bishop", "janbu_simplified", "spencer"],
        n_slices=50,
    )
    p.groundwater.method = "none"
    p.surfaces.surface_type = "noncircular" if noncircular else "circular"
    p.surfaces.noncircular_shape = "polyline"
    p.surfaces.effort = "fine" if noncircular else "normal"
    p.surfaces.n_ctrl = 4
    return p


def arai_tagyo_layered_circular_project() -> Project:
    """VP15 circular search."""
    return arai_tagyo_layered_project(noncircular=False)


def arai_tagyo_layered_noncircular_project() -> Project:
    """VP15 non-circular polyline search."""
    return arai_tagyo_layered_project(noncircular=True)


def borges_cardoso_case2_project() -> Project:
    """Borges & Cardoso (2002) Case 2 / SLOPE/W §2.18.

    Dry 5 m embankment on four total-stress soft-clay layers, including
    depth-varying undrained shear strength and an unanchored geosynthetic.
    Published FoS are reference values, not imposed search results.
    """
    name = "Case 2 geosynthetic – 200 kN/m"
    p = _mk(
        "Borges & Cardoso (2002) — geosynthetic embankment #2",
        [
            MaterialSpec("Embankment", "MC", 20, 20, False, 0, 35, color=PALETTE[0]),
            MaterialSpec("Clay 1", "UD", 17, 17, False, su=33, color=PALETTE[2]),
            MaterialSpec("Clay 2", "UD", 17, 17, False, su=16, color=PALETTE[3]),
            MaterialSpec(
                "Clay 3",
                "UDG",
                17,
                17,
                False,
                su_top=16.0,
                su_bottom=18.4,
                su_y_top=-4.5,
                su_y_bottom=-7.0,
                color=PALETTE[4],
            ),
            MaterialSpec(
                "Clay 4",
                "UDG",
                17,
                17,
                False,
                su_top=18.4,
                su_bottom=55.1,
                su_y_top=-7.0,
                su_y_bottom=-27.0,
                color=PALETTE[5],
            ),
        ],
        [
            [-30, -27],
            [45, -27],
            [45, 0],
            [42.5, 0],
            [36.41, 5],
            [6.15, 5],
            [0, 0],
            [-30, 0],
        ],
        bounds=[
            [[0, 0], [42.5, 0]],
            [[-30, -1], [45, -1]],
            [[-30, -4.5], [45, -4.5]],
            [[-30, -7], [45, -7]],
        ],
        assigns=[
            ((20, 2), "Embankment"),
            ((20, -0.5), "Clay 1"),
            ((20, -2), "Clay 2"),
            ((20, -5.5), "Clay 3"),
            ((20, -12), "Clay 4"),
        ],
        methods=["bishop", "janbu_simplified", "gle"],
        n_slices=50,
    )
    p.groundwater.method = "none"
    p.support_types = [
        SupportType(
            name=name,
            kind="geosynthetic",
            tensile=200,
            coverage=100,
            anchorage="none",
            adhesion=0,
            interface_friction=33.7,
            overburden_gamma=20,
            application="passive",
            orientation="parallel",
        )
    ]
    p.supports = [{"a": [0.0, 0.0], "b": [42.5, 0.0], "type": name}]
    p.surfaces.surface_type = "circular"
    p.surfaces.effort = "normal"
    # Reject degenerate tangent circles whose sliding mass is numerically thin
    # (a circle tangent to the base can carry a near-zero mass and dodge the
    # geosynthetic, producing a spurious low minimum). Slide2-style models use
    # a minimum sliding depth for the same reason.
    p.advanced.min_depth = 1.0
    return p


def layered_example_project() -> Project:
    """Three materials, a weak clay band outcropping on the face, water table."""
    return _mk(
        "Layered slope with water table",
        [
            MaterialSpec("Fill", "MC", 19, 20, True, 8, 32, color=PALETTE[0]),
            MaterialSpec("Soft clay", "MC", 17, 18, True, 15, 18, color=PALETTE[3]),
            MaterialSpec(
                "Weathered rock",
                "HB",
                23,
                24,
                True,
                sigma_ci=8_000,
                gsi=35,
                mi=8,
                d=0.3,
                color=PALETTE[2],
            ),
        ],
        [[0, -12], [70, -12], [70, 14], [50, 12], [40, 12], [20, 0], [0, 0]],
        bounds=[[[0, -1], [70, 5]], [[0, -5], [70, -2]]],
        wt=[[0, -0.5], [20, -0.5], [45, 6], [70, 8]],
        assigns=[((60, 10), "Fill"), ((60, 2), "Soft clay"), ((60, -6), "Weathered rock")],
        n_slices=30,
    )


def anchored_example_project() -> Project:
    """Steep cut with a crest surcharge, stabilised by two rows of grouted tiebacks."""
    p = _mk(
        "Anchored cut with surcharge",
        [MaterialSpec("Sandy clay", "MC", 19, 20, True, 12, 26, color=PALETTE[0])],
        [[0, -8], [50, -8], [50, 12], [26, 12], [18, 0], [0, 0]],
        n_slices=40,
        methods=["bishop", "spencer", "janbu_corrected"],
    )
    p.support_types = [
        SupportType(
            "Tieback 1",
            "grouted_tieback",
            spacing=2.0,
            tensile=400,
            bond_strength=60,
            bond_length=6,
            application="active",
        )
    ]
    p.supports = [
        {"a": [21.33, 5.0], "b": [37.0, -0.5], "type": "Tieback 1"},
        {"a": [24.0, 9.0], "b": [40.0, 3.5], "type": "Tieback 1"},
    ]
    p.loads = [
        {
            "kind": "distributed",
            "points": [[29, 12], [37, 12]],
            "q": [20, 20],
            "orientation": "vertical",
        },
        {"kind": "line", "point": [42, 12], "magnitude": 60, "angle": 270.0},
    ]
    return p


def cracked_example_project() -> Project:
    """Cohesive slope with a water-filled tension crack in the crest zone."""
    p = _mk(
        "Slope with water-filled tension crack",
        [MaterialSpec("Stiff clay", "MC", 19, 20, False, 18, 20, color=PALETTE[1])],
        [[0, -10], [60, -10], [60, 12], [32, 12], [14, 0], [0, 0]],
        n_slices=40,
        methods=["bishop", "spencer", "gle"],
    )
    p.tension_crack = [[32.0, 9.0], [60.0, 9.0]]
    p.groundwater.crack_water = 1.0
    return p


def nailed_shotcrete_project() -> Project:
    """Steep cut stabilised with a soil-nail pattern (15°) and a shotcrete +
    wire mesh facing on the slope face."""
    p = _mk(
        "Soil-nailed cut with shotcrete facing",
        [
            MaterialSpec("Silty sand", "MC", 19, 20, False, 8, 30, color=PALETTE[0]),
            MaterialSpec("Weathered rock", "MC", 22, 23, False, 40, 36, color=PALETTE[2]),
        ],
        [[0, -8], [48, -8], [48, 12], [26, 12], [20, 0], [0, 0]],
        n_slices=40,
        methods=["bishop", "spencer", "janbu_corrected"],
    )
    p.material_boundaries = [[[0, -3], [48, -3]]]
    p.assignments = [
        {"point": [24, 5], "material": "Silty sand"},
        {"point": [24, -6], "material": "Weathered rock"},
    ]
    p.support_types = [
        SupportType(
            "Nail Ø28",
            "soil_nail",
            spacing=1.5,
            tensile=240,
            plate=80,
            bond_strength=40,
            application="passive",
            color="#1f3d7a",
            length=9.0,
        )
    ]
    p.support_patterns = [
        {
            "p1": [20.0, 0.0],
            "p2": [26.0, 12.0],
            "spacing": 1.5,
            "offset": 0.75,
            "angle": 15.0,
            "length": 9.0,
            "type": "Nail Ø28",
        }
    ]
    p.facing_types = [FacingType("Shotcrete 10 cm + Q188")]
    p.facings = [
        {
            "x1": 20.0,
            "x2": 26.0,
            "type": "Shotcrete 10 cm + Q188",
            "points": [[20.0, 0.0], [26.0, 12.0]],
        }
    ]
    p.loads = [
        {
            "kind": "distributed",
            "points": [[29, 12], [40, 12]],
            "q": [15, 15],
            "orientation": "vertical",
        }
    ]
    p.annotations = [
        {
            "kind": "text",
            "pts": [[30.0, 17.0]],
            "text": "Soil-nail pattern: 1.5 m spacing, 15°, L = 9 m\n"
            "Facing: 10 cm shotcrete + Q188",
            "color": "#1b2a3a",
            "size": 9,
            "bold": False,
            "box": True,
        },
        {"kind": "arrow", "pts": [[29.5, 16.0], [24.5, 9.5]], "color": "#c0392b", "width": 1.5},
    ]
    p.display["material_labels"] = "full"
    return p
