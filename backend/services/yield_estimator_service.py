"""
Deterministic Crop Yield Estimator Service.
Runs 100% deterministically with zero LLM dependency.
"""
import logging

from schemas.yield_estimator import YieldEstimatorRequest, YieldEstimatorResponse

logger = logging.getLogger(__name__)

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
    "almonds": 2.2,
    "almond":  2.2,
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


def _deterministic_drivers(req: YieldEstimatorRequest, soil_m: float, irr_m: float, weather_m: float) -> list[str]:
    crop = req.crop_type.strip().title()
    crop_lower = crop.lower()
    lang = (getattr(req, "language", "en") or "en").lower()

    if "almond" in crop_lower:
        if lang == "ta":
            return [
                f"{crop} காய்ப்புத் திறனுக்கு குளிர்கால சில் ஹவர்ஸ் (chill hours) மற்றும் பூக்கும் கால வெப்பநிலை முக்கியமானது.",
                "பூக்கும் காலத்தில் தேனீ மகரந்தச் சேர்க்கை திறன் பருப்பு விளைச்சலைத் தீர்மானிக்கிறது.",
                "ஹல்-ஸ்பிளிட் (hull-split) நிலையில் கட்டுப்படுத்தப்பட்ட பாசன மேலாண்மை.",
            ]
        return [
            f"Winter chill hour fulfillment and bloom-phase temperature critical for {crop} fruit set.",
            "Pollination efficiency during bloom period influencing kernel yield potential.",
            "Hull-split deficit irrigation management regulating kernel quality and hull split timing.",
        ]
    elif "rice" in crop_lower:
        if lang == "ta":
            return [
                "கதிர் உருவாகும் நிலையில் (panicle initiation) நீர் ஆழக் கட்டுப்பாடு.",
                "மணி பிடிக்கும் பருவத்தில் சூரிய ஒளி மற்றும் இலைப்பரப்பு ஒளிச்சேர்க்கை.",
                "பூக்கும் முன் மண்ணின் தழைச்சத்து (Nitrogen) மற்றும் பச்சைய அளவு.",
            ]
        return [
            "Standing water depth control during panicle initiation determining grain head size.",
            "Solar radiation and canopy light interception during grain filling phase.",
            "Soil nitrogen availability and leaf chlorophyll index prior to flowering.",
        ]
    elif "sugarcane" in crop_lower:
        if lang == "ta":
            return [
                "தண்டு நீட்சிப் பருவத்தில் கிடைக்கும் பாசன நீர் மொத்த கரும்பு எடையை உயர்த்துகிறது.",
                "அறுவடைக்கு முன் முதிர்ச்சி நிலையில் சர்க்கரைச் சத்து (Brix sucrose) செறிவு.",
                "மறுதாம்பு (ratoon) பயிர் மேலாண்மை மற்றும் மண் காற்றோட்டம்.",
            ]
        return [
            "Stalk elongation water availability driving total cane biomass production.",
            "Pre-harvest maturation drying phase regulating Brix sucrose accumulation.",
            "Ratoon stubble management and soil aeration supporting tiller density.",
        ]
    elif "tomato" in crop_lower:
        if lang == "ta":
            return [
                "பூ மற்றும் பிஞ்சு பிடிக்கும் நிலையில் கால்சியம் சத்து மற்றும் சீரான மண் ஈரப்பதம்.",
                f"{req.irrigation_type.title()} பாசன முறை மற்றும் {req.soil_type.title()} மண்ணின் வடிகால் திறன்.",
                f"காலநிலை ({req.weather_condition}) மற்றும் மகரந்தச் சேர்க்கை செயல்பாடு.",
            ]
        return [
            "Blossom-end calcium regulation and uniform root-zone moisture during fruit set.",
            f"Canopy aeration and water use efficiency under {req.irrigation_type} irrigation in {req.soil_type} soil.",
            f"Fruit-ripening thermal regime under {req.weather_condition} weather conditions.",
        ]

    if lang == "ta":
        return [
            f"{crop} பயிருக்கான காலநிலை ({req.weather_condition}, காரணி {weather_m:.2f}) விளைச்சலை நிர்ணயிக்கிறது.",
            f"{req.soil_type.title()} மண் வகை (காரணி {soil_m:.2f}) மற்றும் வேர் மண்டல ஊட்டச்சத்து ஈர்ப்பு.",
            f"{req.irrigation_type.title()} பாசன முறை (காரணி {irr_m:.2f}) மூலம் கிடைக்கும் நீர் பயன்பாட்டுத் திறன்.",
        ]

    return [
        f"{crop} physiological response to weather condition ({req.weather_condition}, factor {weather_m:.2f}).",
        f"Water retention and root zone aeration in {req.soil_type} soil (factor {soil_m:.2f}).",
        f"Moisture delivery efficiency under {req.irrigation_type} irrigation (factor {irr_m:.2f}).",
    ]


