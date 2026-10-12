"""
Pure metrics over recorded mission runs (VICON arena metres).

Shared by run_recorder (per-step results / CSV export) and the
tools/results analysis scripts, so both report identical numbers.

Track = list of (time_s, x_m, y_m) VICON samples for one robot.
VICON-mode zones and markers store lon = x_m, lat = y_m.
"""

import math

GRID_M = 0.05                    # coverage grid cell size
CIRCLE_APPROXIMATION_SIDES = 32  # same as area-navigate

Track = list[tuple[float, float, float]]


def zone_polygon_xy(zone: dict) -> list[tuple[float, float]]:
    """Polygon (x_m, y_m) for a VICON-mode zone dict (polygon or circle)."""
    center, radius = zone.get("center"), zone.get("radius_m")
    if center and radius:
        cx, cy = center["lon"], center["lat"]
        return [
            (
                cx + radius * math.cos(2 * math.pi * i / CIRCLE_APPROXIMATION_SIDES),
                cy + radius * math.sin(2 * math.pi * i / CIRCLE_APPROXIMATION_SIDES),
            )
            for i in range(CIRCLE_APPROXIMATION_SIDES)
        ]
    points = zone.get("points") or []
    if len(points) < 3:
        raise ValueError(f"Zone {zone.get('name')!r} has no usable geometry")
    return [(p["lon"], p["lat"]) for p in points]


def point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def grid_origin(polygon: list[tuple[float, float]]) -> tuple[float, float]:
    return min(p[0] for p in polygon), min(p[1] for p in polygon)


def zone_cells(polygon: list[tuple[float, float]]) -> set[tuple[int, int]]:
    """Grid cells whose centre lies inside the zone."""
    x0, y0 = grid_origin(polygon)
    x1 = max(p[0] for p in polygon)
    y1 = max(p[1] for p in polygon)
    return {
        (i, j)
        for i in range(int((x1 - x0) / GRID_M) + 1)
        for j in range(int((y1 - y0) / GRID_M) + 1)
        if point_in_polygon(x0 + (i + 0.5) * GRID_M, y0 + (j + 0.5) * GRID_M, polygon)
    }


def covered_cells(
    track: Track, radius_m: float, origin: tuple[float, float]
) -> set[tuple[int, int]]:
    """Grid cells within radius_m of the trail (long segments are densified)."""
    x0, y0 = origin
    points: list[tuple[float, float]] = []
    for (_, ax, ay), (_, bx, by) in zip(track, track[1:]):
        steps = max(1, int(math.hypot(bx - ax, by - ay) / (GRID_M / 2)))
        points.extend(
            (ax + (bx - ax) * k / steps, ay + (by - ay) * k / steps) for k in range(steps)
        )
    if track:
        points.append((track[-1][1], track[-1][2]))

    r_cells = int(math.ceil(radius_m / GRID_M))
    cells: set[tuple[int, int]] = set()
    for px, py in points:
        ci, cj = int((px - x0) / GRID_M), int((py - y0) / GRID_M)
        for i in range(ci - r_cells, ci + r_cells + 1):
            for j in range(cj - r_cells, cj + r_cells + 1):
                cx, cy = x0 + (i + 0.5) * GRID_M, y0 + (j + 0.5) * GRID_M
                if math.hypot(cx - px, cy - py) <= radius_m:
                    cells.add((i, j))
    return cells


def coverage_percent(
    polygon: list[tuple[float, float]], tracks: list[Track], swath_m: float
) -> float:
    """Share of the zone within swath_m / 2 of any of the tracks, in percent."""
    inside = zone_cells(polygon)
    if not inside:
        return float("nan")
    origin = grid_origin(polygon)
    covered: set[tuple[int, int]] = set()
    for track in tracks:
        covered |= covered_cells(track, swath_m / 2, origin)
    return 100.0 * len(covered & inside) / len(inside)


def final_error_m(track: Track, target_x: float, target_y: float) -> float:
    """Distance from the last sample of the track to the target."""
    _, x, y = track[-1]
    return math.hypot(x - target_x, y - target_y)
