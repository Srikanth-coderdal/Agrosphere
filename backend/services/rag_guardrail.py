import json
import logging
from typing import Optional, List
from fastapi import HTTPException
from google import genai
from google.genai import types

from config import settings
from schemas.diagnostic import VerifiedDiagnosticResponse, SafeDosage, WeatherSummary
from services.extension_db import query_extension_context

logger = logging.getLogger(__name__)

_MODEL = getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash")
_client = genai.Client(api_key=settings.GEMINI_API_KEY)

_BASE_PROMPT = """You are Agrosphere's Expert Agricultural Vision AI.IMPORTANT: For pre_harvest_interval_days, only output a value if the Extension Context explicitly states it. If it is not mentioned, output null. Do not estimate, infer, or use general knowledge for this field — an incorrect pre-harvest interval can cause real crop or food-safety harm.
Analyze the image and return a JSON object.

Based on the provided Extension Context, recommend verified treatments.
If no context is provided, provide general safe advice.

JSON format must match exactly:
{
  "pathogen": "<string>",
  "confidence": <float>,
  "verified_treatment": "<string: treatment plan>",
  "safe_dosages": [
    {
      "chemical_name": "<string>",
      "dosage": "<string>",
      "unit": "<string>",
      "max_frequency": "<string>",
            "pre_harvest_interval_days": <int or null — null if the Extension Context does not explicitly state a pre-harvest interval; never estimate or guess this value>
    }
  ],
  "organic_recommendations": ["<string>"],
  "preventive_measures": ["<string>"],
  "disclaimer": "<string: official disclaimer>",
  "is_verified": <bool: true if using extension context, false otherwise>
}
"""

_BASE_PROMPT_TA = """நீங்கள் Agrosphere-இன் நிபுணர் வேளாண் பார்வை AI.IMPORTANT: For pre_harvest_interval_days, only output a value if the Extension Context explicitly states it. If it is not mentioned, output null. Do not estimate, infer, or use general knowledge for this field — an incorrect pre-harvest interval can cause real crop or food-safety harm.
படத்தை ஆய்வு செய்து JSON-ஐ திருப்பி அளிக்கவும்.

JSON format:
{
  "pathogen": "<string>",
  "confidence": <float>,
  "verified_treatment": "<string: treatment plan>",
  "safe_dosages": [
    {
      "chemical_name": "<string>",
      "dosage": "<string>",
      "unit": "<string>",
      "max_frequency": "<string>",
            "pre_harvest_interval_days": <int or null — null if the Extension Context does not explicitly state a pre-harvest interval; never estimate or guess this value>
    }
  ],
  "organic_recommendations": ["<string>"],
  "preventive_measures": ["<string>"],
  "disclaimer": "<string: official disclaimer>",
  "is_verified": <bool>
}
"""

async def apply_guardrail(
    image_bytes: bytes,
    mime_type: str,
    crop_type: str,
    language: str = "en",
    farmer_comment: Optional[str] = None,
    operational_context: Optional[str] = None,
    weather_summary: Optional[WeatherSummary] = None,
) -> VerifiedDiagnosticResponse:
    
    # 1. Retrieve extension chunks from ChromaDB
    context = query_extension_context(crop_type, farmer_comment=farmer_comment)
    
    # 2. Inject context and target language into Gemini prompt
    system_prompt = _BASE_PROMPT_TA if language.lower() == 'ta' else _BASE_PROMPT
    
    prompt = f"{system_prompt}\n\n"
    prompt += f"Crop Type: {crop_type}\n"
    if operational_context:
        prompt += f"Operational Context Mode: {operational_context}\n"
    if weather_summary:
        prompt += f"Local Weather: Temp {weather_summary.temperature}, Rain Risk: {weather_summary.rain_chance}, Spray Note: {weather_summary.spray_advisory}\n"
    if farmer_comment:
        prompt += f"Farmer Comment: {farmer_comment}\n"
    prompt += f"\nExtension Context:\n{context if context else 'No specific context found. Provide general safe advice and set is_verified=false.'}\n"
    
    try:
        response = await _client.aio.models.generate_content(
            model=_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
    except Exception as exc:
        logger.exception("Gemini API call failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}") from exc
        
    raw_text: str = response.text or ""
    try:
        result: dict = json.loads(raw_text.strip())
        if weather_summary and "weather_summary" not in result:
            result["weather_summary"] = weather_summary.model_dump()
        # Validate and return VerifiedDiagnosticResponse
        return VerifiedDiagnosticResponse(**result)
    except Exception as exc:
        logger.error("Failed to parse Gemini response: %s", raw_text)
        raise HTTPException(status_code=422, detail="Invalid response from AI model") from exc
