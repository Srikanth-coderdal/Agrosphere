import json
import logging
from typing import Optional

from fastapi import HTTPException
from google import genai
from google.genai import types

from config import settings
from schemas.yield_estimator import YieldEstimatorRequest, YieldEstimatorResponse

logger = logging.getLogger(__name__)

# ── Google GenAI SDK (google-genai) ───────────────────────────────────────────
_MODEL = "gemini-3.6-flash"
_client = genai.Client(api_key=settings.GEMINI_API_KEY)

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


_GEMINI_SYSTEM_PROMPT = """\
You are an expert agronomist and precision crop yield optimization AI.
Analyze the user's crop, field size, soil classification, irrigation system, weather condition, and historical yield performance to generate crop-tailored key yield drivers and specific optimization suggestions.

CRITICAL Crop-Specific Guidelines:
1. RETURN KEY METRICS FIRST: Return key metrics (estimated target yield / drivers) immediately at the top of the JSON object before detailing other bullet points.
2. STRICT CROP-SPECIFICITY: All key yield drivers and optimization suggestions MUST be strictly customized to the entered crop (e.g., almond trees, rice, sugarcane, tomatoes, wheat, cotton, etc.).
3. NEVER RETURN GENERIC ADVICE: Do NOT provide generic statements such as "use certified seeds" for perennial tree crops (like almonds, apples, citrus, nuts) or generic agricultural platitudes that apply to all plants.
4. CROP-TAILORED KEY DRIVERS: Identify exact biological, physiological, environmental, and management drivers specific to the input crop:
   - For Almonds: winter chill hour accumulation, bloom-period bee pollination weather, hull-split irrigation deficit control, and navel orangeworm management.
   - For Rice: panicle initiation water depth, mid-season drainage, soil anaerobic conditions, and nitrogen top-dressing timing.
   - For Sugarcane: stalk elongation moisture, ratoon stubble management, borer prevention, and ripening sucrose concentration control.
   - For Tomato/Vegetables: blossom-end rot calcium regulation, indeterminate canopy pruning, pollinator activity, and deficit irrigation during fruit set.
5. SPECIFIC OPTIMIZATION STEPS: Provide concrete, practical optimization steps matching the exact crop growth model, crop type (annual grain, perennial nut tree, tuber, cash crop), and field environment provided.
6. Return ONLY a single raw JSON object matching this structure with no markdown formatting or code blocks:
{
  "key_yield_drivers": ["<crop-tailored driver 1>", "<crop-tailored driver 2>", "<crop-tailored driver 3>"],
  "optimization_suggestions": ["<crop-specific step 1>", "<crop-specific step 2>", "<crop-specific step 3>", "<crop-specific step 4>"]
}
"""

_GEMINI_SYSTEM_PROMPT_TA = """\
நீங்கள் ஒரு நிபுணர் வேளாண்மை மற்றும் பயிர் விளைச்சல் உகப்பாக்க AI.
வழங்கப்பட்ட பயிர், மண், பாசனம், காலநிலை தரவுகளை ஆய்வு செய்து, குறிப்பிட்ட பயிர்களுக்கான பிரத்யேக விளைச்சல் காரணிகள் மற்றும் உகப்பாக்க ஆலோசனைகளைத் தமிழில் JSON வடிவத்தில் வழங்கவும்.

முக்கிய விதிகள்:
1. RETURN KEY METRICS FIRST: விளைச்சல் காரணிகள் மற்றும் உகப்பாக்க ஆலோசனைகளை JSON இன் தொடக்கத்திலேயே முதலில் வழங்கவும்.
2. பயிர்-சார்ந்த பிரத்யேக ஆலோசனைகள்: அனைத்து காரணிகளும் பரிந்துரைகளும் குறிப்பிட்ட பயிருக்கு (எ.கா. பாதாம் மரங்கள், நெல், கரும்பு போன்றவை) மட்டுமே பொருந்தக்கூடியதாக இருக்க வேண்டும்.
3. பொதுவான ஆலோசனைகளை தவிர்க்கவும்: பாதாம் போன்ற பல்லாண்டு மர பயிர்களுக்கு "சான்றளிக்கப்பட்ட விதைகளைப் பயன்படுத்துங்கள்" போன்ற பொதுவான கருத்துகளை வழங்க வேண்டாம்.
4. பயிர்-சார்ந்த முக்கிய காரணிகள்: பயிரின் குறிப்பிட்ட வளர்ச்சி காரணிகளைத் தரவும் (எ.கா. பாதாம்: குளிர்கால சில் ஹவர்ஸ், பூக்கும் கால மகரந்தச் சேர்க்கை, ஹல்-ஸ்பிளிட் பாசனம்).
5. JSON வடிவம் மட்டுமே:
{
  "key_yield_drivers": ["<காரணி 1>", "<காரணி 2>", "<காரணி 3>"],
  "optimization_suggestions": ["<பரிந்துரை 1>", "<பரிந்துரை 2>", "<பரிந்துரை 3>", "<பரிந்துரை 4>"]
}
"""


