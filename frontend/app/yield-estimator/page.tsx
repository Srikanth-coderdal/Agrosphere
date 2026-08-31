"use client";

import { useState } from "react";
import {
  predictYield,
  IrrigationType,
  WeatherCondition,
  YieldEstimatorRequest,
  YieldEstimatorResponse,
  YieldSoilType,
} from "@/app/lib/api";
import { useAuth } from "@/app/lib/useAuth";
import ProtectedRoute from "../components/ProtectedRoute";
import useProfileStore from "@/store/useProfileStore";
import { getMessages } from "../lib/i18n";

/* ── Option lists ───────────────────────────────────────────────────── */
const CROP_CHIPS = ["Wheat", "Rice", "Tomato", "Maize", "Potato", "Sugarcane"];

const SOIL_OPTIONS: { value: YieldSoilType; label: string }[] = [
  { value: "clay",   label: "Clay" },
  { value: "sandy",  label: "Sandy" },
  { value: "loam",   label: "Loam" },
  { value: "silty",  label: "Silty" },
  { value: "chalky", label: "Chalky" },
  { value: "peaty",  label: "Peaty" },
];

const IRRIGATION_OPTIONS: { value: IrrigationType; label: string; icon: string }[] = [
  { value: "drip",       label: "Drip",       icon: "💧" },
  { value: "sprinkler",  label: "Sprinkler",  icon: "🚿" },
  { value: "flood",      label: "Flood",      icon: "🌊" },
  { value: "rainfed",    label: "Rainfed",    icon: "🌧️" },
];

const WEATHER_OPTIONS: { value: WeatherCondition; label: string; icon: string }[] = [
  { value: "optimal",    label: "Optimal",     icon: "☀️" },
  { value: "moderate",   label: "Moderate",    icon: "⛅" },
  { value: "drought",    label: "Drought",     icon: "🏜️" },
  { value: "heavy_rain", label: "Heavy Rain",  icon: "🌧️" },
];

/* ── Shared styles ──────────────────────────────────────────────────── */
const inputCls =
  "w-full rounded-xl border border-emerald-200 bg-white px-4 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-emerald-500 focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50";
const labelCls = "block text-xs font-semibold uppercase tracking-wide mb-1.5";

