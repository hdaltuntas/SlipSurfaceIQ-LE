"""Open in Tools > Python scripting, then Run / Apply. Units: m, kN, kPa."""
from slipsurface.project import empty_project, MaterialSpec
from slipsurface.loads import SupportType, FacingType

project = empty_project()
project.summary.title = "Scripted layered cut"
project.external = [[0, -8], [48, -8], [48, 12], [26, 12], [20, 0], [0, 0]]
project.materials = [
    MaterialSpec(name="Soil", model="MC", gamma=19, c=8, phi=30),
    MaterialSpec(name="Rock", model="HB", gamma=23, sigma_ci=8000, gsi=40, mi=8),
]
project.material_boundaries = [[[0, -3], [48, -3]]]
project.assignments = [
    {"point": [24, 5], "material": "Soil"},
    {"point": [24, -6], "material": "Rock"},
]
project.water_table = [[0, -2], [20, -2], [40, 4], [48, 4]]
project.tension_crack = [[30, 10], [48, 10]]
project.groundwater.crack_water = 0.5
project.support_types = [
    SupportType(name="Nail", kind="soil_nail", spacing=1.5, tensile=240,
                plate=80, bond_strength=40, application="passive", length=9),
]
project.supports = [{"a": [23, 6], "b": [32, 3.5], "type": "Nail"}]
project.support_patterns = [
    {"p1": [20, 0], "p2": [26, 12], "spacing": 2, "offset": 1,
     "angle": 15, "length": 9, "type": "Nail"},
]
project.facing_types = [FacingType(name="Shotcrete")]
project.facings = [
    {"x1": 20, "x2": 26, "type": "Shotcrete", "points": [[20, 0], [26, 12]]},
]
project.loads = [
    {"kind": "distributed", "points": [[29, 12], [40, 12]],
     "q": [15, 15], "orientation": "vertical"},
    {"kind": "line", "point": [42, 12], "magnitude": 20, "angle": 270},
]
project.seismic.kh = 0.1
project.methods.methods = ["bishop", "spencer"]
project.methods.n_slices = 40
project.surfaces.effort = "fast"
print("Ready:", project.summary.title)