def _deterministic_suggestions(req: YieldEstimatorRequest, soil_m: float, irr_m: float, weather_m: float) -> list[str]:
    crop = req.crop_type.strip().lower()
    lang = (getattr(req, "language", "en") or "en").lower()

    if "almond" in crop:
        if lang == "ta":
            return [
                "பூக்கும் காலத்தில் சிறந்த மகரந்தச் சேர்க்கைக்கு ஏக்கருக்கு 2–3 தேனீப் பெட்டிகளைப் பராமரிக்கவும்.",
                "ஹல்-ஸ்பிளிட் காலத்தில் கட்டுப்படுத்தப்பட்ட பாசனத்தை (RDI) மேற்கொள்ளவும்.",
                "பூப்பதற்கு முன் போரான் மற்றும் துத்தநாக நுண்ணூட்டச் சத்துக்களை இலைவழித் தெளிக்கவும்.",
                "வேர் மண்டல ஈரப்பதத்தைக் காக்க சொட்டு நீர்ப் பாதையில் கரிம மூடாக்கு (mulch) இடவும்.",
            ]
        return [
            "Maintain managed beehive density (2–3 hives/acre) during bloom for optimal nut set.",
            "Implement regulated deficit irrigation during hull-split to suppress Navel Orangeworm and Hull Rot.",
            "Apply foliar boron and zinc prior to flowering to support pollen tube growth.",
            "Mulch tree drip-lines to buffer soil moisture fluctuations and protect shallow root networks.",
        ]
    elif "rice" in crop:
        if lang == "ta":
            return [
                "தூர் கட்டும் பருவத்தில் 3–5 செ.மீ நீர் மட்டத்தைப் பராமரித்து, நடுப்பருவ வடிகால் செய்யவும்.",
                "தூர் கட்டும் மற்றும் கதிர் உருவாகும் நிலைகளில் தழைச்சத்தை (Nitrogen) பிரித்து இடவும்.",
                "இலை வண்ண அட்டை (LCC) கொண்டு மேலுர அளவைத் துல்லியமாகத் தீர்மானிக்கவும்.",
                "காய்ச்சலும் பாய்ச்சலும் (AWD) பாசன முறையைப் பின்பற்றி நீரைச் சேமிக்கவும்.",
            ]
        return [
            "Maintain a shallow 3–5 cm standing water layer during tillering, followed by mid-season drainage.",
            "Apply split nitrogen fertilizer at tillering and panicle initiation to maximize filled grain count.",
            "Monitor leaf color chart (LCC) to adjust top-dressing fertilizer rates precisely.",
            "Use alternate wetting and drying (AWD) irrigation to save water while maintaining yield.",
        ]
    elif "sugarcane" in crop:
        if lang == "ta":
            return [
                "சர்க்கரைச் சத்து (sucrose) அதிகரிக்க அறுவடைக்கு 4–6 வாரங்களுக்கு முன் பாசனத்தைக் கட்டுப்படுத்தவும்.",
                "கரும்புப் பார் இடைவெளியில் தோகை மூடாக்கு (trash mulching) இட்டு ஈரப்பதத்தைக் காக்கவும்.",
                "இளம்பயிர் வளர்ச்சிப் பருவத்தில் இரும்பு மற்றும் துத்தநாக நுண்ணூட்டத் தெளிப்பு மேற்கொள்ளவும்.",
                "மழைக்காலத்தில் நீர் தேங்காமல் இருக்க முறையான வடிகால் வசதியை உறுதி செய்யவும்.",
            ]
        return [
            "Schedule regulated water stress 4–6 weeks before harvest to promote sucrose synthesis.",
            "Perform trash mulching between cane rows to preserve moisture and suppress weeds.",
            "Apply micro-nutrient foliar spray (iron and zinc) during early vegetative growth.",
            "Ensure effective subsurface drainage to prevent waterlogging during monsoon periods.",
        ]

    if lang == "ta":
        return [
            f"{req.crop_type.title()} பயிரின் பூக்கும் மற்றும் காய் பிடிக்கும் பருவங்களில் பாசன நேரத்தை முறைப்படுத்தவும்.",
            f"{req.soil_type.title()} மண்ணிற்கு ஏற்ற தழை-மணி-சாம்பல் (N-P-K) உர அளவை மண் பரிசோதனை மூலம் இடவும்.",
            "மண் ஈரப்பதத்தை நிலைநிறுத்தவும் வெப்ப அழுத்தத்தைக் குறைக்கவும் கரிம மூடாக்கு (mulch) இடவும்.",
            "பயிர் சார்ந்த பூச்சி மற்றும் நோய் அறிகுறிகளைத் தொடக்கத்திலேயே கண்காணித்து கட்டுப்படுத்தவும்.",
        ]

    return [
        f"Optimize irrigation timing for {req.crop_type} during critical flowering and grain-filling stages.",
        f"Conduct soil nutrient testing to balance N-P-K formulation for {req.soil_type} soil.",
        "Apply organic mulch to stabilize soil moisture and mitigate temperature spikes.",
        "Monitor field regularly for early signs of crop-specific pests and physiological stress.",
    ]


async def predict_yield(req: YieldEstimatorRequest) -> YieldEstimatorResponse:
    """Compute crop yield estimate, confidence interval, and crop-specific drivers 100% deterministically."""
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
    else:
        estimated_per_ha = baseline * soil_m * irr_m * weather_m

    total_yield = round(estimated_per_ha * req.field_size_hectares, 2)

    # Confidence interval
    window = _CONFIDENCE_WINDOW.get(_key(req.weather_condition), 0.15)
    low  = round(total_yield * (1 - window), 2)
    high = round(total_yield * (1 + window), 2)
    if (getattr(req, "language", "en") or "en").lower() == "ta":
        confidence_range = f"{low} – {high} டன்"
    else:
        confidence_range = f"{low} – {high} tons"

    drivers = _deterministic_drivers(req, soil_m, irr_m, weather_m)
    suggestions = _deterministic_suggestions(req, soil_m, irr_m, weather_m)

    return YieldEstimatorResponse(
        estimated_yield_tons=total_yield,
        confidence_range=confidence_range,
        key_yield_drivers=drivers,
        optimization_suggestions=suggestions,
    )



