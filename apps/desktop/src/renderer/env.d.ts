/// <reference types="vite/client" />

import type { HensoyncAPI } from "../preload/index";

declare global {
  interface Window {
    henosync: HensoyncAPI;
  }
}
