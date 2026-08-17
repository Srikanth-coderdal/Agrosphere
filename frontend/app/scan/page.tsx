"use client";

import { useState } from "react";
import ImageUploader from "../components/ImageUploader";
import ProtectedRoute from "../components/ProtectedRoute";
import { useLanguage } from "../lib/useLanguage";
import { getMessages } from "../lib/i18n";
import { scanCropImage, ScanResponse } from "@/app/lib/api";

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
  visible_symptoms: string[];
  organic_remedies: string[];
  chemical_remedies: string[];
  preventive_measures: string[];
}

/** Convert a raw API ScanResponse into the display format used by this page. */
function toDisplayResult(raw: ScanResponse): DisplayResult {
  return {
    health_status: raw.status,
    disease_name: raw.disease_name,
    // API returns 0.0–1.0; render as 0–100
    confidence_score: Math.round(raw.confidence_score * 100),
    visible_symptoms: raw.visible_symptoms,
    organic_remedies: raw.organic_remedies,
    chemical_remedies: raw.chemical_remedies,
    preventive_measures: raw.preventive_measures,
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
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<DisplayResult | null>(null);
  const { language } = useLanguage();
  const msg = getMessages(language);

  /* ── Uploader callback ── */
  const handleSelect = (file: File | null, comment: string) => {
    setSelectedFile(file);
    setFarmerComment(comment);
    if (scanResult) setScanResult(null);
    if (error) setError(null);
  };

  /* ── Live scan handler ── */
  const handleScan = async () => {
    if (!selectedFile) {
      setError("Please upload a crop or farm image before scanning.");
      return;
    }
    setError(null);
    setScanResult(null);
    setIsLoading(true);
    try {
      const raw = await scanCropImage(selectedFile, farmerComment, language);
      setScanResult(toDisplayResult(raw));
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Scan failed. Please try again."
      );
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
              icon="🍃"
              title={msg.scan.visibleSymptoms}
              items={scanResult.visible_symptoms}
              accentColor="#059669"
            />
            <RemedyCard
              icon="🧪"
              title={msg.scan.organicRemedies}
              items={scanResult.organic_remedies}
              accentColor="#16a34a"
            />
            <RemedyCard
              icon="💊"
              title={msg.scan.chemicalRemedies}
              items={scanResult.chemical_remedies}
              accentColor="#d97706"
            />
            <RemedyCard
              icon="🛡️"
              title={msg.scan.preventiveMeasures}
              items={scanResult.preventive_measures}
              accentColor="#0891b2"
            />
          </div>
        </section>
      )}
      </div>
    </ProtectedRoute>
  );
}
