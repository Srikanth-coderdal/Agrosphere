import json
import base64
import logging
from typing import Optional

from fastapi import HTTPException
from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

# ── Gemini client (instantiated once at module load) ──────────────────────────
_client = genai.Client(api_key=settings.GEMINI_API_KEY)

MODEL_ID = "gemini-2.0-flash"

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


def _build_prompt(farmer_comment: Optional[str]) -> str:
    if farmer_comment:
        return (
            f"Farmer's observation: \"{farmer_comment}\"\n\n"
            "Use this context alongside the image to refine your diagnosis."
        )
    return "Diagnose the crop disease from the image alone."


async def analyze_crop_image(
    image_bytes: bytes,
    farmer_comment: Optional[str] = None,
    mime_type: str = "image/jpeg",
) -> dict:
    """
    Send a crop leaf image to Gemini Vision and return a structured
    diagnosis dict matching the ScanResponse schema.

    Args:
        image_bytes:    Raw bytes of the uploaded image.
        farmer_comment: Optional textual note from the farmer.
        mime_type:      MIME type of the image (default: image/jpeg).

    Returns:
        dict conforming to ScanResponse fields.

    Raises:
        HTTPException 422: If Gemini returns invalid / non-parseable JSON.
        HTTPException 502: If the Gemini API call itself fails.
    """
    user_text = _build_prompt(farmer_comment)

    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    text_part = types.Part.from_text(text=user_text)

    contents = [
        types.Content(
            role="user",
            parts=[image_part, text_part],
        )
    ]

    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT,
        temperature=0.2,          # low temperature → deterministic structured output
        response_mime_type="application/json",
    )

    try:
        response = await _client.aio.models.generate_content(
            model=MODEL_ID,
            contents=contents,
            config=config,
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
