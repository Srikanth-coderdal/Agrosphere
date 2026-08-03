import json
import logging
from typing import Optional

from fastapi import HTTPException
from google import genai
from google.genai import types

from config import settings
from schemas.irrigation import IrrigationRequest, IrrigationResponse

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)
MODEL_ID = "gemini-2.0-flash"

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

    Formula:
      ETo  = f(temperature)
      Kc   = crop coefficient for (crop, stage)
      ETc  = ETo * Kc                          [mm/day consumptive use]
      Deficit = ETc * (1 - soil_moisture/100)  [moisture already present]
      Soil retention factor reduces gross need for clay vs sandy soils
      Volume = Deficit * field_size_ha * 10000 [m² per ha] / retention_factor
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
    # 1 mm over 1 m² = 1 litre; 1 ha = 10,000 m²
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


async def _get_gemini_advice(req: IrrigationRequest, water_liters: float, et_index: str) -> dict:
    prompt = f"""
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
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    config = types.GenerateContentConfig(
        system_instruction=_GEMINI_SYSTEM,
        temperature=0.3,
        response_mime_type="application/json",
    )
    try:
        response = await _client.aio.models.generate_content(
            model=MODEL_ID, contents=contents, config=config
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
