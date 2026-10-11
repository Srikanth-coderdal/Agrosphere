/// <reference lib="webworker" />
import type { PrecacheEntry } from "serwist";
import { Serwist } from "serwist";
import { defaultCache } from "@serwist/next/worker";
import { flushQueue } from "@/lib/syncManager";

declare const self: ServiceWorkerGlobalScope & {
  __SW_MANIFEST: PrecacheEntry[] | undefined;
};

const APP_SHELL_ROUTES = ["/", "/scan", "/irrigation", "/yield-estimator", "/urban", "/login", "/signup"];
const APP_SHELL_CACHE = "agrosphere-app-shell-v1";

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: defaultCache,
});

serwist.addEventListeners();

self.addEventListener("install", (event: ExtendableEvent) => {
  event.waitUntil(
    caches
      .open(APP_SHELL_CACHE)
      .then((cache) =>
        Promise.allSettled(APP_SHELL_ROUTES.map((route) => cache.add(route)))
      )
  );
});

self.addEventListener("sync", (event: Event) => {
  const syncEvent = event as Event & { tag?: string; waitUntil?: (promise: Promise<unknown>) => void };
  if (syncEvent.tag === "sync-scans" || syncEvent.tag === "offline-sync") {
    if (syncEvent.waitUntil) {
      syncEvent.waitUntil(flushQueue());
    }
  }
});
