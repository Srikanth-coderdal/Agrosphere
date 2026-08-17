"use client";

import { useState } from "react";
import {
  getUrbanGardeningAdvice,
  SpaceType,
  UrbanGardeningRequest,
  UrbanGardeningResponse,
} from "@/app/lib/api";
import { useAuth } from "@/app/lib/useAuth";
import ProtectedRoute from "../components/ProtectedRoute";
import { useLanguage } from "../lib/useLanguage";
import { getMessages } from "../lib/i18n";

/* ── Quick-pick plant chips ─────────────────────────────────────────── */
const PLANT_CHIPS = ["Basil", "Mint", "Tomato", "Lettuce", "Chilli", "Succulent"];

/* ── Space type options ─────────────────────────────────────────────── */
const SPACE_OPTIONS: { value: SpaceType; label: string; icon: string }[] = [
  { value: "balcony",  label: "Balcony",  icon: "🏠" },
  { value: "indoor",   label: "Indoor",   icon: "🪴" },
  { value: "rooftop",  label: "Rooftop",  icon: "🏙️" },
];

/* ── Shared styles ──────────────────────────────────────────────────── */
const inputCls =
  "w-full rounded-xl border border-emerald-200 bg-white px-4 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-emerald-500 focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50";
const labelCls = "block text-xs font-semibold uppercase tracking-wide mb-1.5";

/* ── Info card ──────────────────────────────────────────────────────── */
interface InfoCardProps {
  icon: string;
  title: string;
  content: string;
  accentColor?: string;
}

