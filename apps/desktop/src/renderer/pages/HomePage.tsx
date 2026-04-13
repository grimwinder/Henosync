import { useState, useRef } from "react";
import maplibregl from "maplibre-gl";
import { useNodeStore } from "../stores/nodeStore";
import DevicePanel from "../components/fleet/DevicePanel";
import DeviceDetailPanel from "../components/fleet/DeviceDetailPanel";
import MissionMap, {
  type MapBase,
  type MapTheme,
} from "../components/map/MissionMap";
import MapStylePicker from "../components/map/MapStylePicker";
import NodeMarkers from "../components/map/NodeMarkers";
import HubMarker from "../components/map/HubMarker";
import { useHubLocation } from "../hooks/useHubLocation";

export default function HomePage() {
  const selectedNodeId = useNodeStore((s) => s.selectedNodeId);
  const nodes = useNodeStore((s) => s.nodes);
  const selectedNode = selectedNodeId ? nodes[selectedNodeId] : null;
  const hubLocation = useHubLocation();

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const [mapBase, setMapBase] = useState<MapBase>("standard");
  const [mapTheme, setMapTheme] = useState<MapTheme>("dark");
  const [savedView, setSavedView] = useState<{
    center: [number, number];
    zoom: number;
  } | null>(null);

  function handleMapReady(m: maplibregl.Map) {
    mapRef.current = m;
    setMap(m);
  }

  function saveAndSwitch(base: MapBase, theme: MapTheme) {
    if (mapRef.current) {
      const c = mapRef.current.getCenter();
      setSavedView({ center: [c.lng, c.lat], zoom: mapRef.current.getZoom() });
    }
    setMap(null);
    setMapBase(base);
    setMapTheme(theme);
  }

  const styleKey = `${mapBase}-${mapTheme}`;

  return (
    <div
      style={{
        display: "flex",
        flex: 1,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Map fills the entire background */}
      <div style={{ position: "absolute", inset: 0 }}>
        <MissionMap
          key={styleKey}
          mapBase={mapBase}
          mapTheme={mapTheme}
          initialCenter={savedView?.center}
          initialZoom={savedView?.zoom}
          onMapReady={handleMapReady}
        />
        {map && <NodeMarkers map={map} />}
        {map && <HubMarker map={map} location={hubLocation} />}
      </div>

      {/* Map style picker — top-center */}
      <MapStylePicker
        mapBase={mapBase}
        mapTheme={mapTheme}
        onChangeBase={(base) => saveAndSwitch(base, mapTheme)}
        onChangeTheme={(theme) => saveAndSwitch(mapBase, theme)}
        position="top-center"
      />

      {/* Fleet panel — top-left, half height */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          height: "50%",
          zIndex: 10,
        }}
      >
        <DevicePanel readOnly />
      </div>

      {/* Detail panel — right side, full height */}
      {selectedNode && (
        <div
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            height: "100%",
            zIndex: 10,
          }}
        >
          <DeviceDetailPanel node={selectedNode} readOnly />
        </div>
      )}
    </div>
  );
}
