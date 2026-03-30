import type { WsMessage } from "../types";
import { useNodeStore } from "../stores/nodeStore";
import { useSystemStore } from "../stores/systemStore";

const BACKEND_WS = "ws://127.0.0.1:8765";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
const RECONNECT_BACKOFF = 1.5;

// ── WebSocket connection ───────────────────────────────────────────────────────

class ManagedSocket {
  private ws: WebSocket | null = null;
  private reconnectDelay = RECONNECT_BASE_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;

  constructor(
    private readonly url: string,
    private readonly onMessage: (msg: WsMessage) => void,
    private readonly onStatusChange?: (connected: boolean) => void,
  ) {}

  connect() {
    if (this.stopped) return;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.reconnectDelay = RECONNECT_BASE_MS;
      this.onStatusChange?.(true);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as WsMessage;
        if (msg.type !== "ping") {
          this.onMessage(msg);
        }
      } catch {
        // Ignore malformed frames
      }
    };

    this.ws.onerror = () => {
      // onclose fires after onerror, reconnect logic lives there
    };

    this.ws.onclose = () => {
      this.onStatusChange?.(false);
      if (!this.stopped) this.scheduleReconnect();
    };
  }

  private scheduleReconnect() {
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(
        this.reconnectDelay * RECONNECT_BACKOFF,
        RECONNECT_MAX_MS,
      );
      this.connect();
    }, this.reconnectDelay);
  }

  disconnect() {
    this.stopped = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}

// ── Message handlers ───────────────────────────────────────────────────────────

function handleTelemetry(msg: WsMessage) {
  if (msg.type !== "telemetry") return;
  useNodeStore.getState().updateTelemetry(msg.node_id, msg.values);
}

function handleEvent(msg: WsMessage) {
  if (msg.type !== "event") return;
  useSystemStore.getState().addEvent({
    id: msg.id,
    severity: msg.severity,
    title: msg.title,
    message: msg.message,
    node_id: msg.node_id,
    timestamp: msg.timestamp,
    acknowledged: msg.acknowledged,
  });
}

// ── WebSocket manager singleton ────────────────────────────────────────────────

class WebSocketManager {
  private telemetrySocket: ManagedSocket | null = null;
  private eventsSocket: ManagedSocket | null = null;
  private started = false;

  start() {
    if (this.started) return;
    this.started = true;

    this.telemetrySocket = new ManagedSocket(
      `${BACKEND_WS}/ws/telemetry`,
      handleTelemetry,
    );

    this.eventsSocket = new ManagedSocket(
      `${BACKEND_WS}/ws/events`,
      handleEvent,
      (connected) => {
        // Use the events socket as the proxy for overall WS connectivity
        useSystemStore.getState().setBackendConnected(connected);
      },
    );

    this.telemetrySocket.connect();
    this.eventsSocket.connect();
  }

  stop() {
    this.telemetrySocket?.disconnect();
    this.eventsSocket?.disconnect();
    this.telemetrySocket = null;
    this.eventsSocket = null;
    this.started = false;
  }
}

export const wsManager = new WebSocketManager();
