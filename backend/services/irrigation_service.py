import json
import logging
from typing import Optional

from fastapi import HTTPException
import google.generativeai as genai

from config import settings
from schemas.irrigation import IrrigationRequest, IrrigationResponse

logger = logging.getLogger(__name__)

# ── Configure Legacy Gemini SDK ───────────────────────────────────────────────
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')

# ── Crop base ET (mm/day) by growth stage ─────────────────────────────────────
# Source: FAO-56 Kc values (simplified)
_CROP_KC: dict[str, dict[str, float]] = {
    "tomato":   {"initial": 0.6,  "crop development": 0.75, "mid-stage": 1.15, "late stage": 0.8},
    "wheat":    {"initial": 0.3,  "crop development": 0.7,  "mid-stage": 1.15, "late stage": 0.4},
    "maize":    {"initial": 0.3,  "crop development": 0.7,  "mid-stage": 1.2,  "late stage": 0.6},
    "rice":     {"initial": 1.05, "crop development": 1.1,  "mid-stage": 1.2,  "late stage": 0.9},
    "default":  {"initial": 0.5,  "crop development": 0.75, "mid-stage": 1.0,  "late stage": 0.75},
}

# Soil moisture retention factors (higher = retains more water, needs less irrigation)
_SOIL_RETENTION: dict[str, float] = {
    "clay":  0.85,
    "silty": 0.75,
    "loam":  0.65,
    "sandy": 0.45,
}

# Reference ETo (mm/day) driven by temperature (Hargreaves simplified approximation)
def _reference_eto(temp_c: float) -> float:
    """Simplified ETo estimate using temperature (Hargreaves-like proxy)."""
    return max(1.0, 0.17 * (temp_c ** 0.75))


def _classify_et(et_mm: float) -> str:
    if et_mm < 3.0:
        return f"Low ({et_mm:.1f} mm/day)"
    elif et_mm < 5.5:
        return f"Moderate ({et_mm:.1f} mm/day)"
    else:
        return f"High ({et_mm:.1f} mm/day)"


def _compute_water_liters(req: IrrigationRequest) -> tuple[float, float]:
    """
    Returns (water_required_liters, et_mm_per_day).
    """
    crop_key = req.crop_type.lower()
    stage_key = req.growth_stage.lower()
    temp = req.temperature_celsius or 28.0

    kc_table = _CROP_KC.get(crop_key, _CROP_KC["default"])
    kc = kc_table.get(stage_key, 0.75)

    eto = _reference_eto(temp)
    etc = eto * kc  # mm/day

    # Soil moisture deficit (fraction of ETc still needed)
    moisture_fraction = req.soil_moisture_percentage / 100.0
    deficit_mm = etc * (1.0 - moisture_fraction)
    deficit_mm = max(0.0, deficit_mm)

    # Soil retention — clay retains more, sandy loses more
    soil_key = req.soil_type.lower()
    retention = _SOIL_RETENTION.get(soil_key, 0.65)

    # Convert mm deficit → liters over field area, adjusted for retention
    area_m2 = req.field_size_hectares * 10_000
    gross_water_liters = (deficit_mm / retention) * area_m2

    return round(gross_water_liters, 1), round(etc, 2)


_GEMINI_SYSTEM = """\
You are a precision agriculture irrigation expert AI.
Given structured crop and field data, produce a JSON object with EXACTLY these keys:
{
  "recommended_schedule": "<string: specific schedule e.g. 'Water 18,000 L at 06:00 AM every 2 days'>",
  "weather_summary": "<string: 2-3 sentence summary of conditions and their irrigation impact>",
  "actionable_tips": ["<tip 1>", "<tip 2>", "<tip 3>", "<tip 4>"]
}
Rules:
- Output ONLY the raw JSON object. No markdown, no code fences.
- recommended_schedule must include volume, time of day, and frequency.
- actionable_tips must have 3-5 items tailored to the inputs.
"""

_GEMINI_SYSTEM_TA = """\
நீங்கள் ஒரு துல்லிய வேளாண் நீர்ப்பாசன நிபுணர் AI.
கொடுக்கப்பட்ட பயிர் மற்றும் வயல் தரவுகளை வைத்து, கீழே உள்ள EXACT keys-களுடன் ஒரே ஒரு JSON object-ஐ திருப்புங்கள்:
{
  "recommended_schedule": "<string: உதாரணம் '18,000 லிட்டர் நீரை காலை 06:00 மணிக்கு ஒவ்வொரு 2 நாட்களும் பாசனம் செய்யவும்'>",
  "weather_summary": "<string: 2–3 வாக்கியங்களில் நிலைமைகள் மற்றும் அவற்றின் நீர்ப்பாசன தாக்கம்>",
  "actionable_tips": ["<tip 1>", "<tip 2>", "<tip 3>", "<tip 4>"]
}
விதிகள்:
- Output ONLY raw JSON. markdown இல்லை, code fences இல்லை.
- recommended_schedule இல் அளவு (volume), நாளின் நேரம் (time of day), மற்றும் அடுத்தடுத்து வரும் frequency இருக்க வேண்டும்.
- actionable_tips இல் உள்ளீடுகளுக்கு ஏற்ப 3–5 குறிப்புகள் தமிழில் இருக்க வேண்டும்.
"""


async def _get_gemini_advice(req: IrrigationRequest, water_liters: float, et_index: str) -> dict:
    system_prompt = _GEMINI_SYSTEM_TA if (req.language or "").lower() == "ta" else _GEMINI_SYSTEM
    prompt = f"""
{system_prompt}

Crop: {req.crop_type}
Growth Stage: {req.growth_stage}
Soil Type: {req.soil_type}
Field Size: {req.field_size_hectares} hectares
Current Soil Moisture: {req.soil_moisture_percentage}%
Temperature: {req.temperature_celsius}°C
Rainfall Probability: {req.rainfall_probability_percent}%
Calculated Water Requirement: {water_liters:,.0f} liters/day
Evapotranspiration Index: {et_index}
"""
    try:
        response = await model.generate_content_async(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.3,
            }
        )
    except Exception as exc:
        logger.exception("Gemini irrigation advice call failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}") from exc

    try:
        return json.loads((response.text or "").strip())
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Gemini irrigation JSON: %s", response.text)
        raise HTTPException(
            status_code=422,
            detail=f"Gemini returned invalid JSON: {exc}. Snippet: {(response.text or '')[:300]!r}",
        ) from exc


async def calculate_irrigation(req: IrrigationRequest) -> IrrigationResponse:
    """Compute water requirement and fetch AI-generated advice from Gemini."""
    water_liters, et_mm = _compute_water_liters(req)
    et_index = _classify_et(et_mm)

    gemini_data = await _get_gemini_advice(req, water_liters, et_index)

    return IrrigationResponse(
        water_required_liters=water_liters,
        recommended_schedule=gemini_data.get(
            "recommended_schedule",
            f"Apply {water_liters:,.0f} L per day in early morning.",
        ),
        evapotranspiration_index=et_index,
        weather_summary=gemini_data.get("weather_summary", "No weather summary available."),
        actionable_tips=gemini_data.get("actionable_tips", []),
    )
