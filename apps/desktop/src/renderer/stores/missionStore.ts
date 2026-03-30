import { create } from "zustand";
import type { Mission, MissionEngineStatus } from "../types";

interface MissionStore {
  // State
  missions: Record<string, Mission>;
  selectedMissionId: string | null;
  engineStatus: MissionEngineStatus | null;

  // Actions
  setMissions: (missions: Mission[]) => void;
  upsertMission: (mission: Mission) => void;
  removeMission: (id: string) => void;
  setSelectedMission: (id: string | null) => void;
  setEngineStatus: (status: MissionEngineStatus) => void;
}

export const useMissionStore = create<MissionStore>((set) => ({
  missions: {},
  selectedMissionId: null,
  engineStatus: null,

  setMissions: (missions) =>
    set({ missions: Object.fromEntries(missions.map((m) => [m.id, m])) }),

  upsertMission: (mission) =>
    set((s) => ({ missions: { ...s.missions, [mission.id]: mission } })),

  removeMission: (id) =>
    set((s) => {
      const missions = { ...s.missions };
      delete missions[id];
      return {
        missions,
        selectedMissionId:
          s.selectedMissionId === id ? null : s.selectedMissionId,
      };
    }),

  setSelectedMission: (id) => set({ selectedMissionId: id }),

  setEngineStatus: (status) => set({ engineStatus: status }),
}));
