"""
Rule-based deterministic Urban Gardening Advisor.
No external LLM calls — pure Python logic.
"""
from schemas.urban_gardening import UrbanGardeningRequest, UrbanGardeningResponse

# ── Watering rules: (min_liters_per_week, max_liters_per_week, frequency_label) ─
_WATERING_BY_PLANT: dict[str, tuple[float, float, str]] = {
    "succulent":   (0.2,  0.5,  "Once every 10–14 days"),
    "cactus":      (0.1,  0.3,  "Once every 14–21 days"),
    "basil":       (0.5,  1.0,  "Every 2–3 days"),
    "mint":        (0.5,  1.0,  "Every 2–3 days"),
    "tomato":      (2.0,  4.0,  "Daily or every other day"),
    "pepper":      (1.5,  3.0,  "Every 2 days"),
    "lettuce":     (1.0,  2.0,  "Every 2–3 days"),
    "spinach":     (1.0,  2.0,  "Every 2–3 days"),
    "chili":       (1.5,  2.5,  "Every 2 days"),
    "fern":        (0.5,  1.0,  "Every 2–3 days, mist leaves"),
    "aloe vera":   (0.2,  0.4,  "Once every 14 days"),
    "default":     (0.8,  1.5,  "Every 2–3 days"),
}

# ── Sunlight suitability thresholds ──────────────────────────────────────────
_SUNLIGHT_THRESHOLDS: dict[str, tuple[float, float]] = {
    # plant_key: (min_hours, ideal_hours)
    "succulent":   (4.0, 6.0),
    "cactus":      (6.0, 8.0),
    "basil":       (6.0, 8.0),
    "mint":        (4.0, 6.0),
    "tomato":      (7.0, 9.0),
    "pepper":      (6.0, 8.0),
    "lettuce":     (3.0, 5.0),
    "spinach":     (3.0, 5.0),
    "chili":       (6.0, 8.0),
    "fern":        (1.0, 3.0),
    "aloe vera":   (4.0, 6.0),
    "default":     (4.0, 6.0),
}

# ── Soil mix recommendations ──────────────────────────────────────────────────
_SOIL_MIX: dict[str, str] = {
    "succulent":   "Cactus/succulent mix (50% coarse sand + 50% potting soil)",
    "cactus":      "Cactus mix (60% coarse sand + 40% potting soil, well-draining)",
    "basil":       "Light potting mix with perlite (70% potting soil + 30% perlite)",
    "mint":        "Moist, well-draining mix (60% potting soil + 20% compost + 20% perlite)",
    "tomato":      "Rich, fertile mix (50% potting soil + 30% compost + 20% perlite)",
    "pepper":      "Fertile, draining mix (50% potting soil + 30% compost + 20% perlite)",
    "lettuce":     "Light mix (60% potting soil + 30% compost + 10% vermiculite)",
    "spinach":     "Nutrient-rich mix (60% potting soil + 30% compost + 10% vermiculite)",
    "chili":       "Well-draining fertile mix (50% potting soil + 30% compost + 20% perlite)",
    "fern":        "Peat-based mix (40% peat + 40% potting soil + 20% perlite, keep moist)",
    "aloe vera":   "Succulent mix (50% coarse sand + 50% potting soil, excellent drainage)",
    "default":     "All-purpose potting mix with 20% perlite for drainage",
}

# ── Space-based general tips ──────────────────────────────────────────────────
_SPACE_TIPS: dict[str, list[str]] = {
    "balcony": [
        "Use lightweight containers to reduce structural load.",
        "Place wind-sensitive plants in sheltered corners.",
        "Consider vertical planters to maximize limited floor space.",
        "Monitor temperature swings — balconies heat up faster than ground level.",
    ],
    "indoor": [
        "Rotate pots 90° weekly so all sides receive equal light.",
        "Use a humidity tray or mist leaves to compensate for dry indoor air.",
        "Ensure good airflow to prevent mold and fungal issues.",
        "Avoid placing plants near A/C vents or heating radiators.",
    ],
    "rooftop": [
        "Use shade cloth during peak summer to prevent heat stress.",
        "Anchor lightweight pots securely against wind.",
        "Group plants together to create a microclimate and reduce water loss.",
        "Rooftops receive intense UV — apply mulch on topsoil to retain moisture.",
    ],
}


def _plant_key(plant_type: str) -> str:
    return plant_type.strip().lower()


def _sunlight_assessment(plant_type: str, sunlight_hours: float) -> str:
    key = _plant_key(plant_type)
    min_h, ideal_h = _SUNLIGHT_THRESHOLDS.get(key, _SUNLIGHT_THRESHOLDS["default"])
    if sunlight_hours < min_h:
        return (
            f"{plant_type.title()} needs at least {min_h}h of sunlight but your space provides "
            f"{sunlight_hours}h. Consider a grow light to supplement natural light."
        )
    elif sunlight_hours >= ideal_h:
        return (
            f"Excellent! Your {sunlight_hours}h of sunlight meets the ideal {ideal_h}h needed for "
            f"{plant_type.title()}. No supplemental lighting required."
        )
    else:
        return (
            f"Your space provides {sunlight_hours}h of sunlight — adequate for {plant_type.title()} "
            f"(minimum {min_h}h, ideal {ideal_h}h). Place the plant in the brightest spot available."
        )


def _watering_advice(plant_type: str, container_size: float) -> str:
    key = _plant_key(plant_type)
    min_l, max_l, freq = _WATERING_BY_PLANT.get(key, _WATERING_BY_PLANT["default"])
    # Scale water to container size (baseline assumes ~10L container)
    scale = container_size / 10.0
    scaled_min = round(min_l * scale, 2)
    scaled_max = round(max_l * scale, 2)
    return (
        f"{freq}. For your {container_size}L container: apply approximately "
        f"{scaled_min}–{scaled_max} liters per watering. "
        "Check soil moisture 2cm deep — water only when dry."
    )


def _care_schedule(plant_type: str, space_type: str) -> str:
    key = _plant_key(plant_type)
    _, ideal_h = _SUNLIGHT_THRESHOLDS.get(key, _SUNLIGHT_THRESHOLDS["default"])
    return (
        f"Weekly routine for {plant_type.title()} on {space_type}: "
        f"Check soil moisture every 1–2 days. Inspect leaves for pests weekly. "
        f"Fertilize with balanced liquid fertilizer every 2–4 weeks during growing season. "
        f"Prune dead leaves monthly. Target {ideal_h}h of daily sunlight."
    )


def advise_urban_gardening(req: UrbanGardeningRequest) -> UrbanGardeningResponse:
    key = _plant_key(req.plant_type)
    tips: list[str] = list(_SPACE_TIPS.get(req.space_type, []))

    # Add container-size-specific tip
    if req.container_size < 5:
        tips.append(
            f"Your {req.container_size}L container is small — "
            "water more frequently as it dries out faster. "
            "Consider repotting to at least a 10L container for better root development."
        )
    elif req.container_size > 30:
        tips.append(
            f"Large {req.container_size}L containers retain moisture longer — "
            "let the top 3–5 cm of soil dry before watering to prevent root rot."
        )

    return UrbanGardeningResponse(
        care_schedule=_care_schedule(req.plant_type, req.space_type),
        watering_frequency=_watering_advice(req.plant_type, req.container_size),
        sunlight_recommendations=_sunlight_assessment(req.plant_type, req.sunlight_hours),
        soil_mix=_SOIL_MIX.get(key, _SOIL_MIX["default"]),
        actionable_tips=tips,
    )
