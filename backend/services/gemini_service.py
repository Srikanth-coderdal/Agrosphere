import json
import logging
from typing import Optional

from fastapi import HTTPException
import google.generativeai as genai

from config import settings

logger = logging.getLogger(__name__)

# ── Configure Legacy Gemini SDK ───────────────────────────────────────────────
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')

_SYSTEM_PROMPT = """\
You are an expert agricultural plant pathologist AI.
Analyze the provided crop leaf image and return a diagnosis strictly as a \
single JSON object with EXACTLY these keys and value types:

{
  "disease_name": "<string: disease name or 'Healthy'>",
  "status": "<one of: 'Healthy' | 'Diseased' | 'Unclear'>",
  "confidence_score": <float between 0.0 and 1.0>,
  "visible_symptoms": ["<string>", ...],
  "organic_remedies": ["<string>", ...],
  "chemical_remedies": ["<string>", ...],
  "preventive_measures": ["<string>", ...]
}

Rules:
- Output ONLY the raw JSON object. No markdown, no code fences, no commentary.
- If the image is unclear or not a crop leaf, set status to "Unclear".
- All list fields must be arrays (can be empty []).
- confidence_score must be a decimal between 0.0 and 1.0.
"""

_SYSTEM_PROMPT_TA = """\
நீங்கள் ஒரு நிபுணர் வேளாண் தாவர நோய் கண்டறிதல் AI.
கொடுக்கப்பட்ட பயிர் இலை புகைப்படத்தை ஆய்வு செய்து, கீழே உள்ள EXACT keys-களுடன் ஒரே ஒரு JSON object-ஐ மட்டும் திருப்பி அளிக்கவும்.
மதிப்புகள் (values) தமிழில் (தமிழ்நாடு விவசாயர்களுக்கு எளிதாக புரியும் விதத்தில்) இருக்க வேண்டும்.

{
  "disease_name": "<string: நோயின் பெயர் அல்லது 'Healthy'>",
  "status": "<one of: 'Healthy' | 'Diseased' | 'Unclear'>",
  "confidence_score": <float between 0.0 and 1.0>,
  "visible_symptoms": ["<string>", ...],
  "organic_remedies": ["<string>", ...],
  "chemical_remedies": ["<string>", ...],
  "preventive_measures": ["<string>", ...]
}

Rules:
- Output ONLY the raw JSON object. No markdown, no code fences, no commentary.
- status மதிப்பு கண்டிப்பாக 'Healthy' | 'Diseased' | 'Unclear' இவற்றில் ஒன்றாகவே இருக்க வேண்டும்.
- படம் தெளிவில்லையெனில் அல்லது பயிர் இலை அல்ல எனில் status ஐ "Unclear" என்று அமைக்கவும்.
- அனைத்து list புலங்களும் arrays ஆக இருக்க வேண்டும் (empty [] அனுமதி).
- confidence_score must be a decimal between 0.0 and 1.0.
"""


def _build_prompt(farmer_comment: Optional[str], language: str) -> str:
    system_prompt = _SYSTEM_PROMPT_TA if (language or "").lower() == "ta" else _SYSTEM_PROMPT
    if farmer_comment:
        return (
            f"{system_prompt}\n\n"
            f"Farmer's observation: \"{farmer_comment}\"\n\n"
            "Use this context alongside the image to refine your diagnosis."
        )
    return f"{system_prompt}\n\nDiagnose the crop disease from the image alone."


async def analyze_crop_image(
    image_bytes: bytes,
    farmer_comment: Optional[str] = None,
    mime_type: str = "image/jpeg",
    language: str = "en",
) -> dict:
    """
    Send a crop leaf image to Gemini Vision and return a structured
    diagnosis dict matching the ScanResponse schema.
    """
    user_text = _build_prompt(farmer_comment, language)

    image_part = {
        "mime_type": mime_type,
        "data": image_bytes
    }

    try:
        # Call legacy SDK asynchronously
        response = await model.generate_content_async(
            [image_part, user_text],
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
            }
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

    valid_statuses = {"Healthy", "Diseased", "Unclear"}
    if result.get("status") not in valid_statuses:
        result["status"] = "Unclear"

    score = result.get("confidence_score", 0.0)
    if not isinstance(score, (int, float)):
        result["confidence_score"] = 0.0
    else:
        result["confidence_score"] = max(0.0, min(1.0, float(score)))

    return result
