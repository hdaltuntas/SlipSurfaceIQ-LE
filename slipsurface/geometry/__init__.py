"""GeometryModule — soil profiles, region polygons, slip surfaces, water table.

Available:
    SlopeGeometry, Region, simple_slope, layered_geometry, CircularSurface, slip_extent

Planned:
    SplineSurface   : non-circular, scipy BSpline       — later
"""

from slipsurface.geometry.slope import Region, SlopeGeometry, layered_geometry, simple_slope
from slipsurface.geometry.surfaces import (
    CircularSurface,
    PolylineSurface,
    SlipSurface,
    SplineSurface,
    slip_extent,
)

__all__ = ["CircularSurface", "PolylineSurface", "Region", "SlipSurface", "SplineSurface",
           "SlopeGeometry", "layered_geometry", "simple_slope", "slip_extent"]
