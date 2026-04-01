import { useState, useEffect } from "react";
import { HUB_LOCATION } from "../components/map/MissionMap";

/**
 * Resolves the hub location using the browser Geolocation API.
 * Returns HUB_LOCATION as the initial value immediately (so the map
 * is never locationless), then updates to the real GPS position once
 * the browser resolves it.  Falls back permanently to HUB_LOCATION
 * if permission is denied or the API is unavailable.
 */
export function useHubLocation(): [number, number] {
  const [location, setLocation] = useState<[number, number]>(HUB_LOCATION);

  useEffect(() => {
    if (!navigator.geolocation) return;

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocation([pos.coords.longitude, pos.coords.latitude]);
      },
      () => {
        // Permission denied or unavailable — keep fallback, no-op
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }, []);

  return location;
}