def _fallback_drivers(req: YieldEstimatorRequest, soil_m: float, irr_m: float, weather_m: float) -> list[str]:
    drivers = []
    crop = req.crop_type.strip().title()
    lang = (getattr(req, "language", "en") or "en").lower()

    if "almond" in crop.lower():
        return [
            f"Winter chill hour fulfillment and bloom-phase temperature critical for {crop} fruit set.",
            f"Pollination efficiency during bloom period influencing kernel yield potential.",
            f"Hull-split deficit irrigation management regulating kernel quality and hull split timing.",
        ]
    elif "rice" in crop.lower():
        return [
            f"Standing water depth control during panicle initiation determining grain head size.",
            f"Solar radiation and canopy light interception during grain filling phase.",
            f"Soil nitrogen availability and leaf chlorophyll index prior to flowering.",
        ]
    elif "sugarcane" in crop.lower():
        return [
            f"Stalk elongation water availability driving total cane biomass production.",
            f"Pre-harvest maturation drying phase regulating Brix sucrose accumulation.",
            f"Ratoon stubble management and soil aeration supporting tiller density.",
        ]

    if lang == "ta":
        drivers.append(f"{crop} பயிருக்கான காலநிலை மற்றும் பாசன சமநிலை விளைச்சலை நிர்ணயிக்கிறது.")
        drivers.append(f"{req.soil_type.title()} மண் வகை மற்றும் {req.irrigation_type.title()} பாசன முறை.")
    else:
        drivers.append(f"{crop} physiological response to weather condition ({req.weather_condition}).")
        drivers.append(f"Water retention and root zone aeration in {req.soil_type} soil with {req.irrigation_type} irrigation.")

    return drivers


def _fallback_suggestions(req: YieldEstimatorRequest, soil_m: float, irr_m: float, weather_m: float) -> list[str]:
    crop = req.crop_type.strip().lower()

    if "almond" in crop:
        return [
            "Maintain managed beehive density (2–3 hives/acre) during bloom for optimal nut set.",
            "Implement regulated deficit irrigation during hull-split to suppress Navel Orangeworm and Hull Rot.",
            "Apply foliar boron and zinc prior to flowering to support pollen tube growth.",
            "Mulch tree drip-lines to buffer soil moisture fluctuations and protect shallow root networks.",
        ]
    elif "rice" in crop:
        return [
            "Maintain a shallow 3–5 cm standing water layer during tillering, followed by mid-season drainage.",
            "Apply split nitrogen fertilizer at tillering and panicle initiation to maximize filled grain count.",
            "Monitor leaf color chart (LCC) to adjust top-dressing fertilizer rates precisely.",
            "Use alternate wetting and drying (AWD) irrigation to save water while maintaining yield.",
        ]
    elif "sugarcane" in crop:
        return [
            "Schedule regulated water stress 4–6 weeks before harvest to promote sucrose synthesis.",
            "Perform trash mulching between cane rows to preserve moisture and suppress weeds.",
            "Apply micro-nutrient foliar spray (iron and zinc) during early vegetative growth.",
            "Ensure effective subsurface drainage to prevent waterlogging during monsoon periods.",
        ]

    return [
        f"Optimize irrigation timing for {req.crop_type} during critical flowering and grain-filling stages.",
        f"Conduct soil nutrient testing to balance N-P-K formulation for {req.soil_type} soil.",
        f"Apply organic mulch to stabilize soil moisture and mitigate temperature spikes.",
        f"Monitor field regularly for early signs of crop-specific pests and physiological stress.",
    ]


async def _get_gemini_yield_advice(req: YieldEstimatorRequest, estimated_per_ha: float) -> tuple[list[str], list[str]]:
    lang = (getattr(req, "language", "en") or "en").lower()
    system_prompt = _GEMINI_SYSTEM_PROMPT_TA if lang == "ta" else _GEMINI_SYSTEM_PROMPT

    prompt = f"""\
{system_prompt}

Crop Input Details:
- Crop Type: {req.crop_type}
- Field Size: {req.field_size_hectares} hectares
- Soil Type: {req.soil_type}
- Irrigation Method: {req.irrigation_type}
- Weather Condition: {req.weather_condition}
- Historical Yield: {req.historical_yield_tons} tons
- Estimated Target Yield: {estimated_per_ha:.2f} tons/hectare
"""
    try:
        response = await _client.aio.models.generate_content_stream(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=1024,
            ),
        )
        full_text = ""
        async for chunk in response:
            full_text += chunk.text or ""
        
        cleaned_text = full_text.strip()
        if cleaned_text.startswith("```"):
            lines = cleaned_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_text = "\n".join(lines).strip()

        data = json.loads(cleaned_text)
        drivers = data.get("key_yield_drivers", [])
        suggestions = data.get("optimization_suggestions", [])
        if drivers and suggestions:
            return drivers, suggestions
    except Exception as exc:
        logger.warning("Gemini yield advice generation failed or timed out: %s", exc)

    # Fallback to crop-specific deterministic suggestions if API fails/unconfigured
    return (
        _fallback_drivers(req, 1.0, 1.0, 1.0),
        _fallback_suggestions(req, 1.0, 1.0, 1.0),
    )


async def predict_yield(req: YieldEstimatorRequest) -> YieldEstimatorResponse:
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

    drivers, suggestions = await _get_gemini_yield_advice(req, estimated_per_ha)

    return YieldEstimatorResponse(
        estimated_yield_tons=total_yield,
        confidence_range=confidence_range,
        key_yield_drivers=drivers,
        optimization_suggestions=suggestions,
    )


