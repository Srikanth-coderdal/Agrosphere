import { deleteScan, getPendingScans, updateScanStatus, PendingScan } from './db';

const SCAN_ENDPOINT = '/api/scan';
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

/**
 * Serializes a PendingScan into a FormData payload for the POST.
 * Blobs are sent natively — no manual base64 conversion needed.
 */
function buildFormData(scan: PendingScan): FormData {
  const form = new FormData();
  form.append('image', scan.imageBlob, `${scan.id}.jpg`);
  const meta = (scan.metadata || {}) as Record<string, unknown>;
  const cropType = meta.crop_type || meta.cropType || 'General';
  form.append('crop_type', String(cropType));

  if (meta.latitude !== undefined && meta.latitude !== null) {
    form.append('latitude', String(meta.latitude));
  }
  if (meta.longitude !== undefined && meta.longitude !== null) {
    form.append('longitude', String(meta.longitude));
  }
  if (meta.farmer_comment || meta.farmerComment) {
    form.append('farmer_comment', String(meta.farmer_comment || meta.farmerComment));
  }
  if (meta.language) {
    form.append('language', String(meta.language));
  }
  const opContext = meta.operational_context || meta.operationalContext || meta.context_mode || meta.contextMode;
  if (opContext) {
    form.append('operational_context', String(opContext));
    form.append('context_mode', String(opContext));
  }

  form.append('metadata', new Blob([JSON.stringify(scan.metadata)], { type: 'application/json' }));
  form.append('timestamp', String(scan.timestamp));
  return form;
}

/**
 * POSTs a single scan to the backend.
 * @returns `true` if the server acknowledged the scan.
 */
async function uploadScan(scan: PendingScan): Promise<boolean> {
  try {
    const form = buildFormData(scan);
    const res = await fetch(`${API_BASE}${SCAN_ENDPOINT}`, {
      method: 'POST',
      body: form,
    });
    return res.ok;
  } catch {
    // Network-level failure (offline, DNS, CORS-blocking, etc.)
    return false;
  }
}

/**
 * Processes a single scan with exponential-backoff retry.
 * On success, deletes the scan from IndexedDB.
 * On failure after all retries, leaves the scan as 'pending' so it can be retried later.
 */
async function processScan(scan: PendingScan): Promise<void> {
  let attempts = 0;

  while (attempts < MAX_RETRIES) {
    attempts++;

    try {
      const ok = await uploadScan(scan);
      if (ok) {
        await deleteScan(scan.id);
        return;
      }
    } catch {
      // Swallow — uploadScan already catches; this is a safety net.
    }

    if (attempts < MAX_RETRIES) {
      const backoff = RETRY_DELAY_MS * 2 ** (attempts - 1);
      await new Promise((r) => setTimeout(r, backoff));
    }
  }

  // All retries exhausted — ensure status is reset to 'pending'
  await updateScanStatus(scan.id, 'pending').catch(() => {
    /* record may have already been deleted */
  });
}

/**
 * Processes ALL queued scans sequentially.
 * Stops at the first unrecoverable failure (so the queue halts gracefully).
 */
export async function syncQueuedScans(): Promise<{ success: number; failed: number }> {
  const pending = await getPendingScans();
  if (pending.length === 0) {
    return { success: 0, failed: 0 };
  }

  let success = 0;
  let failed = 0;

  for (const scan of pending) {
    // Mark as syncing before upload attempt.
    await updateScanStatus(scan.id, 'syncing').catch(() => {});

    try {
      await processScan(scan);
      success++;
    } catch {
      failed++;
    }
  }

  return { success, failed };
}

/**
 * Attaches a one-time `online` listener to trigger sync when connectivity returns.
 * Call once on app mount.
 */
export function registerOnlineSyncListener(): () => void {
  const handler = () => {
    // Small debounce to let the network settle.
    setTimeout(() => {
      void syncQueuedScans();
    }, 500);
  };

  window.addEventListener('online', handler);

  // Return a cleanup function so callers can deregister if needed.
  return () => {
    window.removeEventListener('online', handler);
  };
}
