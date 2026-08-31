/**
 * api.ts — Agrosphere API service layer
 * Connects the Next.js frontend to the FastAPI backend.
 */
import type { LanguageCode } from "./LanguageContext";

/** Mirrors backend/schemas/diagnostic.py -> SafeDosage */
export interface SafeDosage {
  chemical_name: string;
  dosage: string;
  unit: string;
  max_frequency: string;
  pre_harvest_interval_days: number;
}

/** Mirrors backend/schemas/diagnostic.py -> WeatherSummary */
export interface WeatherSummary {
  temperature: string;
  rain_chance: string;
  spray_advisory: string;
}

/** Mirrors backend/schemas/diagnostic.py -> VerifiedDiagnosticResponse */
export interface ScanResponse {
  pathogen: string;
  confidence: number;
  verified_treatment: string;
  safe_dosages: SafeDosage[];
  organic_recommendations: string[];
  preventive_measures: string[];
  disclaimer: string;
  is_verified: boolean;
  weather_summary?: WeatherSummary | null;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Sends a crop image (and optional farmer comment) to the FastAPI
 * POST /api/scan endpoint and returns structured diagnostic data.
 *
 * @throws {Error} with a human-readable message on HTTP or network failure.
 */
export async function scanCropImage(
  file: File,
  cropType: string,
  latitude?: number,
  longitude?: number,
  farmerComment?: string,
  language?: LanguageCode,
  operationalContext?: string
): Promise<ScanResponse> {
  const form = new FormData();
  form.append("image", file);
  form.append("crop_type", cropType);
  if (latitude !== undefined && latitude !== null) form.append("latitude", latitude.toString());
  if (longitude !== undefined && longitude !== null) form.append("longitude", longitude.toString());
  if (farmerComment && farmerComment.trim().length > 0) {
    form.append("farmer_comment", farmerComment.trim());
  }
  if (language) form.append("language", language);
  if (operationalContext && operationalContext.trim().length > 0) {
    form.append("operational_context", operationalContext.trim());
    form.append("context_mode", operationalContext.trim());
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/scan`, {
      method: "POST",
      body: form,
    });
  } catch {
    throw new Error(
      "Unable to reach the Agrosphere server. Please check that the backend is running and try again."
    );
  }

  if (!response.ok) {
    // Attempt to extract FastAPI's structured error detail
    let detail: string | undefined;
    try {
      const errBody = await response.json();
      detail =
        typeof errBody.detail === "string"
          ? errBody.detail
          : JSON.stringify(errBody.detail);
    } catch {
      // Ignore JSON parse failure — fall through to status-based messages
    }

    switch (response.status) {
      case 400:
        throw new Error(detail ?? "Unsupported image format. Please upload a JPG, PNG, or WebP file.");
      case 422:
        throw new Error(detail ?? "Invalid request data. Please check your file and try again.");
      case 500:
        throw new Error(detail ?? "Internal server error. Please try again in a moment.");
      case 502:
        throw new Error(detail ?? "AI service is temporarily unavailable. Please try again shortly.");
      default:
        throw new Error(detail ?? `Unexpected error (HTTP ${response.status}). Please try again.`);
    }
  }

  return response.json() as Promise<ScanResponse>;
}

/* ══════════════════════════════════════════════════════════════════════
   Smart Irrigation — types & API
   ══════════════════════════════════════════════════════════════════════ */

export type CropType = "Tomato" | "Wheat" | "Maize" | "Rice" | "Cotton" | "Sugarcane";
export type GrowthStage = "Initial" | "Crop Development" | "Mid-Stage" | "Late Stage";
export type SoilType = "Clay" | "Sandy" | "Loam" | "Silty";

/** Mirrors backend/schemas.py → IrrigationRequest */
export interface IrrigationRequest {
  crop_type: string;
  growth_stage: GrowthStage;
  soil_type: SoilType;
  field_size_hectares: number;
  soil_moisture_percentage: number;
  temperature_celsius: number;
  rainfall_probability_percent: number;
}

/** Mirrors backend/schemas.py → IrrigationResponse */
export interface IrrigationResponse {
  water_required_liters: number;
  evapotranspiration_index: number | string | null | undefined;
  recommended_schedule: string;
  weather_summary: string;
  actionable_tips: string[];
}

/**
 * Sends irrigation parameters to the FastAPI POST /api/irrigation/calculate
 * endpoint and returns a structured watering recommendation.
 *
 * @throws {Error} with a human-readable message on HTTP or network failure.
 */
export async function calculateIrrigation(
  data: IrrigationRequest,
  language?: LanguageCode
): Promise<IrrigationResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/irrigation/calculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...data, language: language ?? "en" }),
    });
  } catch {
    throw new Error(
      "Unable to reach the Agrosphere server. Please check that the backend is running and try again."
    );
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const errBody = await response.json();
      detail =
        typeof errBody.detail === "string"
          ? errBody.detail
          : JSON.stringify(errBody.detail);
    } catch {
      // Ignore JSON parse failure
    }

    switch (response.status) {
      case 422:
        throw new Error(detail ?? "Invalid input values. Please review the form and try again.");
      case 500:
        throw new Error(detail ?? "Internal server error. Please try again in a moment.");
      case 502:
        throw new Error(detail ?? "AI service is temporarily unavailable. Please try again shortly.");
      default:
        throw new Error(detail ?? `Unexpected error (HTTP ${response.status}). Please try again.`);
    }
  }

  return response.json() as Promise<IrrigationResponse>;
}

/* ══════════════════════════════════════════════════════════════════════
   Shared JSON fetch helper
   ══════════════════════════════════════════════════════════════════════ */

/**
 * Generic authenticated JSON POST helper.
 * Attaches `Authorization: Bearer <token>` when a token is provided.
 * @throws {Error} with a human-readable message on HTTP/network failure.
 */
async function jsonPost<T>(
  path: string,
  body: unknown,
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "Unable to reach the Agrosphere server. Please check that the backend is running and try again."
    );
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const err = await response.json();
      detail =
        typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    } catch { /* ignore */ }

    switch (response.status) {
      case 400: throw new Error(detail ?? "Bad request. Please review your input.");
      case 401: throw new Error(detail ?? "Invalid credentials. Please try again.");
      case 409: throw new Error(detail ?? "An account with this email already exists.");
      case 422: throw new Error(detail ?? "Validation error. Please check your input.");
      case 500: throw new Error(detail ?? "Internal server error. Please try again.");
      case 502: throw new Error(detail ?? "AI service temporarily unavailable. Please retry.");
      default:  throw new Error(detail ?? `Unexpected error (HTTP ${response.status}).`);
    }
  }

  return response.json() as Promise<T>;
}

/* ══════════════════════════════════════════════════════════════════════
   Authentication — types & API
   ══════════════════════════════════════════════════════════════════════ */

/** Mirrors backend/schemas/auth.py → UserCreate */
export interface AuthSignupRequest {
  full_name: string;
  email: string;
  password: string;
}

/** Mirrors backend/schemas/auth.py → Token */
export interface AuthLoginResponse {
  access_token: string;
  token_type: string;
}

/** Mirrors backend/schemas/auth.py → UserResponse */
export interface UserResponse {
  id: number;
  full_name: string;
  email: string;
  is_active: boolean;
}

/**
 * Register a new user account.
 * POST /api/v1/auth/signup
 */
export async function signupUser(data: AuthSignupRequest): Promise<UserResponse> {
  return jsonPost<UserResponse>("/api/v1/auth/signup", data);
}

/**
 * Authenticate with email + password.
 * POST /api/v1/auth/login  (OAuth2PasswordRequestForm — form-encoded)
 * NOTE: FastAPI expects `username` field for the email value.
 */
export async function loginUser(
  email: string,
  password: string
): Promise<AuthLoginResponse> {
  // OAuth2PasswordRequestForm requires application/x-www-form-urlencoded
  const params = new URLSearchParams({ username: email, password });

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: params.toString(),
    });
  } catch {
    throw new Error(
      "Unable to reach the Agrosphere server. Please check that the backend is running and try again."
    );
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const err = await response.json();
      detail =
        typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    } catch { /* ignore */ }
    throw new Error(detail ?? "Invalid email or password.");
  }

  return response.json() as Promise<AuthLoginResponse>;
}

/**
 * Fetch the currently authenticated user's profile.
 * GET /api/v1/auth/me
 */
export async function fetchCurrentUser(token: string): Promise<UserResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error("Unable to reach the Agrosphere server.");
  }
  if (!response.ok) throw new Error("Session expired. Please log in again.");
  return response.json() as Promise<UserResponse>;
}

/**
 * Log out the current user session and clear backend cookies.
 * POST /api/v1/auth/logout
 */
export async function logoutUser(): Promise<{ message: string }> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (response.ok) {
      return response.json();
    }
  } catch {
    // Gracefully handle network errors during logout
  }
  return { message: "Successfully logged out" };
}

/* ══════════════════════════════════════════════════════════════════════
   Urban Gardening — types & API
   ══════════════════════════════════════════════════════════════════════ */

export type SpaceType = "balcony" | "indoor" | "rooftop";

/** Mirrors backend/schemas/urban_gardening.py → UrbanGardeningRequest */
export interface UrbanGardeningRequest {
  plant_type: string;
  space_type: SpaceType;
  sunlight_hours: number;
  container_size: number;
}

/** Mirrors backend/schemas/urban_gardening.py → UrbanGardeningResponse */
export interface UrbanGardeningResponse {
  care_schedule: string;
  watering_frequency: string;
  sunlight_recommendations: string;
  soil_mix: string;
  actionable_tips: string[];
}

/**
 * Request urban gardening advice.
 * POST /api/v1/urban-gardening/advise
 */
export async function getUrbanGardeningAdvice(
  data: UrbanGardeningRequest,
  token?: string | null,
  language?: LanguageCode
): Promise<UrbanGardeningResponse> {
  return jsonPost<UrbanGardeningResponse>(
    "/api/v1/urban-gardening/advise",
    { ...data, language: language ?? "en" },
    token
  );
}

/* ══════════════════════════════════════════════════════════════════════
   Yield Estimator — types & API
   ══════════════════════════════════════════════════════════════════════ */

export type YieldSoilType = "clay" | "sandy" | "loam" | "silty" | "chalky" | "peaty";
export type IrrigationType = "drip" | "sprinkler" | "flood" | "rainfed";
export type WeatherCondition = "optimal" | "drought" | "heavy_rain" | "moderate";

/** Mirrors backend/schemas/yield_estimator.py → YieldEstimatorRequest */
export interface YieldEstimatorRequest {
  crop_type: string;
  field_size_hectares: number;
  soil_type: YieldSoilType;
  historical_yield_tons: number;
  irrigation_type: IrrigationType;
  weather_condition: WeatherCondition;
}

/** Mirrors backend/schemas/yield_estimator.py → YieldEstimatorResponse */
export interface YieldEstimatorResponse {
  estimated_yield_tons: number;
  confidence_range: string;
  key_yield_drivers: string[];
  optimization_suggestions: string[];
}

/**
 * Predict crop yield.
 * POST /api/v1/yield-estimator/predict
 */
export async function predictYield(
  data: YieldEstimatorRequest,
  token?: string | null,
  language?: LanguageCode
): Promise<YieldEstimatorResponse> {
  return jsonPost<YieldEstimatorResponse>(
    "/api/v1/yield-estimator/predict",
    { ...data, language: language ?? "en" },
    token
  );
}
