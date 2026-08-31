import { useEffect, useState, useCallback } from 'react';
import { getPendingScans, deleteScan } from '@/lib/offline/db';
import { syncQueuedScans, registerOnlineSyncListener } from '@/lib/offline/syncManager';
import { flushQueue } from '@/lib/syncManager';

/**
 * React hook that exposes offline-sync state and controls to UI components.
 */
export interface OfflineSyncState {
  isOnline: boolean;
  pendingCount: number;
  isSyncing: boolean;
  lastSyncResult: { success: number; failed: number } | null;
}

export interface OfflineSyncActions {
  triggerSync: () => Promise<void>;
  deleteScan: (id: string) => Promise<void>;
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

  // ── Helper: fetch current pending count ──────────────────────────
  const refreshCount = useCallback(async () => {
    try {
      const scans = await getPendingScans();
      setPendingCount(scans.length);
    } catch (err) {
      console.error('[useOfflineSync] Failed to count pending scans:', err);
    }
  }, []);

  // ── Helper: delete a scan (useful for UI "discard" buttons) ──────
  const handleDeleteScan = useCallback(async (id: string) => {
    try {
      await deleteScan(id);
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

  // ── Network status listeners ──────────────────────────────────────
  useEffect(() => {
    const goOnline = () => {
      setIsOnline(true);
      // Trigger sync shortly after coming back online.
      setTimeout(() => {
        void flushQueue().then(() => refreshCount());
      }, 500);
    };

    const goOffline = () => setIsOnline(false);

    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);

    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  // ── Register background sync listener (one-time) ──────────────────
  useEffect(() => {
    // Using the db-level `online` listener as well, for redundancy with
    // React's own network listener.
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