/* ── Toggle button group ────────────────────────────────────────────── */
interface ToggleGroupProps<T extends string> {
  options: { value: T; label: string; icon: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
  groupLabel: string;
}

function ToggleGroup<T extends string>({
  options, value, onChange, disabled, groupLabel,
}: ToggleGroupProps<T>) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={groupLabel}>
      {options.map(({ value: v, label, icon }) => {
        const isSelected = value === v;
        return (
          <button
            key={v}
            type="button"
            id={`toggle-${v}`}
            onClick={() => onChange(v)}
            disabled={disabled}
            aria-pressed={isSelected}
            className={`flex items-center gap-1.5 rounded-full border px-4 py-2 text-xs font-bold transition-all shadow-sm ${
              isSelected
                ? "bg-emerald-600 border-emerald-600 text-white"
                : "bg-slate-100 border-slate-300 text-slate-800 hover:bg-slate-200"
            }`}
          >
            <span className="text-sm" aria-hidden="true">{icon}</span>
            <span className={isSelected ? "text-white font-bold" : "text-slate-800 font-bold"}>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────── */
export default function YieldEstimatorPage() {
  const { token } = useAuth();
  const { language } = useProfileStore();
  const msg = getMessages(language);

  const [cropType, setCropType] = useState("");
  const [fieldSize, setFieldSize] = useState(1.0);
  const [soilType, setSoilType] = useState<YieldSoilType>("loam");
  const [historicalYield, setHistoricalYield] = useState(0);
  const [irrigationType, setIrrigationType] = useState<IrrigationType>("drip");
  const [weatherCondition, setWeatherCondition] = useState<WeatherCondition>("optimal");

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<YieldEstimatorResponse | null>(null);

  const resetResult = () => { if (result) setResult(null); if (error) setError(null); };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cropType.trim()) { setError("Please enter or select a crop type."); return; }
    if (fieldSize <= 0) { setError("Field size must be greater than 0."); return; }
    setError(null);
    setResult(null);
    setIsLoading(true);
    try {
      const payload: YieldEstimatorRequest = {
        crop_type: cropType.trim(),
        field_size_hectares: fieldSize,
        soil_type: soilType,
        historical_yield_tons: historicalYield,
        irrigation_type: irrigationType,
        weather_condition: weatherCondition,
      };
      const data = await predictYield(payload, token, language);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prediction failed. Please try again.");
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
          📈 {msg.yield.title}
        </h1>
        <p className="max-w-2xl text-base leading-relaxed" style={{ color: "var(--foreground)", opacity: 0.65 }}>
          Enter your field parameters to receive an AI-powered yield prediction with a confidence
          range, key yield drivers, and targeted optimisation strategies.
        </p>
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* ── Left: Form ── */}
        <section>
          <form
            id="yield-form"
            onSubmit={handleSubmit}
            noValidate
            className="flex flex-col gap-5 rounded-2xl border p-6 shadow-sm"
            style={{
              borderColor: "color-mix(in srgb,var(--primary) 20%,transparent)",
              background: "color-mix(in srgb,var(--primary) 3%,white)",
            }}
          >
            {/* Crop type */}
            <div>
              <label htmlFor="yield-crop-type" className={labelCls} style={{ color: "var(--primary)" }}>
                {msg.yield.cropType}
              </label>
              <div className="mb-2 flex flex-wrap gap-1.5">
                {CROP_CHIPS.map((chip) => {
                  const isSelected = cropType === chip;
                  return (
                    <button
                      key={chip}
                      type="button"
                      onClick={() => { setCropType(chip); resetResult(); }}
                      aria-pressed={isSelected}
                      className={`rounded-full px-3.5 py-1 text-xs font-bold transition-all border ${
                        isSelected
                          ? "bg-emerald-600 border-emerald-600 text-white shadow-sm"
                          : "bg-emerald-100/80 border-emerald-300 text-emerald-950 hover:bg-emerald-200 hover:text-emerald-950"
                      }`}
                    >
                      {chip}
                    </button>
                  );
                })}
              </div>
              <input
                id="yield-crop-type"
                type="text"
                placeholder="Or type a crop name…"
                value={cropType}
                onChange={(e) => { setCropType(e.target.value); resetResult(); }}
                disabled={isLoading}
                className={inputCls}
                style={{ color: "var(--foreground)" }}
              />
            </div>

            {/* Field size + Historical yield */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="yield-field-size" className={labelCls} style={{ color: "var(--primary)" }}>
                  {msg.yield.fieldSize}
                </label>
                <input
                  id="yield-field-size"
                  type="number"
                  min={0.1}
                  step={0.1}
                  value={fieldSize}
                  onChange={(e) => { setFieldSize(parseFloat(e.target.value) || 0); resetResult(); }}
                  disabled={isLoading}
                  className={inputCls}
                  style={{ color: "var(--foreground)" }}
                />
              </div>
              <div>
                <label htmlFor="yield-historical" className={labelCls} style={{ color: "var(--primary)" }}
                  title="Enter 0 if this is your first season">
                  {msg.yield.historicalYield}
                  <span className="ml-1 font-normal opacity-50 normal-case">(0 = first season)</span>
                </label>
                <input
                  id="yield-historical"
                  type="number"
                  min={0}
                  step={0.5}
                  value={historicalYield}
                  onChange={(e) => { setHistoricalYield(parseFloat(e.target.value) || 0); resetResult(); }}
                  disabled={isLoading}
                  className={inputCls}
                  style={{ color: "var(--foreground)" }}
                />
              </div>
            </div>

            {/* Soil type */}
            <div>
              <label htmlFor="yield-soil-type" className={labelCls} style={{ color: "var(--primary)" }}>
                {msg.yield.soilType}
              </label>
              <select
                id="yield-soil-type"
                value={soilType}
                onChange={(e) => { setSoilType(e.target.value as YieldSoilType); resetResult(); }}
                disabled={isLoading}
                className={inputCls}
                style={{ color: "var(--foreground)" }}
              >
                {SOIL_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            {/* Irrigation type */}
            <div>
              <p className={labelCls} style={{ color: "var(--primary)" }}>{msg.yield.irrigationType}</p>
              <ToggleGroup
                options={IRRIGATION_OPTIONS}
                value={irrigationType}
                onChange={(v) => { setIrrigationType(v); resetResult(); }}
                disabled={isLoading}
                groupLabel="Irrigation type"
              />
            </div>

            {/* Weather condition */}
            <div>
              <p className={labelCls} style={{ color: "var(--primary)" }}>{msg.yield.weatherCondition}</p>
              <ToggleGroup
                options={WEATHER_OPTIONS}
                value={weatherCondition}
                onChange={(v) => { setWeatherCondition(v); resetResult(); }}
                disabled={isLoading}
                groupLabel="Weather condition"
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
              id="yield-submit-btn"
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
                  {msg.yield.loadingPredict}
                </>
              ) : (
                <>
                  <span aria-hidden="true">🌾</span>
                  {msg.yield.predictBtn}
                </>
              )}
            </button>
          </form>
        </section>

        {/* ── Right: Results ── */}
        <section aria-live="polite" aria-label="Yield prediction results" className="flex flex-col gap-5">
          {!result && !isLoading && (
            <div
              className="flex h-full min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-10 text-center"
              style={{
                borderColor: "color-mix(in srgb,var(--primary) 20%,transparent)",
                background: "color-mix(in srgb,var(--primary) 3%,transparent)",
              }}
            >
              <span className="text-5xl" aria-hidden="true">📊</span>
              <p className="text-sm font-medium" style={{ color: "var(--foreground)", opacity: 0.45 }}>
                Yield prediction and optimisation advice will appear here.
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
                AI is calculating your yield estimate…
              </p>
            </div>
          )}

          {result && (
            <div className="flex flex-col gap-5">
              {/* ── Hero metric card ── */}
              <div
                className="flex flex-col gap-2 rounded-2xl p-6 text-white shadow-lg"
                style={{ background: "linear-gradient(135deg,var(--primary),var(--primary-dk))" }}
              >
                <p className="text-xs font-semibold uppercase tracking-widest opacity-75">
                  {msg.yield.estimatedYield}
                </p>
                <p className="text-5xl font-extrabold tabular-nums">
                  {result.estimated_yield_tons.toFixed(1)}{" "}
                  <span className="text-2xl font-bold opacity-80">tons</span>
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span
                    className="rounded-full bg-white/20 px-3 py-1.5 text-xs font-semibold backdrop-blur-sm"
                    aria-label={`Confidence range: ${result.confidence_range}`}
                  >
                    📊 {result.confidence_range}
                  </span>
                </div>
              </div>

              {/* ── Key yield drivers ── */}
              {result.key_yield_drivers.length > 0 && (
                <div
                  className="flex flex-col gap-3 rounded-2xl border p-5 shadow-sm bg-white"
                  style={{
                    borderColor: "color-mix(in srgb,#0891b2 20%,transparent)",
                  }}
                >
                  <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide" style={{ color: "#0891b2" }}>
                    <span aria-hidden="true">📊</span>
                    {msg.yield.keyDrivers}
                  </p>
                  <ul className="flex flex-col gap-2" role="list">
                    {result.key_yield_drivers.map((driver, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm leading-snug text-slate-800 font-medium">
                        <span
                          className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full"
                          style={{ background: "#0891b2", marginTop: "0.4rem" }}
                          aria-hidden="true"
                        />
                        {driver}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* ── Optimisation suggestions ── */}
              {result.optimization_suggestions.length > 0 && (
                <div
                  className="flex flex-col gap-3 rounded-2xl border p-5 shadow-sm bg-white"
                  style={{
                    borderColor: "color-mix(in srgb,var(--earthy) 25%,transparent)",
                  }}
                >
                  <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide" style={{ color: "var(--earthy)" }}>
                    <span aria-hidden="true">🚀</span>
                    {msg.yield.optimizationSuggestions}
                  </p>
                  <ul className="flex flex-col gap-2" role="list">
                    {result.optimization_suggestions.map((tip, i) => (
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
