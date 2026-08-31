"use client";

import { useState } from "react";
import ImageUploader from "../components/ImageUploader";
import ProtectedRoute from "../components/ProtectedRoute";
import useProfileStore from "@/store/useProfileStore";
import { getMessages } from "../lib/i18n";
import { scanCropImage, ScanResponse, SafeDosage } from "@/app/lib/api";
import { queueOfflineScan } from "@/lib/syncManager";

/* ── Local display type (confidence_score normalised to 0–100) ───────── */
type HealthStatus =
  | "Diseased / Infected"
  | "Normal / Healthy"
  | "Physically Damaged"
  | "Environmental Hazard"
  | "Unclear";

interface DisplayResult {
  health_status: HealthStatus;
  disease_name: string;
  confidence_score: number; // 0–100 (converted from API's 0–1)
  verified_treatment: string;
  safe_dosages: SafeDosage[];
  organic_recommendations: string[];
  preventive_measures: string[];
  disclaimer: string;
  is_verified: boolean;
  weather_summary?: {
    temperature: string;
    rain_chance: string;
    spray_advisory: string;
  } | null;
}

/** Convert a raw API ScanResponse into the display format used by this page. */
function toDisplayResult(raw: ScanResponse): DisplayResult {
  const isHealthy = raw.pathogen.toLowerCase().includes("healthy") || raw.pathogen.toLowerCase().includes("normal");
  return {
    health_status: isHealthy ? "Normal / Healthy" : "Diseased / Infected",
    disease_name: raw.pathogen,
    // API returns 0.0–1.0; render as 0–100
    confidence_score: Math.round(raw.confidence * 100),
    verified_treatment: raw.verified_treatment,
    safe_dosages: raw.safe_dosages || [],
    organic_recommendations: raw.organic_recommendations || [],
    preventive_measures: raw.preventive_measures || [],
    disclaimer: raw.disclaimer,
    is_verified: raw.is_verified,
    weather_summary: raw.weather_summary,
  };
}

/* ── Badge config ───────────────────────────────────────────────────── */
const STATUS_BADGE: Record<
  HealthStatus,
  { label: string; bg: string; color: string; icon: string }
> = {
  "Diseased / Infected": {
    label: "Diseased / Infected",
    bg: "color-mix(in srgb,#ef4444 12%,transparent)",
    color: "#b91c1c",
    icon: "🚨",
  },
  "Normal / Healthy": {
    label: "Normal / Healthy",
    bg: "color-mix(in srgb,#22c55e 12%,transparent)",
    color: "#15803d",
    icon: "✅",
  },
  "Physically Damaged": {
    label: "Physically Damaged",
    bg: "color-mix(in srgb,#f97316 12%,transparent)",
    color: "#c2410c",
    icon: "🔧",
  },
  "Environmental Hazard": {
    label: "Environmental Hazard",
    bg: "color-mix(in srgb,#eab308 12%,transparent)",
    color: "#a16207",
    icon: "⚡",
  },
  Unclear: {
    label: "Unclear",
    bg: "color-mix(in srgb,#64748b 12%,transparent)",
    color: "#334155",
    icon: "❓",
  },
};

/* ── Confidence bar colour ──────────────────────────────────────────── */
function confidenceColor(score: number): string {
  if (score >= 80) return "#059669";
  if (score >= 55) return "#d97706";
  return "#ef4444";
}

/* ── Remedy card ────────────────────────────────────────────────────── */
interface RemedyCardProps {
  icon: string;
  title: string;
  items: string[];
  accentColor?: string;
}

function RemedyCard({ icon, title, items, accentColor = "var(--primary)" }: RemedyCardProps) {
  return (
    <div
      className="flex flex-col gap-3 rounded-2xl border p-5 shadow-sm transition-shadow hover:shadow-md bg-white"
      style={{
        borderColor: "color-mix(in srgb, var(--primary) 20%, transparent)",
      }}
    >
      <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide" style={{ color: accentColor }}>
        <span aria-hidden="true">{icon}</span>
        {title}
      </h3>
      <ul className="flex flex-col gap-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm leading-snug text-slate-800 font-medium">
            <span
              className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: accentColor }}
              aria-hidden="true"
            />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────── */
