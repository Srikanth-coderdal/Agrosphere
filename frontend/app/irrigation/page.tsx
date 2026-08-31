"use client";

import { useState } from "react";
import {
  calculateIrrigation,
  CropType,
  GrowthStage,
  IrrigationRequest,
  IrrigationResponse,
  SoilType,
} from "@/app/lib/api";
import ProtectedRoute from "../components/ProtectedRoute";
import useProfileStore from "@/store/useProfileStore";
import { getMessages } from "../lib/i18n";

/* ── Option lists ───────────────────────────────────────────────────── */
const CROP_CHIPS = ["Wheat", "Rice", "Tomato", "Maize", "Potato", "Sugarcane"];
const GROWTH_STAGES: GrowthStage[] = ["Initial", "Crop Development", "Mid-Stage", "Late Stage"];
const SOIL_TYPES = ["Clay", "Sandy", "Loam", "Silty", "Chalky", "Peaty"];

/* ── Helpers ────────────────────────────────────────────────────────── */
function formatLiters(n: number | string | null | undefined): string {
  // Backend values occasionally arrive as strings/null; coerce defensively.
  const value = Number(n ?? 0);
  return (Number.isFinite(value) ? value : 0).toLocaleString("en-IN");
}

/* ── Shared input styles ────────────────────────────────────────────── */
const inputCls =
  "w-full rounded-xl border border-emerald-200 bg-white px-4 py-2.5 text-sm text-slate-900 font-semibold outline-none transition-colors focus:border-emerald-500 focus:ring-2 disabled:cursor-not-allowed disabled:opacity-50";
const labelCls = "block text-xs font-bold uppercase tracking-wide mb-1.5 text-emerald-800";

/* ── Sub-components ─────────────────────────────────────────────────── */
interface FieldProps {
  label: string;
  tooltip?: string;
  children: React.ReactNode;
}

