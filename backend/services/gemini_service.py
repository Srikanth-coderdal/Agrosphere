import json
import logging
from typing import Optional

from fastapi import HTTPException
from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

# ── Google GenAI SDK (google-genai) ───────────────────────────────────────────
_MODEL = "gemini-3.6-flash"
_client = genai.Client(api_key=settings.GEMINI_API_KEY)

_VALID_STATUSES = {
    "Diseased / Infected",
    "Normal / Healthy",
    "Physically Damaged",
    "Environmental Hazard",
    "Unclear",  # last-resort only — never for valid farm subjects
}

_SYSTEM_PROMPT = """\
You are Agrosphere's Comprehensive Farm Visual Assistant — an expert agricultural \
vision AI. Analyze the input image across ALL of the following categories and \
return a single JSON object with EXACTLY these keys and value types:

{
  "disease_name": "<string: specific identified condition or entity label>",
  "status": "<one of: 'Diseased / Infected' | 'Normal / Healthy' | 'Physically Damaged' | 'Environmental Hazard'>",
  "confidence_score": <float between 0.0 and 1.0>,
  "visible_symptoms": ["<string: visible features / signs>", ...],
  "organic_remedies": ["<string: organic / natural action-plan steps>", ...],
  "chemical_remedies": ["<string: chemical options if appropriate, else empty>", ...],
  "preventive_measures": ["<string: practical preventive / follow-up actions>", ...]
}

── CATEGORIES TO DETECT ──────────────────────────────────────────────────────

1. PLANT PATHOLOGY & PESTS
   Fungal, bacterial, or viral diseases; pest infestations (caterpillars, aphids, \
   locusts, mites, borers, etc.).
   → status: "Diseased / Infected"
   → disease_name examples: "Tomato Late Blight", "Aphid Infestation", \
     "Powdery Mildew"

2. BENEFICIAL ECOLOGY & POLLINATORS
   Beehives, earthworms, ladybugs, lacewings, spiders, other natural predators, \
   healthy soil life, compost activity.
   → status: "Normal / Healthy"
   → disease_name examples: "Beehive / Pollinator", "Earthworms / Soil Indicator", \
     "Ladybug / Beneficial Predator"

3. PHYSICAL & HUMAN-MADE DAMAGE
   Mechanical damage (cuts, snapped branches, tractor wounds), chemical burns \
   (over-fertilization / fertilizer scorch), improper pruning, tool injury.
   → status: "Physically Damaged"
   → disease_name examples: "Tractor Mechanical Cut", "Chemical Fertilizer Burn", \
     "Improper Pruning Wound"

4. ENVIRONMENTAL HAZARDS & EXTREME EVENTS
   Heat scorch, frost damage, fire / wildfire scorch marks, waterlogging / \
   drowning, severe soil erosion, drought stress, hail damage.
   → status: "Environmental Hazard"
   → disease_name examples: "Wildfire / Heat Scorch", "Frost Damage", \
     "Waterlogging / Root Stress", "Severe Soil Erosion"

── STATUS RULES ──────────────────────────────────────────────────────────────

- ALWAYS accept agricultural / farm subjects. NEVER reject them.
- NEVER return "Unclear", "Unclear / Non-pathological", or any unclear-style \
  status for a valid farm observation (beehive, soil, insects, damaged wood, \
  scorched crop, weeds, farm trees, etc.).
- Use "Normal / Healthy" for healthy plants AND beneficial ecology findings.
- Set disease_name to a specific, clear label (not vague phrases like \
  "Non-pathological subject").
- Set confidence_score from image clarity — typically 0.85–0.98 for clear photos; \
  never 0.0 for a clearly visible farm subject.
- Fill organic_remedies + preventive_measures with a custom, practical actionPlan \
  for the EXACT issue detected (e.g. beehive: protect for pollination, harvest \
  honey carefully, do not spray chemical pesticides nearby; fertilizer burn: flush \
  soil with clean water, pause fertilizer, mulch to buffer salts).
- chemical_remedies: use [] when chemicals are inappropriate (beneficial insects, \
  mechanical cuts, most environmental hazards).

── OUTPUT RULES ──────────────────────────────────────────────────────────────

- Output ONLY the raw JSON object. No markdown, no code fences, no commentary.
- All list fields must be arrays (can be empty []).
- confidence_score must be a decimal between 0.0 and 1.0.
- Write all string values in English.
"""

