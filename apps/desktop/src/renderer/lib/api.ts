import type {
  Node,
  NodeCreate,
  Mission,
  MissionCreate,
  MissionUpdate,
  MissionEngineStatus,
  PluginManifest,
  ControlPluginInfo,
  RunningOperation,
  Zone,
  ZoneCreate,
  MapMarker,
  MapMarkerCreate,
  HealthResponse,
  CommandResult,
} from "../types";

export const BACKEND_URL = "http://127.0.0.1:8765";

// ── Base fetch ─────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BACKEND_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch (err) {
    console.error(
      `[apiFetch] Network error for ${init?.method ?? "GET"} ${url}:`,
      err,
    );
    throw err;
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail?.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Health ─────────────────────────────────────────────────────────────────────

export const getHealth = () => apiFetch<HealthResponse>("/health");

// ── Nodes ──────────────────────────────────────────────────────────────────────

export const getNodes = () =>
  apiFetch<{ nodes: Node[] }>("/api/nodes/").then((r) => r.nodes);

export const getNode = (id: string) => apiFetch<Node>(`/api/nodes/${id}`);

export const addNode = (body: NodeCreate) =>
  apiFetch<Node>("/api/nodes/", { method: "POST", body: JSON.stringify(body) });

export const removeNode = (id: string) =>
  apiFetch<{ success: boolean }>(`/api/nodes/${id}`, { method: "DELETE" });

export const reconnectNode = (id: string) =>
  apiFetch<{ success: boolean }>(`/api/nodes/${id}/reconnect`, {
    method: "POST",
  });

export const sendCommand = (
  id: string,
  capability: string,
  params: Record<string, unknown> = {},
) =>
  apiFetch<CommandResult>(`/api/nodes/${id}/command`, {
    method: "POST",
    body: JSON.stringify({ capability, params }),
  });

export const getStreamUrl = (id: string) =>
  apiFetch<{ stream_url: string | null }>(`/api/nodes/${id}/stream_url`);

// ── Missions ───────────────────────────────────────────────────────────────────

export const getMissions = () =>
  apiFetch<{ missions: Mission[] }>("/api/missions/").then((r) => r.missions);

export const getMission = (id: string) =>
  apiFetch<Mission>(`/api/missions/${id}`);

export const createMission = (body: MissionCreate) =>
  apiFetch<Mission>("/api/missions/", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateMission = (id: string, body: MissionUpdate) =>
  apiFetch<Mission>(`/api/missions/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const deleteMission = (id: string) =>
  apiFetch<{ success: boolean }>(`/api/missions/${id}`, { method: "DELETE" });

export const executeMission = (id: string) =>
  apiFetch<{ success: boolean; status: MissionEngineStatus }>(
    `/api/missions/${id}/execute`,
    {
      method: "POST",
    },
  );

export const pauseMission = (id: string) =>
  apiFetch<{ success: boolean; status: MissionEngineStatus }>(
    `/api/missions/${id}/pause`,
    {
      method: "POST",
    },
  );

export const resumeMission = (id: string) =>
  apiFetch<{ success: boolean; status: MissionEngineStatus }>(
    `/api/missions/${id}/resume`,
    {
      method: "POST",
    },
  );

export const abortMission = (id: string) =>
  apiFetch<{ success: boolean; status: MissionEngineStatus }>(
    `/api/missions/${id}/abort`,
    {
      method: "POST",
    },
  );

export const getMissionEngineStatus = () =>
  apiFetch<MissionEngineStatus>("/api/missions/engine/status");

// ── Plugins ────────────────────────────────────────────────────────────────────

export const getDevicePlugins = () =>
  apiFetch<{ plugins: PluginManifest[] }>("/api/plugins").then(
    (r) => r.plugins,
  );

export const getTransports = () =>
  apiFetch<{ transports: string[] }>("/api/transports").then(
    (r) => r.transports,
  );

export const getControlPlugins = () =>
  apiFetch<{ plugins: ControlPluginInfo[] }>("/api/control-plugins").then(
    (r) => r.plugins,
  );

// ── Operations ─────────────────────────────────────────────────────────────────

export const getOperations = () =>
  apiFetch<{ operations: RunningOperation[] }>("/api/operations").then(
    (r) => r.operations,
  );

export const startOperation = (
  plugin_id: string,
  config: Record<string, unknown> = {},
) =>
  apiFetch<{ success: boolean; message: string }>("/api/operations/start", {
    method: "POST",
    body: JSON.stringify({ plugin_id, config }),
  });

export const stopOperation = (plugin_id: string) =>
  apiFetch<{ success: boolean; message: string }>(
    `/api/operations/${plugin_id}/stop`,
    {
      method: "POST",
    },
  );

// ── Zones ──────────────────────────────────────────────────────────────────────

export const getZones = () =>
  apiFetch<{ zones: Zone[] }>("/api/zones").then((r) => r.zones);

export const createZone = (body: ZoneCreate) =>
  apiFetch<Zone>("/api/zones", { method: "POST", body: JSON.stringify(body) });

export const deleteZone = (id: string) =>
  apiFetch<{ success: boolean }>(`/api/zones/${id}`, { method: "DELETE" });

// ── Markers ────────────────────────────────────────────────────────────────────

export const getMarkers = () =>
  apiFetch<{ markers: MapMarker[] }>("/api/markers").then((r) => r.markers);

export const createMarker = (body: MapMarkerCreate) =>
  apiFetch<MapMarker>("/api/markers", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const deleteMarker = (id: string) =>
  apiFetch<{ success: boolean }>(`/api/markers/${id}`, { method: "DELETE" });

// ── Safety ─────────────────────────────────────────────────────────────────────

export const emergencyStop = () =>
  apiFetch<{ success: boolean; message: string }>(
    "/api/safety/emergency-stop",
    {
      method: "POST",
    },
  );