function InfoCard({ icon, title, content, accentColor = "var(--primary)" }: InfoCardProps) {
  return (
    <div
      className="flex flex-col gap-2 rounded-2xl border p-5 shadow-sm transition-shadow hover:shadow-md bg-white"
      style={{
        borderColor: `color-mix(in srgb,${accentColor} 20%,transparent)`,
      }}
    >
      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide" style={{ color: accentColor }}>
        <span aria-hidden="true">{icon}</span>
        {title}
      </p>
      <p className="text-sm leading-relaxed text-slate-800 font-medium">
        {content}
      </p>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────── */
export default function UrbanGardeningPage() {
  const { token } = useAuth();
  const { language } = useLanguage();
  const msg = getMessages(language);

  const [plantType, setPlantType] = useState("");
  const [spaceType, setSpaceType] = useState<SpaceType>("balcony");
  const [sunlightHours, setSunlightHours] = useState(6);
  const [containerSize, setContainerSize] = useState(10);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UrbanGardeningResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!plantType.trim()) {
      setError("Please enter a plant type.");
      return;
    }
    if (containerSize <= 0) {
      setError("Container size must be greater than 0.");
      return;
    }
    setError(null);
    setResult(null);
    setIsLoading(true);
    try {
      const payload: UrbanGardeningRequest = {
        plant_type: plantType.trim(),
        space_type: spaceType,
        sunlight_hours: sunlightHours,
        container_size: containerSize,
      };
      const data = await getUrbanGardeningAdvice(payload, token, language);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get advice. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ProtectedRoute>
      <div className="flex flex-col gap-10">
      {/* ── Header ── */}
      <section className="flex flex-col gap-2">
        <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl" style={{ color: "var(--primary)" }}>
          🏙️ {msg.urban.title}
        </h1>
        <p className="max-w-2xl text-base leading-relaxed" style={{ color: "var(--foreground)", opacity: 0.65 }}>
          Tell us about your urban space and chosen plant. Our AI will generate a personalised
          care schedule, watering plan, and expert growing tips — perfect for balconies, rooftops,
          and indoor setups.
        </p>
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* ── Left: Form ── */}
        <section>
          <form
            id="urban-form"
            onSubmit={handleSubmit}
            noValidate
            className="flex flex-col gap-5 rounded-2xl border p-6 shadow-sm"
            style={{
              borderColor: "color-mix(in srgb,var(--primary) 20%,transparent)",
              background: "color-mix(in srgb,var(--primary) 3%,white)",
            }}
          >
            {/* Plant type */}
            <div>
              <label htmlFor="plant-type" className={labelCls} style={{ color: "var(--primary)" }}>
                {msg.urban.plantType}
              </label>
              {/* Quick-pick chips */}
              <div className="mb-2 flex flex-wrap gap-1.5">
                {PLANT_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    onClick={() => { setPlantType(chip); if (result) setResult(null); }}
                    className="rounded-full px-3 py-1 text-xs font-semibold transition-colors"
                    style={
                      plantType === chip
                        ? { background: "var(--primary)", color: "#fff" }
                        : {
                            background: "color-mix(in srgb,var(--primary) 10%,transparent)",
                            color: "var(--primary)",
                          }
                    }
                    aria-pressed={plantType === chip}
                  >
                    {chip}
                  </button>
                ))}
              </div>
              <input
                id="plant-type"
                type="text"
                placeholder="Or type any plant name…"
                value={plantType}
                onChange={(e) => { setPlantType(e.target.value); if (result) setResult(null); }}
                disabled={isLoading}
                className={inputCls}
                style={{ color: "var(--foreground)" }}
              />
            </div>

            {/* Space type */}
            <div>
              <p className={labelCls} style={{ color: "var(--primary)" }}>{msg.urban.spaceType}</p>
              <div className="grid grid-cols-3 gap-2" role="group" aria-label="Space type">
                {SPACE_OPTIONS.map(({ value, label, icon }) => (
                  <button
                    key={value}
                    type="button"
                    id={`space-${value}`}
                    onClick={() => { setSpaceType(value); if (result) setResult(null); }}
                    disabled={isLoading}
                    aria-pressed={spaceType === value}
                    className="flex flex-col items-center gap-1 rounded-xl border py-3 text-sm font-semibold transition-all"
                    style={
                      spaceType === value
                        ? { background: "var(--primary)", borderColor: "var(--primary)", color: "#fff" }
                        : {
                            borderColor: "color-mix(in srgb,var(--primary) 25%,transparent)",
                            color: "var(--foreground)",
                          }
                    }
                  >
                    <span className="text-xl" aria-hidden="true">{icon}</span>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Sunlight slider */}
            <div>
              <label htmlFor="sunlight-hours" className={labelCls} style={{ color: "var(--primary)" }}>
                {msg.urban.dailySunlight(sunlightHours)}
              </label>
              <div className="flex items-center gap-3">
                <span className="text-xs opacity-50">0</span>
                <input
                  id="sunlight-hours"
                  type="range"
                  min={0}
                  max={14}
                  step={0.5}
                  value={sunlightHours}
                  onChange={(e) => { setSunlightHours(parseFloat(e.target.value)); if (result) setResult(null); }}
                  disabled={isLoading}
                  className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-emerald-100 accent-emerald-600 disabled:cursor-not-allowed"
                  aria-valuenow={sunlightHours}
                  aria-valuemin={0}
                  aria-valuemax={14}
                />
                <span className="text-xs opacity-50">14</span>
                <span
                  className="w-14 rounded-lg px-2 py-1 text-center text-xs font-bold tabular-nums"
                  style={{ background: "color-mix(in srgb,var(--primary) 15%,transparent)", color: "var(--primary)" }}
                >
                  {sunlightHours} hrs
                </span>
              </div>
            </div>

            {/* Container size */}
            <div>
              <label htmlFor="container-size" className={labelCls} style={{ color: "var(--primary)" }}>
                {msg.urban.containerSize}
              </label>
              <input
                id="container-size"
                type="number"
                min={0.5}
                step={0.5}
                value={containerSize}
                onChange={(e) => { setContainerSize(parseFloat(e.target.value) || 0); if (result) setResult(null); }}
                disabled={isLoading}
                className={inputCls}
                style={{ color: "var(--foreground)" }}
              />
            </div>

            {/* Error */}
            {error && (
              <p
                role="alert"
                className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium"
                style={{ background: "color-mix(in srgb,#ef4444 10%,transparent)", color: "#b91c1c" }}
              >
                ⚠️ {error}
              </p>
            )}

            {/* Submit */}
            <button
              id="urban-submit-btn"
              type="submit"
              disabled={isLoading}
              aria-busy={isLoading}
              className="flex w-full items-center justify-center gap-2.5 rounded-2xl px-6 py-4 text-base font-bold text-white shadow-lg transition-all duration-200 hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: "linear-gradient(135deg,var(--primary),var(--primary-dk))" }}
            >
              {isLoading ? (
                <>
                  <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  {msg.urban.loading}
                </>
              ) : (
                <>
                  <span aria-hidden="true">🪴</span>
                  {msg.urban.submitBtn}
                </>
              )}
            </button>
          </form>
        </section>

        {/* ── Right: Results ── */}
        <section aria-live="polite" aria-label="Gardening advice results" className="flex flex-col gap-4">
          {!result && !isLoading && (
            <div
              className="flex h-full min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-10 text-center"
              style={{
                borderColor: "color-mix(in srgb,var(--primary) 20%,transparent)",
                background: "color-mix(in srgb,var(--primary) 3%,transparent)",
              }}
            >
              <span className="text-5xl" aria-hidden="true">🌿</span>
              <p className="text-sm font-medium" style={{ color: "var(--foreground)", opacity: 0.45 }}>
                Personalised gardening advice will appear here.
              </p>
            </div>
          )}

          {isLoading && (
            <div className="flex h-full min-h-64 flex-col items-center justify-center gap-4 rounded-2xl">
              <div
                className="h-14 w-14 animate-spin rounded-full border-4"
                style={{ borderColor: "var(--primary)", borderTopColor: "transparent" }}
                aria-hidden="true"
              />
              <p className="text-sm font-semibold" style={{ color: "var(--primary)" }}>
                AI is crafting your care plan…
              </p>
            </div>
          )}

          {result && (
            <div className="flex flex-col gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <InfoCard icon="📅" title={msg.urban.infoCareSchedule}          content={result.care_schedule}             accentColor="var(--primary)" />
                <InfoCard icon="💧" title={msg.urban.infoWateringFrequency}     content={result.watering_frequency}        accentColor="#0891b2" />
                <InfoCard icon="☀️" title={msg.urban.infoSunlightRecommendations} content={result.sunlight_recommendations} accentColor="#d97706" />
                <InfoCard icon="🌱" title={msg.urban.infoSoilMix}               content={result.soil_mix}                  accentColor="#16a34a" />
              </div>

              {/* Actionable tips — full width */}
              {result.actionable_tips.length > 0 && (
                <div
                  className="flex flex-col gap-3 rounded-2xl border p-5 shadow-sm"
                  style={{
                    borderColor: "color-mix(in srgb,var(--earthy) 25%,transparent)",
                    background: "color-mix(in srgb,var(--earthy) 5%,white)",
                  }}
                >
                  <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide" style={{ color: "var(--earthy)" }}>
                    <span aria-hidden="true">💡</span>
                    {msg.urban.actionableTips}
                  </p>
                  <ul className="flex flex-col gap-2" role="list">
                    {result.actionable_tips.map((tip, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm leading-snug text-slate-800 font-medium">
                        <span
                          className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] text-white"
                          style={{ background: "var(--earthy)" }}
                          aria-hidden="true"
                        >
                          ✓
                        </span>
                        {tip}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
      </div>
    </ProtectedRoute>
  );
}
