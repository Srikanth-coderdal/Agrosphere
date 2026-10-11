import { useEffect, useState, useCallback } from 'react';
import {
  getQueuedScans,
  removeQueuedScan,
  flushQueue,
  registerOnlineSyncListener,
  OFFLINE_QUEUE_EVENT,
} from '@/lib/syncManager';

/**
 * React hook that exposes offline-sync state and controls to UI components,
 * backed by the unified IndexedDB store (AgroSphereOffline / scans).
 */
export interface OfflineSyncState {
  isOnline: boolean;
  pendingCount: number;
  isSyncing: boolean;
  lastSyncResult: { success: number; failed: number } | null;
}

export interface OfflineSyncActions {
  triggerSync: () => Promise<void>;
  deleteScan: (id: number | string) => Promise<void>;
  refreshCount: () => Promise<void>;
}

export type UseOfflineSyncReturn = OfflineSyncState & OfflineSyncActions;

export function useOfflineSync(): UseOfflineSyncReturn {
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof window !== 'undefined' ? navigator.onLine : true
  );
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [lastSyncResult, setLastSyncResult] = useState<{ success: number; failed: number } | null>(
    null
  );

  // ── Helper: fetch current pending count from AgroSphereOffline / scans ──
  const refreshCount = useCallback(async () => {
    try {
      const scans = await getQueuedScans();
      setPendingCount(scans.length);
    } catch (err) {
      console.error('[useOfflineSync] Failed to count pending scans:', err);
    }
  }, []);

  // ── Helper: delete a scan (useful for UI "discard" buttons) ──────
  const handleDeleteScan = useCallback(async (id: number | string) => {
    try {
      await removeQueuedScan(Number(id));
      await refreshCount();
    } catch (err) {
      console.error('[useOfflineSync] Failed to delete scan:', err);
    }
  }, [refreshCount]);

  // ── Helper: trigger a manual sync ─────────────────────────────────
  const triggerSync = useCallback(async () => {
    if (isSyncing) return;

    setIsSyncing(true);
    try {
      const result = await flushQueue();
      setLastSyncResult(result);
      await refreshCount();
    } catch (err) {
      console.error('[useOfflineSync] Sync failed:', err);
      setLastSyncResult({ success: 0, failed: 0 });
    } finally {
      setIsSyncing(false);
    }
  }, [isSyncing, refreshCount]);

  // ── Network & queue-change listeners ──────────────────────────────
  useEffect(() => {
    const goOnline = () => {
      setIsOnline(true);
      setTimeout(() => {
        void flushQueue().then(() => refreshCount());
      }, 500);
    };

    const goOffline = () => setIsOnline(false);

    const onQueueChanged = () => {
      void refreshCount();
    };

    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    window.addEventListener(OFFLINE_QUEUE_EVENT, onQueueChanged);

    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
      window.removeEventListener(OFFLINE_QUEUE_EVENT, onQueueChanged);
    };
  }, [refreshCount]);

  // ── Register background sync listener (one-time) ──────────────────
  useEffect(() => {
    const cleanup = registerOnlineSyncListener();
    return cleanup;
  }, []);

  // ── Auto-refresh count on mount ───────────────────────────────────
  useEffect(() => {
    void refreshCount();
  }, [refreshCount]);

  return {
    // State
    isOnline,
    pendingCount,
    isSyncing,
    lastSyncResult,

    // Actions
    triggerSync,
    deleteScan: handleDeleteScan,
    refreshCount,
  };
}
