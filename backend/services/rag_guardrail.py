import json
import logging
from typing import Optional, List
from fastapi import HTTPException
from google import genai
from google.genai import types
from google.genai.errors import ServerError
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings
from schemas.diagnostic import VerifiedDiagnosticResponse, SafeDosage, WeatherSummary
from services.extension_db import query_extension_context_scored

logger = logging.getLogger(__name__)

REFUSAL_THRESHOLD = 0.35
_MODEL = getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash")
_client = genai.Client(api_key=settings.GEMINI_API_KEY)

_BASE_PROMPT = """You are Agrosphere's Expert Agricultural Vision AI.IMPORTANT: For pre_harvest_interval_days, only output a value if the Extension Context explicitly states it. If it is not mentioned, output null. Do not estimate, infer, or use general knowledge for this field — an incorrect pre-harvest interval can cause real crop or food-safety harm.
Analyze the image and return a JSON object.

Based on the provided Extension Context, recommend verified treatments.
If no context is provided, provide general safe advice.

MULTIMODAL CONFLICT RULE: Compare the visual disease identification with the farmer's written symptoms. If there is a contradiction (e.g. image shows Late Blight but text describes 'concentric rings' which indicates Early Blight), explicitly state this discrepancy in the diagnosis and note both possibilities.

STRICT CHEMICAL GROUNDING: You MUST ONLY recommend chemicals and dosages that explicitly appear in the provided Extension Context text for the matched disease. Never suggest a chemical from general knowledge or other disease sections. If a chemical is not in the context, do NOT list it.

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

MULTIMODAL CONFLICT RULE: Compare the visual disease identification with the farmer's written symptoms. If there is a contradiction (e.g. image shows Late Blight but text describes 'concentric rings' which indicates Early Blight), explicitly state this discrepancy in the diagnosis and note both possibilities.

STRICT CHEMICAL GROUNDING: You MUST ONLY recommend chemicals and dosages that explicitly appear in the provided Extension Context text for the matched disease. Never suggest a chemical from general knowledge or other disease sections. If a chemical is not in the context, do NOT list it.

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

CORPUS_CROPS: List[str] = [
    "Tomato",
    "Chillies",
    "Brinjal",
    "Onion",
    "Bhendi",
    "Gourds",
    "Water Melon",
    "Mango",
    "Banana",
    "Turmeric",
    "Pepper",
    "Rose",
    "Jasmine",
    "Chrysanthemum",
    "Crossandra",
    "Marigold",
    "Tuberose",
    "Carnation",
]

_CROP_PREDICT_PROMPT = f"""Identify the crop or plant shown in this image so it can be matched against our agronomic disease manual.
Known corpus crops: {", ".join(CORPUS_CROPS)}.
If the plant in the image matches one of the known corpus crops (for example Eggplant -> Brinjal, Okra -> Bhendi, Watermelon -> Water Melon, Chili -> Chillies), set "predicted_crop" to that exact corpus crop name, followed by any visible disease or symptom keywords (e.g. "Tomato Early Blight" or "Mango Anthracnose").
If it is a different plant or non-plant subject, set "predicted_crop" to its specific name.
Return ONLY a valid JSON object:
{{"predicted_crop": "<string>"}}
"""


async def predict_crop_from_image(image_bytes: bytes, mime_type: str) -> str:
    """Run the vision model first to predict the crop from the image when 'Not sure' is selected."""
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=2, max=10),
            retry=retry_if_exception_type(ServerError),
            reraise=True,
        ):
            with attempt:
                resp = await _client.aio.models.generate_content(
                    model=_MODEL,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        _CROP_PREDICT_PROMPT,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
        parsed = json.loads((resp.text or "{}").strip())
        predicted = str(parsed.get("predicted_crop", "")).strip()
        if predicted:
            logger.info("Vision model predicted crop for 'Not sure': %s", predicted)
            return predicted
    except Exception as exc:
        logger.warning("Crop prediction from image failed (%s); falling back to farmer comment.", exc)
    return farmer_fallback_query()


def farmer_fallback_query() -> str:
    return "Unknown Crop"


async def apply_guardrail(
    image_bytes: bytes,
    mime_type: str,
    crop_type: str,
    language: str = "en",
    farmer_comment: Optional[str] = None,
    operational_context: Optional[str] = None,
    weather_summary: Optional[WeatherSummary] = None,
) -> VerifiedDiagnosticResponse:
    normalized_crop = (crop_type or "").strip()
    if normalized_crop.lower() in {"not sure", "not_sure", "unsure", "unknown", "general", ""}:
        predicted_crop = await predict_crop_from_image(image_bytes=image_bytes, mime_type=mime_type)
        effective_crop_type = predicted_crop
    else:
        effective_crop_type = normalized_crop

    # Ensure bare corpus crop names (e.g. "Pepper") match corpus section headers when no comment is given
    retrieval_crop_query = effective_crop_type
    if (
        not farmer_comment
        and any(effective_crop_type.lower() == c.lower() for c in CORPUS_CROPS)
    ):
        retrieval_crop_query = f"Diseases of {effective_crop_type}"

    # 1. Scored retrieval from ChromaDB
    scored_chunks = await query_extension_context_scored(
        retrieval_crop_query, farmer_comment=farmer_comment, n_results=5
    )

    # 2. Hard refusal gate — short-circuit before any LLM API call
    top_score = scored_chunks[0][2] if scored_chunks else 0.0
    if not scored_chunks or top_score < REFUSAL_THRESHOLD:
        raise HTTPException(
            status_code=422,
            detail={
                "is_refusal": True,
                "reason": (
                    f"No sufficiently relevant agronomic context found for '{effective_crop_type}'. "
                    "Please verify the crop selection or consult the Kisan Call Centre (1800-180-1551)."
                ),
                "top_relevance_score": top_score,
                "predicted_crop": effective_crop_type,
            },
        )

    # 3. Build citation-tagged context and citations list
    citation_ids = [chunk_id for chunk_id, _, _ in scored_chunks]
    context = "\n\n---\n\n".join(
        f"[{chunk_id}] {text}" for chunk_id, text, _ in scored_chunks
    )

    # 4. Inject context, citation rules, and target language into Gemini prompt
    system_prompt = _BASE_PROMPT_TA if language.lower() == 'ta' else _BASE_PROMPT

    prompt = f"{system_prompt}\n\n"
    prompt += (
        "CITATION RULE: Every treatment, dosage, or diagnostic claim must "
        "cite its source chunk in square brackets, e.g. [doc_42]. If a claim "
        "cannot be tied to a chunk ID below, do not state it.\n\n"
    )
    prompt += f"Crop Type: {effective_crop_type}\n"
    if operational_context:
        prompt += f"Operational Context Mode: {operational_context}\n"
    if weather_summary:
        prompt += f"Local Weather: Temp {weather_summary.temperature}, Rain Risk: {weather_summary.rain_chance}, Spray Note: {weather_summary.spray_advisory}\n"
    if farmer_comment:
        prompt += f"Farmer Comment: {farmer_comment}\n"
    prompt += f"\nExtension Context:\n{context}\n"

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=2, max=10),
            retry=retry_if_exception_type(ServerError),
            reraise=True,
        ):
            with attempt:
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
    except ServerError as exc:
        logger.error("Gemini server overloaded after retries: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Agronomic diagnostic engine is temporarily overloaded. Please retry in a few seconds.",
        ) from exc
    except Exception as exc:
        logger.exception("Gemini API call failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}") from exc

    raw_text: str = response.text or ""
    try:
        result: dict = json.loads(raw_text.strip())
        if weather_summary and "weather_summary" not in result:
            result["weather_summary"] = weather_summary.model_dump()
        result["citations"] = citation_ids

        # Combine retrieved context for string verification
        combined_context_lower = " ".join([text.lower() for _, text, _ in scored_chunks])

        # Filter safe_dosages against retrieved text
        if "safe_dosages" in result and isinstance(result["safe_dosages"], list):
            grounded_dosages = []
            for dosage in result["safe_dosages"]:
                chem_name = dosage.get("chemical_name", "").strip().lower()
                # Keep dosage only if chemical name literally appears in the retrieved context
                if chem_name and chem_name in combined_context_lower:
                    grounded_dosages.append(dosage)
                else:
                    logger.warning(f"STRIPPED UNGROUNDED CHEMICAL HALLUCINATION: {chem_name}")
            result["safe_dosages"] = grounded_dosages

        # Validate and return VerifiedDiagnosticResponse
        return VerifiedDiagnosticResponse(**result)
    except Exception as exc:
        logger.error("Failed to parse Gemini response: %s", raw_text)
        raise HTTPException(status_code=422, detail="Invalid response from AI model") from exc
