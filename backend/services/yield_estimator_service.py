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
    lang = (getattr(req, "language", "en") or "en").lower()

    # Weather is highest impact
    if weather_m < 0.7:
        if lang == "ta":
            drivers.append(
                f"வறட்சி நிலைகள் விளைச்சலை கடுமையாக குறைக்கின்றன (காலநிலை பெருக்கம்: {weather_m:.2f}×)"
            )
        else:
            drivers.append(
                f"Drought conditions severely limiting yield (weather multiplier: {weather_m:.2f}×)"
            )
    elif weather_m < 0.9:
        if lang == "ta":
            drivers.append(f"சிறிதளவு உகந்தில்லாத காலநிலை விளைச்சலை குறைக்கிறது (பெருக்கம்: {weather_m:.2f}×)")
        else:
            drivers.append(f"Sub-optimal weather reducing yield (multiplier: {weather_m:.2f}×)")
    else:
        drivers.append(
            "வழக்கத்திற்கு ஏற்ற காலநிலை நல்ல விளைச்சலுக்கு உதவுகிறது"
            if lang == "ta"
            else "Favourable weather conditions supporting strong yield"
        )

    # Irrigation
    if irr_m < 0.75:
        if lang == "ta":
            drivers.append(
                f"மழை சார்ந்த/வெள்ள பாசனம் நீர் திறனை குறைக்கிறது (பெருக்கம்: {irr_m:.2f}×)"
            )
        else:
            drivers.append(
                f"Rainfed/flood irrigation reducing water efficiency (multiplier: {irr_m:.2f}×)"
            )
    elif irr_m >= 1.0:
        drivers.append(
            "துளி பாசனம் நீர்ப்பயன்பாட்டு திறனை அதிகரிக்கிறது"
            if lang == "ta"
            else "Drip irrigation maximising water-use efficiency"
        )

    # Soil
    if soil_m < 0.75:
        if lang == "ta":
            drivers.append(
                f"மணல்/சுண்ணாம்பு தன்மை மண் சத்துகளை பிடித்துக் கொள்ளும் திறனை குறைக்கிறது (பெருக்கம்: {soil_m:.2f}×)"
            )
        else:
            drivers.append(
                f"Sandy/chalky soil limiting nutrient retention (multiplier: {soil_m:.2f}×)"
            )
    elif soil_m >= 1.0:
        drivers.append(
            "மண்-களிமண் (loamy) மண் சத்து மற்றும் ஈரப்பதத்திற்கு உகந்த சமநிலையை வழங்குகிறது"
            if lang == "ta"
            else "Loamy soil providing ideal nutrient and moisture balance"
        )

    # Historical data
    if req.historical_yield_tons > 0:
        if lang == "ta":
            drivers.append(
                f"கடந்த பருவத்தில் {req.historical_yield_tons} டன் விளைச்சல் அளவுத்தீர்விற்குப் பயன்படுத்தப்பட்டது"
            )
        else:
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
    lang = (getattr(req, "language", "en") or "en").lower()

    if irr_m < 0.9:
        suggestions.append(
            "நீர் பயன்பாட்டுத் திறனை அதிகரிக்க துளி பாசனத்திற்கு மாறுங்கள் (அதிகபட்சம் சுமார் 35% வரை)."
            if lang == "ta"
            else "Upgrade to drip irrigation to improve water-use efficiency by up to 35%."
        )
    if soil_m < 0.85:
        suggestions.append(
            "மண்ணின் அமைப்பு மற்றும் நீரை பிடித்துக் கொள்ளும் திறன் மேம்பட கரிம உரம் (compost) மற்றும் பயோசார் (biochar) சேர்க்கவும்."
            if lang == "ta"
            else "Amend soil with organic compost and biochar to improve structure and water retention."
        )
    if weather_m < 0.7:
        suggestions.append(
            "வறட்சியை சமாளிக்க நிழற்பாய்/ஷேட் நெட் அல்லது மைக்ரோ-ஸ்பிரிங்களரை பயன்படுத்தி ஆவியாதல் (evaporation) குறைக்கவும்."
            if lang == "ta"
            else "Install shade nets or micro-sprinklers for drought mitigation and evaporation control."
        )
    if req.weather_condition == "heavy_rain":
        suggestions.append(
            "வயலில் நீர் தேங்காமல் இருக்க உயர்த்தப்பட்ட படுக்கைகள் (raised beds) அல்லது வாய்க்கால்/ஃபர்ரோ முறைகளை அமைக்கவும்."
            if lang == "ta"
            else "Improve field drainage with raised beds or furrow systems to prevent waterlogging."
        )
    suggestions.append(
        "உரத்தை 3 தடவைகளாக (அடிப்படை + மேலிடு) பிரித்து கொடுப்பதால் நீர்வழி (leaching) இழப்புகள் குறையும்."
        if lang == "ta"
        else f"Apply split fertilization across 3 doses (basal + top-dress) to reduce leaching losses."
    )
    suggestions.append(
        "உங்கள் பகுதியின் காலநிலை/வேளாண் நிலைக்கு பொருந்தும், சான்றளிக்கப்பட்ட நோய் எதிர்ப்பு விதைகளை பயன்படுத்துங்கள்."
        if lang == "ta"
        else "Use certified, disease-resistant seed varieties matched to your regional agro-climatic zone."
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
    if (getattr(req, "language", "en") or "en").lower() == "ta":
        confidence_range = f"{low} – {high} டன்"
    else:
        confidence_range = f"{low} – {high} tons"

    drivers = _identify_drivers(req, soil_m, irr_m, weather_m, historical_factor)
    suggestions = _optimization_suggestions(req, soil_m, irr_m, weather_m)

    return YieldEstimatorResponse(
        estimated_yield_tons=total_yield,
        confidence_range=confidence_range,
        key_yield_drivers=drivers,
        optimization_suggestions=suggestions,
    )
