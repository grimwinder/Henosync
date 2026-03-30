import { create } from "zustand";
import type { HealthResponse, SystemEvent } from "../types";

const MAX_EVENTS = 100;

interface SystemStore {
  // State
  health: HealthResponse | null;
  backendConnected: boolean;
  events: SystemEvent[];
  unreadCount: number;

  // Actions
  setHealth: (health: HealthResponse) => void;
  setBackendConnected: (connected: boolean) => void;
  addEvent: (event: SystemEvent) => void;
  acknowledgeEvent: (id: string) => void;
  clearEvents: () => void;
  markAllRead: () => void;
}

export const useSystemStore = create<SystemStore>((set) => ({
  health: null,
  backendConnected: false,
  events: [],
  unreadCount: 0,

  setHealth: (health) => set({ health, backendConnected: true }),

  setBackendConnected: (connected) => set({ backendConnected: connected }),

  addEvent: (event) =>
    set((s) => {
      const events = [event, ...s.events].slice(0, MAX_EVENTS);
      return { events, unreadCount: s.unreadCount + 1 };
    }),

  acknowledgeEvent: (id) =>
    set((s) => ({
      events: s.events.map((e) =>
        e.id === id ? { ...e, acknowledged: true } : e,
      ),
    })),

  clearEvents: () => set({ events: [], unreadCount: 0 }),

  markAllRead: () => set({ unreadCount: 0 }),
}));
