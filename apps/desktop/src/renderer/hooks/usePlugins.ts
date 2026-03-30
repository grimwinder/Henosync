import { useQuery } from "@tanstack/react-query";
import * as api from "../lib/api";

export const PLUGIN_KEYS = {
  device: ["plugins", "device"] as const,
  control: ["plugins", "control"] as const,
  transports: ["plugins", "transports"] as const,
};

export function useDevicePlugins() {
  return useQuery({
    queryKey: PLUGIN_KEYS.device,
    queryFn: api.getDevicePlugins,
    staleTime: Infinity,
  });
}

export function useControlPlugins() {
  return useQuery({
    queryKey: PLUGIN_KEYS.control,
    queryFn: api.getControlPlugins,
    staleTime: Infinity,
  });
}

export function useTransports() {
  return useQuery({
    queryKey: PLUGIN_KEYS.transports,
    queryFn: api.getTransports,
    staleTime: Infinity,
  });
}