function Field({ label, tooltip, children }: FieldProps) {
  return (
    <div className="flex flex-col">
      <label className={labelCls} title={tooltip}>
        {label}
        {tooltip && (
          <span
            className="ml-1.5 inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800"
            aria-label={tooltip}
          >
            ?
          </span>
        )}
      </label>
      {children}
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────── */
export default function IrrigationPage() {
  /* ── Form state ── */
  const [form, setForm] = useState<IrrigationRequest>({
    crop_type: "Tomato",
    growth_stage: "Initial",
    soil_type: "Loam",
    field_size_hectares: 1.0,
    soil_moisture_percentage: 35,
    temperature_celsius: 28,
    rainfall_probability_percent: 10,
  });

  /* ── Async state ── */
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IrrigationResponse | null>(null);
  const { language } = useProfileStore();
  const msg = getMessages(language);

  /* ── Handlers ── */
  function set<K extends keyof IrrigationRequest>(key: K, value: IrrigationRequest[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (result) setResult(null);
    if (error) setError(null);
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setIsLoading(true);
    try {
      const data = await calculateIrrigation(form, language);
      setResult(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Calculation failed. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const etVal = parseFloat(result?.evapotranspiration_index as any);
  const displayEt = !isNaN(etVal) ? etVal.toFixed(2) : "0.00";

  /* ── Render ── */
  return (
    <ProtectedRoute>
      <div className="flex flex-col gap-10">
      {/* ── Page header ── */}
      <section className="flex flex-col gap-2">
        <h1 className="flex items-center gap-2 text-3xl font-extrabold tracking-tight sm:text-4xl text-emerald-400">
          💧 {msg.irrigation.title}
        </h1>
        <p className="max-w-2xl text-base leading-relaxed text-slate-300">
          Enter your field parameters to receive a precise AI-calculated water requirement, an
          optimal irrigation schedule, and actionable conservation tips tailored to your crop and
          soil conditions.
        </p>
      </section>

      {/* ── Main grid ── */}
      <div className="grid gap-8 lg:grid-cols-2">
        {/* ── Left: Form ── */}
        <section>
          <form
            id="irrigation-form"
            onSubmit={handleSubmit}
            className="flex flex-col gap-5 rounded-2xl border border-emerald-100 bg-white p-6 shadow-sm"
            noValidate
          >
            {/* Row 1 — Crop */}
            <Field label={msg.irrigation.cropType} tooltip="Select the primary crop in your field">
              <div className="mb-2.5 flex flex-wrap gap-1.5">
                {CROP_CHIPS.map((chip) => {
                  const isSelected = form.crop_type === chip;
                  return (
                    <button
                      key={chip}
                      type="button"
                      id={`crop-${chip.toLowerCase()}`}
                      onClick={() => set("crop_type", chip)}
                      disabled={isLoading}
                      aria-pressed={isSelected}
                      className={`rounded-full px-3.5 py-1 text-xs transition-all border ${
                        isSelected
                          ? "bg-emerald-600 border-emerald-600 text-white font-bold"
                          : "bg-emerald-100/70 border-emerald-300 text-emerald-950 font-bold hover:bg-emerald-200"
                      }`}
                    >
                      {chip}
                    </button>
                  );
                })}
              </div>
              <input
                id="irrigation-crop-type"
                type="text"
                placeholder="Or type a crop name..."
                value={form.crop_type}
                onChange={(e) => set("crop_type", e.target.value)}
                disabled={isLoading}
                className={inputCls}
              />
            </Field>

            {/* Row 2 — Growth Stage */}
            <Field label={msg.irrigation.growthStage} tooltip="Current phenological stage of the crop">
              <div className="flex flex-wrap gap-1.5">
                {GROWTH_STAGES.map((s) => {
                  const isSelected = form.growth_stage === s;
                  const icons: Record<string, string> = { Initial: "🌱", "Crop Development": "🌿", "Mid-Stage": "🌳", "Late Stage": "🍂" };
                  return (
                    <button
                      key={s}
                      type="button"
                      id={`stage-${s.toLowerCase().replace(/\s+/g, '-')}`}
                      onClick={() => set("growth_stage", s)}
                      disabled={isLoading}
                      aria-pressed={isSelected}
                      className={`rounded-full px-3.5 py-1.5 text-xs transition-all border flex items-center gap-1.5 shadow-sm ${
                        isSelected
                          ? "bg-emerald-600 border-emerald-600 text-white font-bold"
                          : "bg-slate-100/80 border-slate-200 text-slate-900 font-bold hover:bg-slate-200"
                      }`}
                    >
                      <span className="text-sm" aria-hidden="true">{icons[s] || "🌱"}</span>
                      <span>{s}</span>
                    </button>
                  );
                })}
              </div>
            </Field>

            {/* Row 3 — Soil Type + Field size */}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={msg.irrigation.soilType} tooltip="Dominant soil texture in the field">
                <select
                  id="soil-type"
                  value={form.soil_type}
                  onChange={(e) => set("soil_type", e.target.value as SoilType)}
                  disabled={isLoading}
                  className="w-full rounded-xl border border-emerald-300 bg-white px-4 py-2.5 text-sm text-slate-900 font-medium outline-none transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {SOIL_TYPES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </Field>

              <Field label={msg.irrigation.fieldSize} tooltip="Total cultivated area in hectares">
                <input
                  id="field-size"
                  type="number"
                  min={0.1}
                  step={0.1}
                  value={form.field_size_hectares}
                  onChange={(e) => set("field_size_hectares", parseFloat(e.target.value) || 0.1)}
                  disabled={isLoading}
                  className={inputCls}
                />
              </Field>
            </div>

            {/* Row 3 — Soil moisture slider */}
            <Field
              label={msg.irrigation.soilMoisture(form.soil_moisture_percentage)}
              tooltip="Current volumetric soil moisture level"
            >
              <div className="flex items-center gap-3">
                <span className="text-xs font-medium text-slate-400">0%</span>
                <input
                  id="soil-moisture"
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={form.soil_moisture_percentage}
                  onChange={(e) => set("soil_moisture_percentage", parseInt(e.target.value))}
                  disabled={isLoading}
                  className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-emerald-100 accent-emerald-600 disabled:cursor-not-allowed"
                  aria-label={`Soil moisture: ${form.soil_moisture_percentage}%`}
                  aria-valuenow={form.soil_moisture_percentage}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
                <span className="text-xs font-medium text-slate-400">100%</span>
                <span
                  className="w-12 rounded-lg px-2 py-1 text-center text-xs font-bold tabular-nums bg-emerald-100 text-emerald-800"
                >
                  {form.soil_moisture_percentage}%
                </span>
              </div>
            </Field>

            {/* Row 4 — Temperature + Rainfall probability */}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={msg.irrigation.temperature} tooltip="Expected daytime temperature during irrigation period">
                <input
                  id="temperature"
                  type="number"
                  min={-10}
                  max={60}
                  step={0.5}
                  value={form.temperature_celsius}
                  onChange={(e) => set("temperature_celsius", parseFloat(e.target.value) || 0)}
                  disabled={isLoading}
                  className={inputCls}
                />
              </Field>

              <Field
                label={msg.irrigation.rainfallProbability}
                tooltip="Probability of rainfall in the next 24 hours (0–100)"
              >
                <input
                  id="rainfall-probability"
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={form.rainfall_probability_percent}
                  onChange={(e) => set("rainfall_probability_percent", parseInt(e.target.value) || 0)}
                  disabled={isLoading}
                  className={inputCls}
                />
              </Field>
            </div>

            {/* Error */}
            {error && (
              <p
                role="alert"
                className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium bg-red-50 text-red-700 border border-red-100"
              >
                ⚠️ {error}
              </p>
            )}

            {/* Submit */}
            <button
              id="calculate-btn"
              type="submit"
              disabled={isLoading}
              aria-busy={isLoading}
              className="flex w-full items-center justify-center gap-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 rounded-xl shadow-md transition-all duration-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <svg className="h-5 w-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Calculating Water Need…
                </>
              ) : (
                <>
                  <span aria-hidden="true">💧</span>
                  {msg.irrigation.analyzeBtn}
                </>
              )}
            </button>
          </form>
        </section>

        {/* ── Right: Results ── */}
        <section aria-live="polite" aria-label="Irrigation results" className="flex flex-col gap-5">
          {!result && !isLoading && (
            <div
              className="flex h-full min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-emerald-900/50 bg-slate-900/40 p-10 text-center"
            >
              <span className="text-5xl" aria-hidden="true">📊</span>
              <p className="text-sm font-medium text-slate-400">
                Water requirement &amp; schedule will appear here after analysis.
              </p>
            </div>
          )}

          {isLoading && (
            <div className="flex h-full min-h-64 flex-col items-center justify-center gap-4 rounded-2xl border border-emerald-800/60 bg-slate-900/80">
              <div
                className="h-14 w-14 animate-spin rounded-full border-4 border-t-transparent border-emerald-500"
                aria-hidden="true"
              />
              <p className="text-sm font-semibold text-emerald-400">
                AI is calculating optimal irrigation…
              </p>
            </div>
          )}

          {result && (
            <>
              {/* ── Hero metric card ── */}
              <div className="flex flex-col gap-1 rounded-2xl p-6 text-white shadow-md bg-emerald-600">
                <p className="text-xs font-bold uppercase tracking-wider text-emerald-100 opacity-90">
                  {msg.irrigation.totalWaterRequired}
                </p>
                <p className="text-5xl font-extrabold tabular-nums">
                  {formatLiters(result.water_required_liters)}{" "}
                  <span className="text-2xl font-bold opacity-80">L</span>
                </p>
                <div className="mt-3">
                  <span className="rounded-full bg-emerald-700/60 text-white font-semibold text-xs px-3 py-1 border border-emerald-500/40 inline-flex items-center gap-1.5">
                    {msg.irrigation.evapotranspirationIndex}: {displayEt}
                  </span>
                </div>
              </div>

              {/* ── Recommended schedule card ── */}
              <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col gap-3">
                <span className="text-2xl" aria-hidden="true">📅</span>
                <div className="flex flex-col gap-1">
                  <p className="text-xs font-bold uppercase tracking-wider text-teal-600 flex items-center gap-2">
                    {msg.irrigation.recommendedSchedule}
                  </p>
                  <p className="text-slate-900 font-medium text-sm leading-relaxed">
                    {result.recommended_schedule}
                  </p>
                </div>
              </div>

              {/* ── Weather context card ── */}
              <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col gap-3">
                <span className="text-2xl" aria-hidden="true">⛅</span>
                <div className="flex flex-col gap-1">
                  <p className="text-xs font-bold uppercase tracking-wider text-teal-600 flex items-center gap-2">
                    {msg.irrigation.weatherContext}
                  </p>
                  <p className="text-slate-900 font-medium text-sm leading-relaxed">
                    {result.weather_summary}
                  </p>
                </div>
              </div>

              {/* ── Actionable tips card ── */}
              <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col gap-3">
                <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-teal-600">
                  <span aria-hidden="true">💡</span>
                  {msg.irrigation.tipsHeader}
                </p>
                <ul className="flex flex-col gap-2.5" role="list">
                  {result.actionable_tips.map((tip, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-slate-900 font-medium text-sm leading-relaxed">
                      <span
                        className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white text-[10px] font-bold"
                        aria-hidden="true"
                      >
                        ✓
                      </span>
                      {tip}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </section>
      </div>
      </div>
    </ProtectedRoute>
  );
}