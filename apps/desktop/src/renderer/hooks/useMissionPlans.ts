import { useState, useCallback } from "react";
import type { MissionBlock } from "../pages/MissionPage";

// ── Persisted type ─────────────────────────────────────────────────────────────

export interface MissionPlan {
  id: string;
  name: string;
  savedAt: string; // ISO-8601
  blocks: MissionBlock[];
}

const STORAGE_KEY = "henosync_mission_plans";

function read(): MissionPlan[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as MissionPlan[]) : [];
  } catch {
    return [];
  }
}

function write(plans: MissionPlan[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(plans));
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useMissionPlans() {
  const [plans, setPlans] = useState<MissionPlan[]>(read);

  /** Snapshot the given blocks under a name. */
  const save = useCallback((name: string, blocks: MissionBlock[]) => {
    const plan: MissionPlan = {
      id: crypto.randomUUID(),
      name: name.trim() || "Untitled Plan",
      savedAt: new Date().toISOString(),
      // Re-stamp instanceIds so re-saves don't share references
      blocks: blocks.map((b) => ({ ...b, instanceId: crypto.randomUUID() })),
    };
    setPlans((prev) => {
      const next = [plan, ...prev];
      write(next);
      return next;
    });
  }, []);

  /** Remove a saved plan by id. */
  const remove = useCallback((id: string) => {
    setPlans((prev) => {
      const next = prev.filter((p) => p.id !== id);
      write(next);
      return next;
    });
  }, []);

  return { plans, save, remove };
}