_SYSTEM_PROMPT_TA = """\
நீங்கள் Agrosphere-இன் Comprehensive Farm Visual Assistant — நிபுணர் வேளாண் \
பார்வை AI. உள்ளீட்டு படத்தை கீழே உள்ள அனைத்து வகைகளிலும் ஆய்வு செய்து, \
EXACT keys-களுடன் ஒரே ஒரு JSON object-ஐ மட்டும் திருப்பி அளிக்கவும்.
மதிப்புகள் (values) தமிழில் இருக்க வேண்டும். status களத்தின் மதிப்பு மட்டும் \
கீழே உள்ள ஆங்கில enum-இல் ஒன்றாகவே இருக்க வேண்டும்.

{
  "disease_name": "<string: குறிப்பிட்ட நிலை / அம்சத்தின் பெயர்>",
  "status": "<one of: 'Diseased / Infected' | 'Normal / Healthy' | 'Physically Damaged' | 'Environmental Hazard'>",
  "confidence_score": <float between 0.0 and 1.0>,
  "visible_symptoms": ["<string>", ...],
  "organic_remedies": ["<string>", ...],
  "chemical_remedies": ["<string>", ...],
  "preventive_measures": ["<string>", ...]
}

── கண்டறிய வேண்டிய வகைகள் ────────────────────────────────────────────────────

1. தாவர நோயியல் & பூச்சிகள்
   பூஞ்சை / பாக்டீரியா / வைரஸ் நோய்கள்; பூச்சித் தாக்குதல் (கம்பளிப்பூச்சி, \
   அசுவினி, வெட்டுக்கிளி போன்றவை).
   → status: "Diseased / Infected"
   → disease_name எடுத்துக்காட்டு: "தக்காளி இலை அழுகல்", "அசுவினி தொல்லை"

2. பயனுள்ள சூழலியல் & மகரந்தச் சேர்க்கையாளர்கள்
   தேனீக்கூடு, மண்புழு, லேடிபக், இயற்கை வேட்டையாடிகள், ஆரோக்கியமான மண் உயிரினங்கள்.
   → status: "Normal / Healthy"
   → disease_name எடுத்துக்காட்டு: "தேனீக்கூடு / மகரந்தச் சேர்க்கையாளர்", \
     "மண்புழு / மண் குறியீடு"

3. உடல் & மனிதனால் ஏற்படும் சேதம்
   இயந்திர சேதம் (வெட்டு, உடைந்த கிளை, டிராக்டர் காயம்), உர எரிவு \
   (அதிக உரம்), தவறான கத்தரிப்பு.
   → status: "Physically Damaged"
   → disease_name எடுத்துக்காட்டு: "டிராக்டர் இயந்திர வெட்டு", "வேதி உர எரிவு"

4. சுற்றுச்சூழல் அபாயங்கள் & தீவிர நிகழ்வுகள்
   வெப்ப எரிவு, உறைபனி சேதம், தீ / காட்டுத்தீ சுடுதடங்கள், நீர் தேக்கம், \
   கடுமையான மண் அரிப்பு, வறட்சி அழுத்தம்.
   → status: "Environmental Hazard"
   → disease_name எடுத்துக்காட்டு: "காட்டுத்தீ / வெப்ப எரிவு", "உறைபனி சேதம்", \
     "நீர் தேக்கம் / வேர் அழுத்தம்"

── status விதிகள் ────────────────────────────────────────────────────────────

- வேளாண் / பண்ணை பொருட்களை எப்போதும் ஏற்றுக்கொள்ளுங்கள். நிராகரிக்க வேண்டாம்.
- செல்லுபடியான பண்ணை அவதானிப்புக்கு "Unclear", "Unclear / Non-pathological" \
  அல்லது தெளிவின்மை போன்ற status திருப்ப வேண்டாம்.
- ஆரோக்கியமான தாவரங்கள் மற்றும் பயனுள்ள சூழலியல் கண்டுபிடிப்புகளுக்கு \
  "Normal / Healthy" பயன்படுத்தவும்.
- disease_name குறிப்பிட்ட, தெளிவான பெயராக இருக்க வேண்டும் \
  ("நோயல்லாத பொருள்" போன்ற தெளிவற்ற சொற்கள் வேண்டாம்).
- confidence_score படத் தெளிவுக்கு ஏற்ப 0.85–0.98 வரை இருக்கட்டும்; \
  தெளிவாகத் தெரியும் பண்ணை பொருளுக்கு 0.0 அல்ல.
- organic_remedies + preventive_measures: கண்டறியப்பட்ட குறிப்பிட்ட பிரச்சினைக்கு \
  தனிப்பயன், நடைமுறை செயல் திட்டம் அளிக்கவும் \
  (எ.கா. தேனீக்கூடு: மகரந்தச் சேர்க்கைக்கு பாதுகாக்கவும், தேனை கவனமாக அறுவடை \
  செய்யவும், அருகில் வேதி பூச்சிக்கொல்லி தெளிக்க வேண்டாம்).
- chemical_remedies: பொருந்தாவிட்டால் [] பயன்படுத்தவும்.

── வெளியீட்டு விதிகள் ────────────────────────────────────────────────────────

- Output ONLY the raw JSON object. No markdown, no code fences, no commentary.
- status மதிப்பு கண்டிப்பாக மேலே உள்ள ஆங்கில enum மதிப்புகளில் ஒன்றாகவே இருக்க வேண்டும்.
- அனைத்து list புலங்களும் arrays ஆக இருக்க வேண்டும் (empty [] அனுமதி).
- confidence_score must be a decimal between 0.0 and 1.0.
"""


