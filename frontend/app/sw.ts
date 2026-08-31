/// <reference lib="webworker" />
import type { PrecacheEntry } from "serwist";
import { Serwist } from "serwist";
import { defaultCache } from "@serwist/next/worker";
import { flushQueue } from "@/lib/syncManager";

declare const self: ServiceWorkerGlobalScope & {
  __SW_MANIFEST: PrecacheEntry[] | undefined;
};

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: defaultCache,
});

serwist.addEventListeners();

self.addEventListener("sync", (event: Event) => {
  const syncEvent = event as Event & { tag?: string; waitUntil?: (promise: Promise<unknown>) => void };
  if (syncEvent.tag === "sync-scans" || syncEvent.tag === "offline-sync") {
    if (syncEvent.waitUntil) {
      syncEvent.waitUntil(flushQueue());
    }
  }
});
