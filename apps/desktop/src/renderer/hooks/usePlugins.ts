import { useQuery } from "@tanstack/react-query";
import { getDevicePlugins, getControlPlugins, getTransports } from "../lib/api";

export const PLUGIN_KEYS = {
  device: ["plugins", "device"] as const,
  control: ["plugins", "control"] as const,
  transports: ["plugins", "transports"] as const,
};

export function useDevicePlugins() {
  return useQuery({
    queryKey: PLUGIN_KEYS.device,
    queryFn: getDevicePlugins,
    staleTime: 30_000,
  });
}

export function useControlPlugins() {
  return useQuery({
    queryKey: PLUGIN_KEYS.control,
    queryFn: getControlPlugins,
    staleTime: 30_000,
  });
}

export function useTransports() {
  return useQuery({
    queryKey: PLUGIN_KEYS.transports,
    queryFn: getTransports,
    staleTime: Infinity,
  });
}