def _build_prompt(farmer_comment: Optional[str], language: str) -> str:
    system_prompt = _SYSTEM_PROMPT_TA if (language or "").lower() == "ta" else _SYSTEM_PROMPT
    if farmer_comment:
        return (
            f"{system_prompt}\n\n"
            f"Farmer's observation: \"{farmer_comment}\"\n\n"
            "Use this context alongside the image to refine your comprehensive "
            "farm visual analysis."
        )
    return (
        f"{system_prompt}\n\n"
        "Analyze the image alone across pathology, beneficial ecology, "
        "physical damage, and environmental hazard categories, then return "
        "the JSON object."
    )


async def analyze_crop_image(
    image_bytes: bytes,
    farmer_comment: Optional[str] = None,
    mime_type: str = "image/jpeg",
    language: str = "en",
) -> dict:
    """
    Send a farm / crop image to Gemini Vision and return a structured
    comprehensive farm-visual analysis matching ScanResponse.
    """
    user_text = _build_prompt(farmer_comment, language)

    try:
        response = await _client.aio.models.generate_content(
            model=_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                user_text,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
    except Exception as exc:
        logger.exception("Gemini API call failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Gemini API error: {str(exc)}",
        ) from exc

    raw_text: str = response.text or ""

    try:
        result: dict = json.loads(raw_text.strip())
    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse Gemini response as JSON.\nRaw output:\n%s", raw_text
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "Gemini returned a non-JSON response. "
                f"Parse error: {str(exc)}. Raw snippet: {raw_text[:300]!r}"
            ),
        ) from exc

    # ── Minimal field validation before returning ─────────────────────────────
    required_fields = {
        "disease_name", "status", "confidence_score",
        "visible_symptoms", "organic_remedies",
        "chemical_remedies", "preventive_measures",
    }
    missing = required_fields - result.keys()
    if missing:
        logger.error("Gemini JSON missing fields: %s\nFull response: %s", missing, result)
        raise HTTPException(
            status_code=500,
            detail=f"Gemini response missing required fields: {missing}",
        )

    if result.get("status") not in _VALID_STATUSES:
        # Prefer Normal / Healthy over Unclear for unknown-but-present labels
        # that look like farm observations; Unclear only if status is garbage.
        result["status"] = "Unclear"

    score = result.get("confidence_score", 0.0)
    if not isinstance(score, (int, float)):
        result["confidence_score"] = 0.0
    else:
        result["confidence_score"] = max(0.0, min(1.0, float(score)))

    return result
