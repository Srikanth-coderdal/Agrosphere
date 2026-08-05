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

_WATERING_BY_PLANT_TA: dict[str, tuple[float, float, str]] = {
    "succulent":   (0.2,  0.5,  "10–14 நாட்களுக்கு ஒருமுறை"),
    "cactus":      (0.1,  0.3,  "14–21 நாட்களுக்கு ஒருமுறை"),
    "basil":       (0.5,  1.0,  "2–3 நாட்களுக்கு ஒருமுறை"),
    "mint":        (0.5,  1.0,  "2–3 நாட்களுக்கு ஒருமுறை"),
    "tomato":      (2.0,  4.0,  "தினசரி அல்லது ஒவ்வொரு 2 நாளுக்கும்"),
    "pepper":      (1.5,  3.0,  "2 நாட்களுக்கு ஒருமுறை"),
    "lettuce":     (1.0,  2.0,  "2–3 நாட்களுக்கு ஒருமுறை"),
    "spinach":     (1.0,  2.0,  "2–3 நாட்களுக்கு ஒருமுறை"),
    "chili":       (1.5,  2.5,  "2 நாட்களுக்கு ஒருமுறை"),
    "fern":        (0.5,  1.0,  "2–3 நாட்களுக்கு ஒருமுறை; இலைகளை மிஸ்ட் செய்யவும்"),
    "aloe vera":   (0.2,  0.4,  "14 நாட்களுக்கு ஒருமுறை"),
    "default":     (0.8,  1.5,  "2–3 நாட்களுக்கு ஒருமுறை"),
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

_SOIL_MIX_TA: dict[str, str] = {
    "succulent":   "சக்குலென்ட்/கற்றாழை கலவை (50% கரடுமுரடான மணல் + 50% பாட்டிங் மண்)",
    "cactus":      "கற்றாழை கலவை (60% கரடுமுரடான மணல் + 40% பாட்டிங் மண்; நன்றாக வடிகால்)",
    "basil":       "பெர்லைட் உடன் லேசான பாட்டிங் மண் (70% பாட்டிங் மண் + 30% பெர்லைட்)",
    "mint":        "ஈரமாகவும் நன்றாக வடிகாலும் உள்ள கலவை (60% பாட்டிங் மண் + 20% கம்போஸ்ட் + 20% பெர்லைட்)",
    "tomato":      "சத்து மிகுந்த வளமான கலவை (50% பாட்டிங் மண் + 30% கம்போஸ்ட் + 20% பெர்லைட்)",
    "pepper":      "வளமான, நன்றாக வடிகால் கலவை (50% பாட்டிங் மண் + 30% கம்போஸ்ட் + 20% பெர்லைட்)",
    "lettuce":     "லேசான கலவை (60% பாட்டிங் மண் + 30% கம்போஸ்ட் + 10% வெர்மிகுலைட்)",
    "spinach":     "சத்து நிறைந்த கலவை (60% பாட்டிங் மண் + 30% கம்போஸ்ட் + 10% வெர்மிகுலைட்)",
    "chili":       "நன்றாக வடிகால் உள்ள வளமான கலவை (50% பாட்டிங் மண் + 30% கம்போஸ்ட் + 20% பெர்லைட்)",
    "fern":        "பீட் அடிப்படையிலான கலவை (40% பீட் + 40% பாட்டிங் மண் + 20% பெர்லைட்; ஈரமாக வைத்திருங்கள்)",
    "aloe vera":   "சக்குலென்ட் கலவை (50% கரடுமுரடான மணல் + 50% பாட்டிங் மண்; மிக நல்ல வடிகால்)",
    "default":     "அனைத்துக்கும் ஏற்ற பாட்டிங் மண் + வடிகாலுக்கு 20% பெர்லைட்",
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

_SPACE_TIPS_TA: dict[str, list[str]] = {
    "balcony": [
        "கட்டமைப்புச் சுமை குறைய இலகுவான தொட்டிகளை பயன்படுத்துங்கள்.",
        "காற்றில் பாதிக்கப்படும் செடிகளை பாதுகாப்பான மூலைகளில் வையுங்கள்.",
        "குறைந்த தரை இடத்தை அதிகரிக்க செங்குத்து (vertical) நடவு பெட்டிகளை பயன்படுத்துங்கள்.",
        "வெப்பநிலை மாற்றங்களை கவனியுங்கள் — பால்கனிகள் தரையை விட வேகமாக சூடாகும்.",
    ],
    "indoor": [
        "வாரத்திற்கு ஒருமுறை பானையை 90° திருப்பி வையுங்கள், எல்லா பக்கமும் சம வெளிச்சம் கிடைக்கும்.",
        "வீட்டின் உலர்ந்த காற்றை சமாளிக்க ஈரத்தட்டு (humidity tray) அல்லது இலைகளை மிஸ்ட் செய்யுங்கள்.",
        "பூஞ்சை/மோல்ட் பிரச்சனை வராமல் நல்ல காற்றோட்டம் இருக்கட்டும்.",
        "A/C காற்றோட்டம் அல்லது ஹீட்டர் அருகில் செடிகளை வைக்காதீர்கள்.",
    ],
    "rooftop": [
        "கோடை உச்சத்தில் நிழற்பாய் (shade cloth) பயன்படுத்தி வெப்ப அழுத்தத்தை குறைக்கவும்.",
        "காற்று வீசும்போது இலகுவான தொட்டிகள் நிலைத்திருக்கும் வகையில் உறுதியாக பொருத்துங்கள்.",
        "செடிகளை ஒன்றாக சேர்த்து வையுங்கள்; சிறிய காலநிலை (microclimate) உருவாகி நீர் இழப்பு குறையும்.",
        "மாடித்தளங்கள் UV அதிகமாக பெறும் — மேல் மண்ணில் மல்ச் (mulch) போடுங்கள்; ஈரப்பதம் நிலைக்கும்.",
    ],
}


def _plant_key(plant_type: str) -> str:
    return plant_type.strip().lower()


def _sunlight_assessment(plant_type: str, sunlight_hours: float, language: str) -> str:
    key = _plant_key(plant_type)
    min_h, ideal_h = _SUNLIGHT_THRESHOLDS.get(key, _SUNLIGHT_THRESHOLDS["default"])
    lang = (language or "").lower()
    if sunlight_hours < min_h:
        if lang == "ta":
            return (
                f"{plant_type.title()} குறைந்தது {min_h} மணி நேர சூரிய ஒளி தேவை; உங்கள் இடம் {sunlight_hours} மணி மட்டுமே தருகிறது. "
                "இயற்கை ஒளியை கூடுதலாக பெற grow light பயன்படுத்தலாம்."
            )
        return (
            f"{plant_type.title()} needs at least {min_h}h of sunlight but your space provides "
            f"{sunlight_hours}h. Consider a grow light to supplement natural light."
        )
    elif sunlight_hours >= ideal_h:
        if lang == "ta":
            return (
                f"அருமை! உங்கள் {sunlight_hours} மணி சூரிய ஒளி {plant_type.title()} க்கு தேவையான சிறந்த {ideal_h} மணி நேரத்தை பூர்த்தி செய்கிறது. "
                "கூடுதல் விளக்கு தேவையில்லை."
            )
        return (
            f"Excellent! Your {sunlight_hours}h of sunlight meets the ideal {ideal_h}h needed for "
            f"{plant_type.title()}. No supplemental lighting required."
        )
    else:
        if lang == "ta":
            return (
                f"உங்கள் இடம் {sunlight_hours} மணி சூரிய ஒளி தருகிறது — {plant_type.title()} க்கு போதுமானது "
                f"(குறைந்தது {min_h} மணி, சிறந்தது {ideal_h} மணி). கிடைக்கும் மிக روشنமான இடத்தில் வையுங்கள்."
            )
        return (
            f"Your space provides {sunlight_hours}h of sunlight — adequate for {plant_type.title()} "
            f"(minimum {min_h}h, ideal {ideal_h}h). Place the plant in the brightest spot available."
        )


def _watering_advice(plant_type: str, container_size: float, language: str) -> str:
    key = _plant_key(plant_type)
    lang = (language or "").lower()
    if lang == "ta":
        min_l, max_l, freq = _WATERING_BY_PLANT_TA.get(key, _WATERING_BY_PLANT_TA["default"])
    else:
        min_l, max_l, freq = _WATERING_BY_PLANT.get(key, _WATERING_BY_PLANT["default"])
    # Scale water to container size (baseline assumes ~10L container)
    scale = container_size / 10.0
    scaled_min = round(min_l * scale, 2)
    scaled_max = round(max_l * scale, 2)
    if lang == "ta":
        return (
            f"{freq}. உங்கள் {container_size}L கொண்ட தொட்டிக்கு ஒவ்வொரு முறையும் சுமார் {scaled_min}–{scaled_max} லிட்டர் நீர். "
            "மண் ஈரப்பதத்தை 2 செ.மீ ஆழத்தில் சோதிக்கவும் — மண் வறண்ட பிறகு மட்டுமே நீர் ஊற்றவும்."
        )
    return (
        f"{freq}. For your {container_size}L container: apply approximately "
        f"{scaled_min}–{scaled_max} liters per watering. "
        "Check soil moisture 2cm deep — water only when dry."
    )


def _care_schedule(plant_type: str, space_type: str, language: str) -> str:
    key = _plant_key(plant_type)
    _, ideal_h = _SUNLIGHT_THRESHOLDS.get(key, _SUNLIGHT_THRESHOLDS["default"])
    lang = (language or "").lower()
    if lang == "ta":
        return (
            f"{plant_type.title()} க்கு {space_type} இடத்தில் வாராந்திர நடைமுறை: "
            "1–2 நாட்களுக்கு ஒருமுறை மண் ஈரப்பதத்தை சரிபார்க்கவும். "
            "பூச்சிகளுக்காக இலைகளை வாரம் ஒருமுறை பார்க்கவும். "
            "வளர்ச்சி காலத்தில் 2–4 வாரத்திற்கு ஒருமுறை சமநிலை திரவ உரம் (liquid fertilizer) போடுங்கள். "
            f"மாதம் ஒருமுறை உலர்ந்த இலைகளை வெட்டுங்கள். தினசரி {ideal_h} மணி சூரிய ஒளி இலக்காக வைத்துக்கொள்ளுங்கள்."
        )
    return (
        f"Weekly routine for {plant_type.title()} on {space_type}: "
        f"Check soil moisture every 1–2 days. Inspect leaves for pests weekly. "
        f"Fertilize with balanced liquid fertilizer every 2–4 weeks during growing season. "
        f"Prune dead leaves monthly. Target {ideal_h}h of daily sunlight."
    )


def advise_urban_gardening(req: UrbanGardeningRequest) -> UrbanGardeningResponse:
    lang = (getattr(req, "language", "en") or "en").lower()
    key = _plant_key(req.plant_type)
    tips_map = _SPACE_TIPS_TA if lang == "ta" else _SPACE_TIPS
    tips: list[str] = list(tips_map.get(req.space_type, []))

    # Add container-size-specific tip
    if req.container_size < 5:
        if lang == "ta":
            tips.append(
                f"உங்கள் {req.container_size} லிட்டர் கொண்ட தொட்டி சிறியது — அது வேகமாக காய்வதால் அதிகமாக நீர் ஊற்ற வேண்டும். "
                "வேர் வளர்ச்சிக்கு குறைந்தது 10 லிட்டர் தொட்டிக்கு மாற்ற பரிசீலிக்கவும்."
            )
        else:
            tips.append(
                f"Your {req.container_size}L container is small — "
                "water more frequently as it dries out faster. "
                "Consider repotting to at least a 10L container for better root development."
            )
    elif req.container_size > 30:
        if lang == "ta":
            tips.append(
                f"பெரிய {req.container_size} லிட்டர் தொட்டிகள் நீரை நீண்ட நேரம் வைத்திருக்கும் — வேர் அழுகல் வராமல் இருக்க நீர் ஊற்றுவதற்கு முன் மண் மேல் 3–5 செ.மீ வறங்கிய பிறகு ஊற்றுங்கள்."
            )
        else:
            tips.append(
                f"Large {req.container_size}L containers retain moisture longer — "
                "let the top 3–5 cm of soil dry before watering to prevent root rot."
            )

    if lang == "ta":
        soil_mix = _SOIL_MIX_TA.get(key, _SOIL_MIX_TA["default"])
    else:
        soil_mix = _SOIL_MIX.get(key, _SOIL_MIX["default"])

    return UrbanGardeningResponse(
        care_schedule=_care_schedule(req.plant_type, req.space_type, req.language),
        watering_frequency=_watering_advice(req.plant_type, req.container_size, req.language),
        sunlight_recommendations=_sunlight_assessment(req.plant_type, req.sunlight_hours, req.language),
        soil_mix=soil_mix,
        actionable_tips=tips,
    )
