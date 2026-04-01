// ── Enums ──────────────────────────────────────────────────────────────────────

export type NodeStatus =
  | "connecting"
  | "online"
  | "degraded"
  | "offline"
  | "error";

export type DeviceCategory =
  | "drone"
  | "plane"
  | "agv"
  | "boat"
  | "rov"
  | "arm"
  | "unknown";

export type DeviceCapability =
  | "move_2d"
  | "move_3d"
  | "gps"
  | "lidar"
  | "camera"
  | "sonar"
  | "imu"
  | "thermal"
  | "horn"
  | "lights"
  | "payload"
  | "arm_tool"
  | "battery"
  | "charging";

export type StepType =
  | "move"
  | "action"
  | "wait"
  | "condition"
  | "parallel"
  | "loop"
  | "wait_for";

export type StepStatus =
  | "pending"
  | "active"
  | "completed"
  | "failed"
  | "skipped";

export type MissionStatus =
  | "draft"
  | "ready"
  | "executing"
  | "paused"
  | "completed"
  | "aborted"
  | "failed";

export type ConditionOperator = "gt" | "lt" | "eq" | "neq";

export type FailsafeAction = "abort" | "pause" | "continue" | "return_home";

export type EventSeverity = "info" | "warning" | "critical";

export type OperationState =
  | "idle"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "stopping";

export type ZoneType =
  | "perimeter"
  | "no_go"
  | "safe_return"
  | "coverage"
  | "alert"
  | "custom";

export type ZoneShape = "polygon" | "circle";

export type AppMode = "plan" | "execute" | "review";

// ── Node / Device models ───────────────────────────────────────────────────────

export interface Position {
  lat: number;
  lon: number;
  alt: number;
  heading?: number | null;
  accuracy?: number | null;
}

export interface LocalOrigin {
  lat: number;
  lon: number;
  alt: number;
}

export interface CapabilitySpec {
  capability: DeviceCapability;
  max_range?: number | null;
  resolution?: number | null;
  fps?: number | null;
  fov?: number | null;
  dimensions?: number | null;
  notes?: string | null;
}

export interface CapabilityRequirement {
  capability: DeviceCapability;
  min_range?: number | null;
  min_resolution?: number | null;
  min_fps?: number | null;
  required: boolean;
}

export interface DeviceSpecs {
  category: DeviceCategory;
  capabilities: CapabilitySpec[];
  weight_kg?: number | null;
  length_m?: number | null;
  width_m?: number | null;
  height_m?: number | null;
  max_speed_ms?: number | null;
  max_range_m?: number | null;
  max_altitude_m?: number | null;
  min_altitude_m?: number | null;
  battery_capacity_wh?: number | null;
  endurance_minutes?: number | null;
  has_gps: boolean;
  uses_odometry: boolean;
  coordinate_frame: string;
}

export interface NodeCapability {
  id: string;
  label: string;
  params: string[];
  destructive: boolean;
}

export interface Node {
  id: string;
  name: string;
  plugin_id: string;
  status: NodeStatus;
  position: Position;
  battery_percent: number | null;
  signal_strength: number | null;
  capabilities: NodeCapability[];
  telemetry: Record<string, unknown>;
  last_seen: string | null;
  home_position: Position | null;
  local_origin: LocalOrigin | null;
  config: Record<string, unknown>;
  specs: DeviceSpecs | null;
}

export interface NodeCreate {
  name: string;
  plugin_id: string;
  config: Record<string, unknown>;
}

// ── Mission models ─────────────────────────────────────────────────────────────

export interface Condition {
  telemetry_key: string;
  operator: ConditionOperator;
  value: number;
  node_id: string;
}

export interface MissionStep {
  id: string;
  step_type: StepType;
  label: string;
  target_node_id: string | null;
  parameters: Record<string, unknown>;
  status: StepStatus;
  on_complete: string | null;
  on_fail: string | null;
  condition: Condition | null;
  then_step_id: string | null;
  else_step_id: string | null;
  parallel_step_ids: string[];
  loop_step_ids: string[];
  loop_count: number | null;
  loop_condition: Condition | null;
  wait_for_condition: Condition | null;
  wait_for_timeout_seconds: number;
}

