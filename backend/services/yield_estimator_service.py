"""
Algorithmic Yield Estimator — deterministic, no external LLM.
Uses crop baseline yields combined with soil, irrigation, and weather multipliers.
"""
from schemas.yield_estimator import YieldEstimatorRequest, YieldEstimatorResponse

# ── Baseline yield (tons/hectare) under ideal conditions ─────────────────────
_BASELINE_YIELD: dict[str, float] = {
    "wheat":   3.5,
    "rice":    4.5,
    "maize":   5.5,
    "tomato":  40.0,
    "potato":  25.0,
    "cotton":  1.8,
    "soybean": 2.8,
    "sugarcane": 70.0,
    "default": 4.0,
}

# ── Soil type yield multipliers ───────────────────────────────────────────────
_SOIL_MULTIPLIER: dict[str, float] = {
    "loam":    1.00,  # ideal
    "silty":   0.95,
    "clay":    0.85,
    "peaty":   0.90,
    "chalky":  0.75,
    "sandy":   0.65,
}

# ── Irrigation type yield multipliers ─────────────────────────────────────────
_IRRIGATION_MULTIPLIER: dict[str, float] = {
    "drip":       1.00,  # most efficient
    "sprinkler":  0.92,
    "flood":      0.80,
    "rainfed":    0.65,
}

# ── Weather condition yield multipliers ───────────────────────────────────────
_WEATHER_MULTIPLIER: dict[str, float] = {
    "optimal":     1.00,
    "moderate":    0.85,
    "heavy_rain":  0.70,
    "drought":     0.45,
}

# ── Confidence window (±%) per weather condition ──────────────────────────────
_CONFIDENCE_WINDOW: dict[str, float] = {
    "optimal":     0.08,   # ±8%
    "moderate":    0.12,
    "heavy_rain":  0.18,
    "drought":     0.22,
}


def _key(value: str) -> str:
    return value.strip().lower()


def _identify_drivers(
    req: YieldEstimatorRequest,
    soil_m: float,
    irr_m: float,
    weather_m: float,
    historical_factor: float,
) -> list[str]:
    drivers: list[str] = []

    # Weather is highest impact
    if weather_m < 0.7:
        drivers.append(f"Drought conditions severely limiting yield (weather multiplier: {weather_m:.2f}×)")
    elif weather_m < 0.9:
        drivers.append(f"Sub-optimal weather reducing yield (multiplier: {weather_m:.2f}×)")
    else:
        drivers.append("Favourable weather conditions supporting strong yield")

    # Irrigation
    if irr_m < 0.75:
        drivers.append(f"Rainfed/flood irrigation reducing water efficiency (multiplier: {irr_m:.2f}×)")
    elif irr_m >= 1.0:
        drivers.append("Drip irrigation maximising water-use efficiency")

    # Soil
    if soil_m < 0.75:
        drivers.append(f"Sandy/chalky soil limiting nutrient retention (multiplier: {soil_m:.2f}×)")
    elif soil_m >= 1.0:
        drivers.append("Loamy soil providing ideal nutrient and moisture balance")

    # Historical data
    if req.historical_yield_tons > 0:
        drivers.append(
            f"Historical yield of {req.historical_yield_tons} tons used as calibration anchor"
        )

    return drivers


def _optimization_suggestions(
    req: YieldEstimatorRequest,
    soil_m: float,
    irr_m: float,
    weather_m: float,
) -> list[str]:
    suggestions: list[str] = []

    if irr_m < 0.9:
        suggestions.append(
            "Upgrade to drip irrigation to improve water-use efficiency by up to 35%."
        )
    if soil_m < 0.85:
        suggestions.append(
            "Amend soil with organic compost and biochar to improve structure and water retention."
        )
    if weather_m < 0.7:
        suggestions.append(
            "Install shade nets or micro-sprinklers for drought mitigation and evaporation control."
        )
    if req.weather_condition == "heavy_rain":
        suggestions.append(
            "Improve field drainage with raised beds or furrow systems to prevent waterlogging."
        )
    suggestions.append(
        f"Apply split fertilization across 3 doses (basal + top-dress) to reduce leaching losses."
    )
    suggestions.append(
        "Use certified, disease-resistant seed varieties matched to your regional agro-climatic zone."
    )

    return suggestions


def predict_yield(req: YieldEstimatorRequest) -> YieldEstimatorResponse:
    crop_key = _key(req.crop_type)
    baseline = _BASELINE_YIELD.get(crop_key, _BASELINE_YIELD["default"])

    soil_m    = _SOIL_MULTIPLIER.get(_key(req.soil_type), 0.80)
    irr_m     = _IRRIGATION_MULTIPLIER.get(_key(req.irrigation_type), 0.80)
    weather_m = _WEATHER_MULTIPLIER.get(_key(req.weather_condition), 0.80)

    # Blend historical yield into estimate if available (40% weight)
    if req.historical_yield_tons > 0:
        historical_per_ha = req.historical_yield_tons / req.field_size_hectares
        model_per_ha = baseline * soil_m * irr_m * weather_m
        estimated_per_ha = 0.6 * model_per_ha + 0.4 * historical_per_ha
        historical_factor = historical_per_ha
    else:
        estimated_per_ha = baseline * soil_m * irr_m * weather_m
        historical_factor = 0.0

    total_yield = round(estimated_per_ha * req.field_size_hectares, 2)
    per_ha_yield = round(estimated_per_ha, 2)

    # Confidence interval
    window = _CONFIDENCE_WINDOW.get(_key(req.weather_condition), 0.15)
    low  = round(total_yield * (1 - window), 2)
    high = round(total_yield * (1 + window), 2)
    confidence_range = f"{low} – {high} tons"

    drivers = _identify_drivers(req, soil_m, irr_m, weather_m, historical_factor)
    suggestions = _optimization_suggestions(req, soil_m, irr_m, weather_m)

    return YieldEstimatorResponse(
        estimated_yield_tons=total_yield,
        confidence_range=confidence_range,
        key_yield_drivers=drivers,
        optimization_suggestions=suggestions,
    )
