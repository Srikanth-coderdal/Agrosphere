const DB_NAME = "AgroSphereOffline";
const DB_VERSION = 1;
const STORE_NAME = "scans";

interface ScanRecord {
  id?: number;
  payload: Record<string, unknown>;
  timestamp?: number;
}

export interface QueuedScanItem {
  id: number;
  payload: Record<string, unknown>;
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is not available in this environment."));
      return;
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id", autoIncrement: true });
      }
    };

    request.onsuccess = () => {
      resolve(request.result);
    };

    request.onerror = () => {
      reject(request.error || new Error("Failed to open IndexedDB"));
    };
  });
}

export const OFFLINE_QUEUE_EVENT = "agrosphere:offline-queue-updated";

function notifyQueueChanged(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(OFFLINE_QUEUE_EVENT));
  }
}

/**
 * Stores a pending scan request payload into IndexedDB (AgroSphereOffline / scans).
 */
export async function queueOfflineScan(payload: Record<string, unknown>): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const item: ScanRecord = {
      payload,
      timestamp: Date.now(),
    };
    const req = store.add(item);

    req.onsuccess = () => {
      notifyQueueChanged();
      resolve();
    };
    req.onerror = () => reject(req.error || new Error("Failed to queue offline scan"));
  });
}

/**
 * Retrieves all queued scan items from IndexedDB.
 */
export async function getQueuedScans(): Promise<Array<{ id: number; payload: Record<string, unknown> }>> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const req = store.openCursor();
    const results: Array<{ id: number; payload: Record<string, unknown> }> = [];

    req.onsuccess = () => {
      const cursor = req.result;
      if (cursor) {
        results.push({
          id: cursor.primaryKey as number,
          payload: (cursor.value as ScanRecord).payload,
        });
        cursor.continue();
      } else {
        resolve(results);
      }
    };

    req.onerror = () => reject(req.error || new Error("Failed to retrieve queued scans"));
  });
}

/**
 * Removes a queued scan item by ID from IndexedDB.
 */
export async function removeQueuedScan(id: number): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const req = store.delete(id);

    req.onsuccess = () => {
      notifyQueueChanged();
      resolve();
    };
    req.onerror = () => reject(req.error || new Error(`Failed to remove scan with id ${id}`));
  });
}

/**
 * Flushes all pending scan items using the provided API sender callback and removes successful ones.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function flushScanQueue(sendApiCallback: (payload: any) => Promise<boolean>): Promise<void> {
  const items = await getQueuedScans();
  for (const item of items) {
    try {
      const success = await sendApiCallback(item.payload);
      if (success) {
        await removeQueuedScan(item.id);
      }
    } catch {
      // Keep in queue on error to retry next time
    }
  }
  notifyQueueChanged();
}

/**
 * Backwards-compatible wrappers
 */
export async function queueScan(payload: Record<string, unknown>): Promise<void> {
  return queueOfflineScan(payload);
}

export async function flushQueue(): Promise<{ success: number; failed: number }> {
  let success = 0;
  let failed = 0;
  await flushScanQueue(async (payload) => {
    try {
      const formData = new FormData();
      if (payload.imageBlob instanceof Blob) {
        formData.append("image", payload.imageBlob, "scan.jpg");
      } else if (payload.image instanceof Blob) {
        formData.append("image", payload.image, "scan.jpg");
      }
      if (payload.cropType || payload.crop_type) {
        formData.append("crop_type", String(payload.cropType || payload.crop_type));
      }
      if (payload.latitude !== undefined && payload.latitude !== null) {
        formData.append("latitude", String(payload.latitude));
      }
      if (payload.longitude !== undefined && payload.longitude !== null) {
        formData.append("longitude", String(payload.longitude));
      }
      if (payload.farmerComment || payload.farmer_comment) {
        formData.append("farmer_comment", String(payload.farmerComment || payload.farmer_comment));
      }
      if (payload.language) formData.append("language", String(payload.language));
      const opContext =
        payload.operational_context ||
        payload.operationalContext ||
        payload.context_mode ||
        payload.contextMode;
      if (opContext) {
        formData.append("operational_context", String(opContext));
      }

      const headers: Record<string, string> = {};
      if (typeof window !== "undefined") {
        const token = localStorage.getItem("agrosphere_token");
        if (token) headers["Authorization"] = `Bearer ${token}`;
      }

      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${apiBase}/api/scan`, {
        method: "POST",
        headers,
        body: formData,
      });
      if (res.ok) {
        success++;
        return true;
      }
      failed++;
      return false;
    } catch {
      failed++;
      return false;
    }
  });
  return { success, failed };
}

/**
 * Attaches an `online` listener to trigger sync when connectivity returns.
 */
export function registerOnlineSyncListener(): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => {
    setTimeout(() => {
      void flushQueue();
    }, 500);
  };
  window.addEventListener("online", handler);
  return () => {
    window.removeEventListener("online", handler);
  };
}
