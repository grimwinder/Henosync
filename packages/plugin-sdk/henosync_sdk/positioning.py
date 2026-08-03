"""
Henosync Plugin SDK — PositioningMixin
=======================================
Utility mixin for device plugins that need to convert local X/Y coordinates
(metres, East/North) to WGS84 GPS coordinates.

Intended for robots whose position comes from a motion capture system (VICON,
OptiTrack, etc.) rather than an onboard GPS receiver.

Usage
-----
Inherit alongside NodePlugin:

    class MyRobotPlugin(NodePlugin, PositioningMixin):
        ...
        def _on_vicon(self, node_id, msg, home_lat, home_lon):
            x = msg["transform"]["translation"]["x"]
            y = msg["transform"]["translation"]["y"]
            lat, lon = self._local_to_gps(x, y, home_lat, home_lon)
            ...
"""

import math


class PositioningMixin:
    """
    Provides coordinate conversion from local X/Y (metres) to WGS84 lat/lon.

    Uses an equirectangular approximation which is accurate within ~1 km of
    the home position — sufficient for indoor lab and campus-scale VICON setups.

    Assumes X = East, Y = North from the local origin.
    If your VICON system uses a different convention (e.g. X = Forward, Y = Left),
    swap or negate the axes before calling _local_to_gps().
    """

    _EARTH_RADIUS_M: float = 6_371_000.0

    @staticmethod
    def _local_to_gps(
        x_m: float,
        y_m: float,
        home_lat: float,
        home_lon: float,
    ) -> tuple[float, float]:
        """
        Convert a local East/North offset to WGS84 latitude and longitude.

        Args:
            x_m:      East offset in metres from home position.
            y_m:      North offset in metres from home position.
            home_lat: WGS84 latitude of the local origin (decimal degrees).
            home_lon: WGS84 longitude of the local origin (decimal degrees).

        Returns:
            (lat, lon) in decimal degrees.
        """
        R = 6_371_000.0
        lat = home_lat + math.degrees(y_m / R)
        lon = home_lon + math.degrees(x_m / (R * math.cos(math.radians(home_lat))))
        return lat, lon
