"""
Deterministic FAO-56 Smart Irrigation Service.
Runs 100% deterministically with zero LLM dependency.
"""
import logging

from schemas.irrigation import IrrigationRequest, IrrigationResponse

logger = logging.getLogger(__name__)

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


def _build_deterministic_irrigation_advice(
    req: IrrigationRequest,
    water_liters: float,
    et_mm: float,
    et_index: str,
) -> dict:
    """
    100% deterministic FAO-56 schedule, weather summary, and actionable tips.
    Zero LLM calls.
    """
    lang = (req.language or "en").strip().lower()
    temp = req.temperature_celsius if req.temperature_celsius is not None else 28.0
    rain_prob = req.rainfall_probability_percent if req.rainfall_probability_percent is not None else 20.0
    moisture = req.soil_moisture_percentage
    soil_key = (req.soil_type or "loam").strip().lower()
    crop_title = (req.crop_type or "Crop").strip().title()
    stage_label = (req.growth_stage or "mid-stage").strip()

    # Determine irrigation frequency based on soil retention & rainfall probability
    if rain_prob >= 70:
        freq_en = "every 2–3 days (reduce volume by 30% if rain occurs)"
        freq_ta = "ஒவ்வொரு 2–3 நாட்களும் (மழை பெய்தால் அளவை 30% குறைக்கவும்)"
    elif soil_key == "sandy" or temp >= 34:
        freq_en = "daily in two split cycles (06:00 AM and 05:30 PM)"
        freq_ta = "தினமும் இரண்டு முறை (காலை 06:00 மற்றும் மாலை 05:30)"
    elif soil_key == "clay":
        freq_en = "every 2 days at 06:00 AM"
        freq_ta = "ஒவ்வொரு 2 நாட்களுக்கும் காலை 06:00 மணிக்கு"
    else:
        freq_en = "daily at 06:00 AM"
        freq_ta = "தினமும் காலை 06:00 மணிக்கு"

    if lang == "ta":
        recommended_schedule = (
            f"{water_liters:,.0f} லிட்டர் நீரை {freq_ta} பாசனம் செய்யவும்."
        )
        weather_summary = (
            f"FAO-56 மாதிரியின்படி {temp:.1f}°C வெப்பநிலை மற்றும் {moisture:.0f}% மண் ஈரப்பதத்தில் "
            f"{crop_title} ({stage_label}) பயிருக்கான ஆவிப்போக்கல் {et_index} ஆக உள்ளது. "
            f"மழை வாய்ப்பு {rain_prob:.0f}% என்பதால் {req.field_size_hectares} ஹெக்டேர் வயலுக்கு "
            f"தினசரி {water_liters:,.0f} லிட்டர் நீர் தேவைப்படுகிறது."
        )
        tips = [
            f"ஆவியாதல் இழப்பைக் குறைக்க காலை 06:00–08:00 மணிக்குள் {water_liters:,.0f} லிட்டர் நீரைப் பாய்ச்சவும்.",
            f"{req.soil_type.title()} மண்ணின் ஈரப்பதம் தற்போது {moisture:.0f}% ஆக உள்ளது — வேர் மண்டலத்தைத் தொடர்ந்து கண்காணிக்கவும்.",
            (
                f"மழை வாய்ப்பு அதிகமாக ({rain_prob:.0f}%) உள்ளதால் மழை பெய்தால் பாசனத்தை ஒத்திவைக்கவும்."
                if rain_prob >= 50
                else f"வெப்பநிலை ({temp:.1f}°C) அதிகமாகும் போது மண் ஈரப்பதத்தைக் காக்க கரிம மூடாக்கு (mulch) இடவும்."
            ),
            "வயலில் நீர் தேங்குவதைத் தடுக்க முறையான வடிகால் வசதியை உறுதி செய்யவும்.",
        ]
        return {
            "recommended_schedule": recommended_schedule,
            "weather_summary": weather_summary,
            "actionable_tips": tips,
        }

    recommended_schedule = f"Apply {water_liters:,.0f} L {freq_en}."
    weather_summary = (
        f"FAO-56 evapotranspiration analysis at {temp:.1f}°C and {moisture:.0f}% soil moisture "
        f"indicates {et_index} water demand for {crop_title} ({stage_label}). "
        f"With {rain_prob:.0f}% rainfall probability across {req.field_size_hectares} ha of {soil_key} soil, "
        f"net daily irrigation requirement is {water_liters:,.0f} L."
    )
    tips = [
        f"Irrigate {water_liters:,.0f} L during early morning hours (06:00–08:00 AM) to minimize evaporative loss.",
        f"Monitor root-zone moisture in {soil_key} soil (currently {moisture:.0f}%) before each watering cycle.",
        (
            f"Rainfall probability is {rain_prob:.0f}% — delay scheduled irrigation if natural precipitation exceeds 5 mm."
            if rain_prob >= 50
            else f"Apply surface mulching to conserve soil moisture at {temp:.1f}°C ambient temperature."
        ),
        "Ensure clear field drainage channels to prevent root-zone waterlogging and nutrient leaching.",
    ]
    return {
        "recommended_schedule": recommended_schedule,
        "weather_summary": weather_summary,
        "actionable_tips": tips,
    }


async def calculate_irrigation(req: IrrigationRequest) -> IrrigationResponse:
    """Compute FAO-56 water requirement and deterministic irrigation schedule with zero LLM calls."""
    water_liters, et_mm = _compute_water_liters(req)
    et_index = _classify_et(et_mm)
    advice = _build_deterministic_irrigation_advice(req, water_liters, et_mm, et_index)

    return IrrigationResponse(
        water_required_liters=water_liters,
        recommended_schedule=advice["recommended_schedule"],
        evapotranspiration_index=et_index,
        weather_summary=advice["weather_summary"],
        actionable_tips=advice["actionable_tips"],
    )

