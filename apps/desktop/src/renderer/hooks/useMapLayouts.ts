import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import * as api from "../lib/api";
import { useZoneStore } from "../stores/zoneStore";
import { useMarkerStore } from "../stores/markerStore";
import { ZONE_KEYS } from "./useZones";
import { MARKER_KEYS } from "./useMarkers";
import type { Zone, MapMarker, ZoneCreate, MapMarkerCreate } from "../types";

// ── Persisted type ─────────────────────────────────────────────────────────────

export interface MapLayout {
  id: string;
  name: string;
  savedAt: string; // ISO-8601
  zones: Zone[];
  markers: MapMarker[];
}

const STORAGE_KEY = "henosync_map_layouts";

function readLayouts(): MapLayout[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as MapLayout[]) : [];
  } catch {
    return [];
  }
}

function writeLayouts(layouts: MapLayout[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(layouts));
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useMapLayouts() {
  const [layouts, setLayouts] = useState<MapLayout[]>(readLayouts);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const qc = useQueryClient();
  const zones = useZoneStore((s) => Object.values(s.zones));
  const markers = useMarkerStore((s) => Object.values(s.markers));
  const setZones = useZoneStore((s) => s.setZones);
  const setMarkers = useMarkerStore((s) => s.setMarkers);

  /** Snapshot current zones + markers under a given name. */
  const save = useCallback(
    (name: string) => {
      const layout: MapLayout = {
        id: crypto.randomUUID(),
        name: name.trim() || "Untitled Map",
        savedAt: new Date().toISOString(),
        zones: [...zones],
        markers: [...markers],
      };
      setLayouts((prev) => {
        const next = [layout, ...prev];
        writeLayouts(next);
        return next;
      });
    },
    [zones, markers],
  );

  /** Remove a saved layout by id. */
  const remove = useCallback((id: string) => {
    setLayouts((prev) => {
      const next = prev.filter((l) => l.id !== id);
      writeLayouts(next);
      return next;
    });
  }, []);

  /** Rename a saved layout. */
  const rename = useCallback((id: string, name: string) => {
    setLayouts((prev) => {
      const next = prev.map((l) =>
        l.id === id ? { ...l, name: name.trim() || l.name } : l,
      );
      writeLayouts(next);
      return next;
    });
  }, []);

  /**
   * Replace all current zones + markers with those from the saved layout.
   * Deletes existing backend records then recreates from the snapshot.
   */
  const load = useCallback(
    async (layout: MapLayout) => {
      setLoadingId(layout.id);
      try {
        // Delete all current zones and markers in parallel
        await Promise.all([
          ...zones.map((z) => api.deleteZone(z.id)),
          ...markers.map((m) => api.deleteMarker(m.id)),
        ]);

        // Recreate zones from snapshot
        const newZones = await Promise.all(
          layout.zones.map((z) => {
            const body: ZoneCreate = {
              name: z.name,
              zone_type: z.zone_type,
              color: z.color,
              ...(z.shape === "circle" && z.center
                ? { center: z.center, radius_m: z.radius_m ?? undefined }
                : { points: z.points }),
            };
            return api.createZone(body);
          }),
        );

        // Recreate markers from snapshot
        const newMarkers = await Promise.all(
          layout.markers.map((m) => {
            const body: MapMarkerCreate = {
              name: m.name,
              marker_type: m.marker_type,
              lat: m.lat,
              lon: m.lon,
              color: m.color,
            };
            return api.createMarker(body);
          }),
        );

        // Push into stores and refresh cache
        setZones(newZones);
        setMarkers(newMarkers);
        qc.invalidateQueries({ queryKey: ZONE_KEYS.all });
        qc.invalidateQueries({ queryKey: MARKER_KEYS.all });
      } catch (err) {
        console.error("[useMapLayouts] load failed:", err);
        // Recover consistent state from server
        qc.invalidateQueries({ queryKey: ZONE_KEYS.all });
        qc.invalidateQueries({ queryKey: MARKER_KEYS.all });
      } finally {
        setLoadingId(null);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [zones, markers],
  );

  return { layouts, loadingId, save, remove, rename, load };
}
