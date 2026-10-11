"""
Verification of area-navigate's lawnmower (boustrophedon) path generation —
the pure geometry behind AREA_COVERAGE, tested without any robot.
"""

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

_PLUGIN = (
    Path(__file__).resolve().parents[3] / "plugins" / "control" / "area-navigate" / "plugin.py"
)
_spec = importlib.util.spec_from_file_location("area_navigate_plugin", _PLUGIN)
area_nav = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(area_nav)


def _vicon_zone(xy: list[tuple[float, float]]):
    """VICON-mode polygon zone (convention: lon = x_m, lat = y_m)."""
    return SimpleNamespace(
        name="test-zone",
        map_mode="vicon",
        center=None,
        radius_m=None,
        points=[SimpleNamespace(lat=y, lon=x) for x, y in xy],
    )


RECT = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
L_SHAPE = [(0.0, 0.0), (4.0, 0.0), (4.0, 1.5), (1.5, 1.5), (1.5, 4.0), (0.0, 4.0)]


def _lanes(path: list[tuple[float, float]], angle_deg: float) -> list[tuple[float, float, float]]:
    """(y, x_start, x_end) per lane, in the sweep's rotated frame."""
    rotated = [area_nav._rotate(x, y, angle_deg) for x, y in path]
    return [
        (rotated[i][1], rotated[i][0], rotated[i + 1][0])
        for i in range(0, len(rotated), 2)
    ]


@pytest.mark.parametrize("polygon", [RECT, L_SHAPE], ids=["rectangle", "l-shape"])
@pytest.mark.parametrize("robots", [1, 2, 3])
@pytest.mark.parametrize("angle", [0.0, 30.0, 90.0])
def test_every_waypoint_is_inside_the_zone(polygon, robots, angle):
    kind, paths = area_nav._generate_coverage_paths(_vicon_zone(polygon), robots, 0.5, angle)

    assert kind == "local"
    assert len(paths) == robots
    for path in paths:
        for x, y in path:
            assert area_nav._point_in_polygon_xy(x, y, polygon), (x, y)


def test_lanes_alternate_direction():
    _, (path,) = area_nav._generate_coverage_paths(_vicon_zone(RECT), 1, 0.5, 0.0)
    directions = [math.copysign(1, x_end - x_start) for _, x_start, x_end in _lanes(path, 0.0)]

    assert len(directions) >= 2
    assert all(a == -b for a, b in zip(directions, directions[1:]))


@pytest.mark.parametrize("spacing", [0.3, 0.5, 1.0])
def test_lane_spacing_matches_request_when_zone_height_is_a_multiple(spacing):
    # 3.0 m tall zone: exact multiple of every spacing above.
    _, (path,) = area_nav._generate_coverage_paths(_vicon_zone(RECT), 1, spacing, 0.0)
    ys = [y for y, _, _ in _lanes(path, 0.0)]
    gaps = [b - a for a, b in zip(ys, ys[1:])]

    assert gaps
    assert all(g == pytest.approx(spacing, rel=1e-6) for g in gaps)


@pytest.mark.parametrize("height", [2.2, 3.4, 3.9])
def test_lane_spacing_is_never_below_request_and_under_double(height):
    """
    Documents current behaviour: lane count is floor(height / spacing), so the
    actual lane gap is >= the requested spacing and < 2x it. Coverage results
    should report the actual lane gap, not just the requested spacing.
    """
    spacing = 1.0
    zone = _vicon_zone([(0.0, 0.0), (4.0, 0.0), (4.0, height), (0.0, height)])
    _, (path,) = area_nav._generate_coverage_paths(zone, 1, spacing, 0.0)
    ys = [y for y, _, _ in _lanes(path, 0.0)]
    gaps = [b - a for a, b in zip(ys, ys[1:])]

    assert all(spacing - 1e-9 <= g < 2 * spacing for g in gaps)


def _band_areas(polygon, robots, angle):
    """Zone area (m²) inside each robot's strip, by fine grid sampling."""
    rotated = [area_nav._rotate(x, y, angle) for x, y in polygon]
    xs, ys = [p[0] for p in rotated], [p[1] for p in rotated]
    bands = area_nav._equal_area_band_bounds(
        rotated, robots, min(xs), max(xs), min(ys), max(ys)
    )
    cell = 0.02
    areas = [0.0] * robots
    y = min(ys) + cell / 2
    while y < max(ys):
        x = min(xs) + cell / 2
        while x < max(xs):
            if area_nav._point_in_polygon_xy(x, y, rotated):
                for i, (lo, hi) in enumerate(bands):
                    if lo <= y < hi:
                        areas[i] += cell * cell
                        break
            x += cell
        y += cell
    return areas


@pytest.mark.parametrize("polygon", [RECT, L_SHAPE], ids=["rectangle", "l-shape"])
@pytest.mark.parametrize("robots", [2, 3])
def test_strips_split_the_zone_into_equal_areas(polygon, robots):
    areas = _band_areas(polygon, robots, 0.0)
    mean = sum(areas) / len(areas)

    assert all(abs(a - mean) / mean < 0.05 for a in areas), areas


def test_circle_zone_is_supported():
    zone = SimpleNamespace(
        name="circle",
        map_mode="vicon",
        center=SimpleNamespace(lat=1.0, lon=2.0),
        radius_m=1.5,
        points=[],
    )
    _, (path,) = area_nav._generate_coverage_paths(zone, 1, 0.5, 0.0)

    assert path
    for x, y in path:
        assert math.hypot(x - 2.0, y - 1.0) <= 1.5 + 1e-6


def test_perimeter_patrol_follows_drawn_vertices():
    kind, vertices = area_nav._perimeter_vertices(_vicon_zone(L_SHAPE))

    assert kind == "local"
    assert vertices == L_SHAPE
