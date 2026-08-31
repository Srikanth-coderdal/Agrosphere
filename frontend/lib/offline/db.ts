import { openDB, DBSchema, IDBPDatabase } from 'idb';

/**
 * Pending leaf scan payload stored offline.
 * `imageBlob` is persisted as a File/Blob; `idb` handles structured-clone serialization.
 */
export interface PendingScan {
  id: string;
  imageBlob: Blob;
  metadata: Record<string, unknown>;
  timestamp: number; // epoch ms
  status: 'pending' | 'syncing';
}

interface AgrosphereOfflineDB extends DBSchema {
  pendingScans: {
    key: string;
    value: PendingScan;
    indexes: { status: string; timestamp: number };
  };
}

const DB_NAME = 'agrosphere-offline';
const DB_VERSION = 1;
const STORE_NAME = 'pendingScans';

let _db: IDBPDatabase<AgrosphereOfflineDB> | null = null;

/**
 * Lazily opens (and caches) the IndexedDB connection.
 * Safe to call multiple times — returns the cached instance.
 */
async function getDB(): Promise<IDBPDatabase<AgrosphereOfflineDB>> {
  if (_db) return _db;

  // `idb`'s openDB wraps native IndexedDB with promise-based, typed access.
  _db = await openDB<AgrosphereOfflineDB>(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        store.createIndex('status', 'status');
        store.createIndex('timestamp', 'timestamp');
      }
    },
    blocked() {
      // Another tab opened a newer version but didn't close.
      console.warn('[offline-db] Database blocked by another tab.');
    },
    blocking() {
      // A newer version is trying to open — we should close.
      if (_db) _db.close();
      _db = null;
    },
  });

  return _db;
}

/**
 * Persists a pending scan to IndexedDB.
 * @returns The ID of the saved scan.
 */
export async function savePendingScan(scan: Omit<PendingScan, 'status'>): Promise<string> {
  const db = await getDB();
  const record: PendingScan = {
    ...scan,
    status: 'pending',
  };
  await db.put(STORE_NAME, record);
  return record.id;
}

/**
 * Fetches all pending scans, ordered by timestamp (ascending).
 */
export async function getPendingScans(): Promise<PendingScan[]> {
  const db = await getDB();
  const tx = db.transaction(STORE_NAME, 'readonly');
  const index = tx.store.index('timestamp');
  return index.getAll();
}

/**
 * Removes a scan from the store by its ID.
 */
export async function deleteScan(id: string): Promise<void> {
  const db = await getDB();
  await db.delete(STORE_NAME, id);
}

/**
 * Updates a scan's status (e.g. to 'syncing' during upload).
 */
export async function updateScanStatus(
  id: string,
  status: PendingScan['status']
): Promise<void> {
  const db = await getDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  const scan = await tx.store.get(id);
  if (scan) {
    scan.status = status;
    await tx.store.put(scan);
  }
  await tx.done;
}