export interface FailsafeConfig {
  on_node_lost: FailsafeAction;
  on_low_battery: FailsafeAction;
  low_battery_threshold: number;
}

export interface Mission {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  status: MissionStatus;
  steps: MissionStep[];
  failsafe: FailsafeConfig;
  metadata: Record<string, unknown>;
}

export interface MissionCreate {
  name: string;
  steps?: MissionStep[];
  failsafe?: Partial<FailsafeConfig>;
  metadata?: Record<string, unknown>;
}

export interface MissionUpdate {
  name?: string;
  steps?: MissionStep[];
  failsafe?: FailsafeConfig;
  metadata?: Record<string, unknown>;
}

export interface MissionEngineStatus {
  status: MissionStatus;
  mission_id: string | null;
  mission_name: string | null;
  current_step: number;
  total_steps: number;
}

// ── Telemetry / events ─────────────────────────────────────────────────────────

export interface TelemetryWsMessage {
  type: "telemetry";
  node_id: string;
  timestamp: string;
  sequence: number;
  values: Record<string, unknown>;
}

export interface SystemEvent {
  id: string;
  severity: EventSeverity;
  title: string;
  message: string;
  node_id: string | null;
  timestamp: string;
  acknowledged: boolean;
}

export interface EventWsMessage extends SystemEvent {
  type: "event";
}

export interface PingWsMessage {
  type: "ping";
}

export type WsMessage = TelemetryWsMessage | EventWsMessage | PingWsMessage;

export interface CommandResult {
  success: boolean;
  message: string;
  data: Record<string, unknown>;
}

// ── Plugin models ──────────────────────────────────────────────────────────────

export interface PluginCapabilityDef {
  id: string;
  label: string;
  params: string[];
  destructive?: boolean;
}

export interface PluginConfigField {
  type: "string" | "number" | "boolean";
  label: string;
  required?: boolean;
  default?: unknown;
  placeholder?: string;
}

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  author: string;
  description: string;
  sdk_version: string;
  node_types: string[];
  capabilities: PluginCapabilityDef[];
  transport: string;
  icon?: string;
  config_schema?: Record<string, PluginConfigField>;
}

export interface UIContribution {
  config_schema: Record<string, unknown>;
  display_name: string;
  description: string;
  icon: string;
}

export interface ControlPluginInfo {
  id: string;
  name: string;
  version: string;
  author: string;
  operation_name: string;
  description: string;
  required_capabilities: DeviceCapability[];
  supported_categories: DeviceCategory[];
  priority: number;
  ui: UIContribution;
}

// ── Operation models ───────────────────────────────────────────────────────────

export interface OperationStatus {
  state: OperationState;
  status_text: string;
  progress_percent: number | null;
  devices_active: string[];
  devices_available: string[];
  data: Record<string, unknown>;
}

export interface RunningOperation {
  plugin_id: string;
  operation_name: string;
  started_at: string;
  status: OperationStatus;
}

// ── Zone models ────────────────────────────────────────────────────────────────

export interface GeoPoint {
  lat: number;
  lon: number;
}

export interface Zone {
  id: string;
  name: string;
  zone_type: ZoneType;
  shape: ZoneShape;
  points: GeoPoint[];
  center: GeoPoint | null;
  radius_m: number | null;
  created_by: string;
  active: boolean;
  color: string;
}

export interface ZoneCreate {
  name: string;
  zone_type: ZoneType;
  points?: GeoPoint[];
  center?: GeoPoint;
  radius_m?: number;
  color?: string;
}

// ── Marker models ─────────────────────────────────────────────────────────────

export type MarkerType =
  | "home_position"
  | "waypoint"
  | "reference"
  | "hazard"
  | "custom";

export interface MapMarker {
  id: string;
  name: string;
  marker_type: MarkerType;
  lat: number;
  lon: number;
  color: string;
}

export interface MapMarkerCreate {
  name: string;
  marker_type: MarkerType;
  lat: number;
  lon: number;
  color?: string;
}

// ── Health ─────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: "ok";
  version: string;
  nodes_total: number;
  nodes_online: number;
}
