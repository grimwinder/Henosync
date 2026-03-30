/// <reference types="vite/client" />

import type { HenosyncAPI } from "../preload/index";

declare global {
  interface Window {
    henosync: HenosyncAPI;
  }
}
