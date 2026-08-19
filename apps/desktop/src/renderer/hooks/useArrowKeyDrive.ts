import { useEffect, useRef } from "react";
import { sendOperatorInput } from "../lib/api";

const KEY_MAP: Record<string, string> = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  w: "up",
  s: "down",
  a: "left",
  d: "right",
};

// Sends arrow-key press/release state to a running control plugin operation
// via on_operator_input. Ignores OS key-repeat and releases all held keys
// on cleanup so the device never keeps driving after the panel closes.
export function useArrowKeyDrive(active: boolean, pluginId: string) {
  const pressedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!active) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const inputKey = KEY_MAP[e.key];
      if (!inputKey || pressedRef.current.has(inputKey)) return;
      e.preventDefault();
      pressedRef.current.add(inputKey);
      sendOperatorInput(pluginId, inputKey, true).catch(() => {});
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      const inputKey = KEY_MAP[e.key];
      if (!inputKey) return;
      e.preventDefault();
      pressedRef.current.delete(inputKey);
      sendOperatorInput(pluginId, inputKey, false).catch(() => {});
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      for (const inputKey of pressedRef.current) {
        sendOperatorInput(pluginId, inputKey, false).catch(() => {});
      }
      pressedRef.current.clear();
    };
  }, [active, pluginId]);
}
