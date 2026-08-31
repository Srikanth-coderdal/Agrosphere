"use client";

import { useState, useEffect, useCallback, useRef } from "react";

/* ── Types ──────────────────────────────────────────────────────────── */
interface GeoCoordinates {
  lat: number;
  lng: number;
}

interface UseLocationReturn {
  location: GeoCoordinates | null;
  loading: boolean;
  error: string | null;
  refetchLocation: () => void;
}

/* ── Tamil Nadu baseline fallback ───────────────────────────────────── */
const FALLBACK_COORDS: GeoCoordinates = { lat: 13.0827, lng: 80.2707 };

/** Timeout (ms) for the geolocation request. */
const GEO_TIMEOUT_MS = 8_000;

/* ── Human-readable error from GeolocationPositionError codes ─────── */
function geoErrorMessage(code: number): string {
  switch (code) {
    case 1:
      return "Location permission denied. Using default coordinates.";
    case 2:
      return "Location information unavailable. Using default coordinates.";
    case 3:
      return "Location request timed out. Using default coordinates.";
    default:
      return "Unable to retrieve location. Using default coordinates.";
  }
}

/* ── Hook ───────────────────────────────────────────────────────────── */
export function useLocation(): UseLocationReturn {
  const [location, setLocation] = useState<GeoCoordinates | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const watchIdRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  const fetchLocation = useCallback(() => {
    /* Guard: no geolocation API → fallback immediately */
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setLocation(FALLBACK_COORDS);
      setError("Geolocation is not supported by this browser. Using default coordinates.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    /* Race getCurrentPosition against an 8-second timeout */
    let settled = false;

    const timeoutId = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        if (mountedRef.current) {
          setLocation(FALLBACK_COORDS);
          setError("Location request timed out. Using default coordinates.");
          setLoading(false);
        }
      }
    }, GEO_TIMEOUT_MS);

    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (!settled) {
          settled = true;
          window.clearTimeout(timeoutId);
          if (mountedRef.current) {
            setLocation({
              lat: position.coords.latitude,
              lng: position.coords.longitude,
            });
            setError(null);
            setLoading(false);
          }
        }
      },
      (positionError) => {
        if (!settled) {
          settled = true;
          window.clearTimeout(timeoutId);
          if (mountedRef.current) {
            setLocation(FALLBACK_COORDS);
            setError(geoErrorMessage(positionError.code));
            setLoading(false);
          }
        }
      },
      {
        enableHighAccuracy: true,
        timeout: GEO_TIMEOUT_MS,
        maximumAge: 60_000,
      },
    );
  }, []);

  /* Initial fetch on mount */
  useEffect(() => {
    mountedRef.current = true;
    fetchLocation();

    return () => {
      mountedRef.current = false;
      /* Clean up any active watcher */
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
    };
  }, [fetchLocation]);

  return { location, loading, error, refetchLocation: fetchLocation };
}

export default useLocation;