export default function ScanPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [farmerComment, setFarmerComment] = useState("");
  const [geoLat, setGeoLat] = useState<number | undefined>(undefined);
  const [geoLng, setGeoLng] = useState<number | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<DisplayResult | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const { language, profileMode } = useProfileStore();
  const msg = getMessages(language);

  /* ── Uploader callback ── */
  const handleSelect = (file: File | null, comment: string, latitude?: number, longitude?: number) => {
    setSelectedFile(file);
    setFarmerComment(comment);
    setGeoLat(latitude);
    setGeoLng(longitude);
    if (scanResult) setScanResult(null);
    if (error) setError(null);
    if (successMessage) setSuccessMessage(null);
  };

  /* ── Live scan handler ── */
  const handleScan = async () => {
    if (!selectedFile) {
      setError("Please upload a crop or farm image before scanning.");
      return;
    }
    setError(null);
    setSuccessMessage(null);
    setScanResult(null);
    setIsLoading(true);

    const operationalContext = profileMode === "URBAN_GARDEN" ? "Urban" : "Commercial";
    const payload = {
      image: selectedFile,
      imageBlob: selectedFile,
      cropType: "General",
      latitude: geoLat,
      longitude: geoLng,
      farmerComment: farmerComment,
      language: language,
      operationalContext: operationalContext,
    };

    if (typeof navigator !== "undefined" && !navigator.onLine) {
      try {
        await queueOfflineScan(payload);
        setSuccessMessage("📡 You are offline. Scan saved to queue and will auto-sync when connected.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to queue offline scan.");
      } finally {
        setIsLoading(false);
      }
      return;
    }

    try {
      const raw = await scanCropImage(
        selectedFile,
        "General",
        geoLat,
        geoLng,
        farmerComment,
        language,
        operationalContext
      );
      setScanResult(toDisplayResult(raw));
    } catch (err) {
      try {
        await queueOfflineScan(payload);
        setSuccessMessage("📡 You are offline. Scan saved to queue and will auto-sync when connected.");
      } catch (queueErr) {
        setError(
          err instanceof Error
            ? err.message
            : "Scan failed. Please try again."
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  const badge = scanResult ? STATUS_BADGE[scanResult.health_status] : null;

  return (
    <ProtectedRoute>
      <div className="flex flex-col gap-10">
      {/* ── Page header ── */}
      <section className="flex flex-col gap-2">
        <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl" style={{ color: "var(--primary)" }}>
          🔍 {msg.scan.title}
        </h1>
        <p className="max-w-2xl text-base leading-relaxed" style={{ color: "var(--foreground)", opacity: 0.65 }}>
          Upload a clear photo of a leaf, plant part, or any farm subject. Our AI analyzes
          disease &amp; pests, beneficial ecology, physical damage, and environmental hazards —
          then suggests a practical action plan.
        </p>
      </section>

      {/* ── Main grid ── */}
      <div className="grid gap-8 lg:grid-cols-2">
        {/* ── Left: Upload + action ── */}
        <section className="flex flex-col gap-5">
          <ImageUploader onSelect={handleSelect} disabled={isLoading} />

          {/* Error */}
          {error && (
            <p
              role="alert"
              className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium"
              style={{
                background: "color-mix(in srgb,#ef4444 10%,transparent)",
                color: "#b91c1c",
              }}
            >
              ⚠️ {error}
            </p>
          )}

          {/* Success / Offline Queue Message */}
          {successMessage && (
            <p
              role="status"
              className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium"
              style={{
                background: "color-mix(in srgb,#10b981 10%,transparent)",
                color: "#047857",
              }}
            >
              {successMessage}
            </p>
          )}

          {/* Analyze button */}
          <button
            id="analyze-btn"
            type="button"
            onClick={handleScan}
            disabled={!selectedFile || isLoading}
            className="flex w-full items-center justify-center gap-2.5 rounded-2xl px-6 py-4 text-base font-bold text-white shadow-lg transition-all duration-200 hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: "linear-gradient(135deg,var(--primary),var(--primary-dk))" }}
            aria-busy={isLoading}
          >
            {isLoading ? (
              <>
                {/* Spinner */}
                <svg
                  className="h-5 w-5 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                Analyzing Leaf Sample…
              </>
            ) : (
              <>
                <span aria-hidden="true">🧬</span>
                {msg.scan.analyzeBtn}
              </>
            )}
          </button>
        </section>

        {/* ── Right: Results ── */}
        <section aria-live="polite" aria-label="Scan results">
          {!scanResult && !isLoading && (
            <div
              className="flex h-full min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-10 text-center"
              style={{
                borderColor: "color-mix(in srgb,var(--primary) 20%,transparent)",
                background: "color-mix(in srgb,var(--primary) 3%,transparent)",
              }}
            >
              <span className="text-5xl" aria-hidden="true">🌿</span>
              <p className="text-sm font-medium" style={{ color: "var(--foreground)", opacity: 0.45 }}>
                Diagnosis results will appear here after scanning.
              </p>
            </div>
          )}

          {isLoading && (
            <div className="flex h-full min-h-48 flex-col items-center justify-center gap-4 rounded-2xl p-10">
              <div
                className="h-14 w-14 animate-spin rounded-full border-4 border-t-transparent"
                style={{ borderColor: "var(--primary)", borderTopColor: "transparent" }}
                aria-hidden="true"
              />
              <p className="text-sm font-semibold" style={{ color: "var(--primary)" }}>
                AI is analyzing your crop image…
              </p>
            </div>
          )}

          {scanResult && badge && (
            <div className="flex flex-col gap-5">
              {/* ── Status badge ── */}
              <div className="flex items-center justify-between rounded-2xl border px-5 py-4 shadow-sm"
                style={{ borderColor: badge.color + "33", background: badge.bg }}>
                <div className="flex flex-col gap-0.5">
                  <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: badge.color, opacity: 0.7 }}>
                    {msg.scan.healthStatus}
                  </span>
                  <span className="text-xl font-extrabold" style={{ color: badge.color }}>
                    {badge.icon} {badge.label}
                  </span>
                </div>
                <span
                  className="rounded-xl px-3 py-1.5 text-sm font-bold"
                  style={{ background: badge.color, color: "#fff" }}
                >
                  {scanResult.confidence_score}% confident
                </span>
              </div>

              {/* ── Disease name + confidence bar ── */}
              <div className="flex flex-col gap-2 rounded-2xl border px-5 py-4 shadow-sm bg-white"
                style={{ borderColor: "color-mix(in srgb,var(--primary) 15%,transparent)" }}>
                <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--primary)", opacity: 0.7 }}>
                  {msg.scan.identifiedCondition}
                </p>
                <p className="text-lg font-bold leading-snug text-slate-900">
                  {scanResult.disease_name}
                </p>
                {/* Confidence bar */}
                <div className="mt-1 flex items-center gap-3">
                  <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-slate-200">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${scanResult.confidence_score}%`,
                        background: confidenceColor(scanResult.confidence_score),
                      }}
                      role="progressbar"
                      aria-valuenow={scanResult.confidence_score}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`Confidence score: ${scanResult.confidence_score}%`}
                    />
                  </div>
                  <span className="w-10 text-right text-xs font-bold tabular-nums"
                    style={{ color: confidenceColor(scanResult.confidence_score) }}>
                    {scanResult.confidence_score}%
                  </span>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* ── Remedy grid (full width below) ── */}
      {scanResult && (
        <section aria-label="Remedy and action plan" className="flex flex-col gap-4">
          <h2 className="text-xl font-bold" style={{ color: "var(--foreground)" }}>
            📋 {msg.scan.actionPlanTitle}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <RemedyCard
              icon="📋"
              title="Verified Treatment"
              items={[scanResult.verified_treatment]}
              accentColor="#059669"
            />
            <RemedyCard
              icon="🧪"
              title={msg.scan.organicRemedies}
              items={scanResult.organic_recommendations}
              accentColor="#16a34a"
            />
            <RemedyCard
              icon="💊"
              title="Safe Dosages"
              items={scanResult.safe_dosages.map(d => `${d.chemical_name}: ${d.dosage} ${d.unit} (Max: ${d.max_frequency}, PHI: ${d.pre_harvest_interval_days} days)`)}
              accentColor="#d97706"
            />
            <RemedyCard
              icon="🛡️"
              title={msg.scan.preventiveMeasures}
              items={scanResult.preventive_measures}
              accentColor="#0891b2"
            />
          </div>

          {/* ── Weather & Spray Advisory Card ── */}
          {scanResult.weather_summary && (
            <div className="rounded-2xl border border-sky-200 bg-gradient-to-br from-sky-50/80 via-blue-50/40 to-white p-5 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-sky-100 pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl" aria-hidden="true">🌦️</span>
                  <h3 className="text-sm font-bold uppercase tracking-wide text-sky-900">
                    Weather &amp; Spray Advisory
                  </h3>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs font-semibold">
                  <span className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-slate-700 shadow-xs border border-sky-100">
                    🌡️ Temperature: <strong className="text-slate-900">{scanResult.weather_summary.temperature}</strong>
                  </span>
                  <span className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-slate-700 shadow-xs border border-sky-100">
                    🌧️ Rain Risk: <strong className="text-slate-900">{scanResult.weather_summary.rain_chance}</strong>
                  </span>
                </div>
              </div>
              <div className="mt-3 flex items-start gap-2.5">
                <span className="text-base shrink-0 mt-0.5" aria-hidden="true">📢</span>
                <p className="text-sm font-medium leading-relaxed text-slate-800">
                  {scanResult.weather_summary.spray_advisory}
                </p>
              </div>
            </div>
          )}

          {scanResult.disclaimer && (
            <div className="mt-2 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              <strong>Disclaimer: </strong>
              {scanResult.disclaimer}
            </div>
          )}
        </section>
      )}
      </div>
    </ProtectedRoute>
  );
}
