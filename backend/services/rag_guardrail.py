import asyncio
from collections import OrderedDict
from email.utils import parsedate_to_datetime
import hashlib
import json
import logging
import math
import os
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from google import genai
from google.genai import types
from google.genai.errors import ServerError

from config import settings
from schemas.diagnostic import (
    SafeDosage,
    ServedByLayer,
    VerifiedDiagnosticResponse,
    WeatherSummary,
)
from services.extension_db import query_extension_context_scored
from services.quota_manager import (
    HEAVY_REQUEST_SEMAPHORE,
    circuit_breaker,
    enforce_user_daily_scan_limit,
    quota_ledger,
    reset_all_quotas_and_breakers,
    user_scan_limiter,
)

logger = logging.getLogger(__name__)


# ── Constants & Thresholds ────────────────────────────────────────────────────
REFUSAL_THRESHOLD = 0.35
KISAN_CALL_CENTRE_NUMBER = "1800-180-1551"

# Layer 1 (Gemini Primary) configuration: 8–10s timeout, up to 2 retries
GEMINI_TIMEOUT_SECONDS: float = float(getattr(settings, "GEMINI_TIMEOUT_SECONDS", 9.0))
GEMINI_MAX_RETRIES: int = int(getattr(settings, "GEMINI_MAX_RETRIES", 2))
MAX_SINGLE_WAIT_SECONDS: float = 3.0
LAYER1_TOTAL_BUDGET_SECONDS: float = 12.0

# Layer 2 (Ollama Low-RAM Fallback) configuration: qwen2.5-coder:1.5b, num_ctx=2048, 5s timeout
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:1.5b"
OLLAMA_NUM_CTX = 2048
OLLAMA_TIMEOUT_SECONDS: float = float(getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 5.0))

# Layer 0 (Cache) bounded size to keep RAM footprint negligible (< 1 MB)
MAX_CACHE_ENTRIES = 256
SEMANTIC_SIMILARITY_THRESHOLD = 0.55

_MODEL = getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash")
_client = genai.Client(api_key=settings.GEMINI_API_KEY or "unconfigured-key")

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

_CROP_ALIASES: Dict[str, str] = {
    "eggplant": "brinjal",
    "aubergine": "brinjal",
    "okra": "bhendi",
    "ladies finger": "bhendi",
    "lady finger": "bhendi",
    "watermelon": "water melon",
    "chili": "chillies",
    "chilli": "chillies",
    "Hot pepper": "chillies",
    "black pepper": "pepper",
}

_CROP_PREDICT_PROMPT = f"""Identify the crop or plant shown in this image so it can be matched against our agronomic disease manual.
Known corpus crops: {", ".join(CORPUS_CROPS)}.
If the plant in the image matches one of the known corpus crops (for example Eggplant -> Brinjal, Okra -> Bhendi, Watermelon -> Water Melon, Chili -> Chillies), set "predicted_crop" to that exact corpus crop name, followed by any visible disease or symptom keywords (e.g. "Tomato Early Blight" or "Mango Anthracnose").
If it is a different plant or non-plant subject, set "predicted_crop" to its specific name.
Return ONLY a valid JSON object:
{{"predicted_crop": "<string>"}}
"""

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 0: Exact & Semantic Cache (Low-RAM, 0 API Calls, 0 Model Compute)
# ══════════════════════════════════════════════════════════════════════════════

_STOPWORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "by", "crop", "disease",
    "diseases", "do", "for", "from", "has", "have", "how", "i", "in", "is",
    "it", "leaf", "leaves", "my", "of", "on", "or", "plant", "plants",
    "please", "seeing", "show", "showing", "some", "symptom", "symptoms",
    "that", "the", "their", "this", "to", "treatment", "what", "with",
}

# Canonical agronomic disease/symptom groups for zero-compute semantic matching
_DISEASE_SYNONYM_GROUPS: Dict[str, Tuple[str, ...]] = {
    "early_blight": (
        "early blight",
        "alternaria solani",
        "concentric rings",
        "target board",
        "bullseye",
        "bulls eye",
        "alternaria leaf spot",
    ),
    "late_blight": (
        "late blight",
        "phytophthora infestans",
        "water soaked lesions",
        "water-soaked lesions",
        "white fungal growth underside",
    ),
    "anthracnose": (
        "anthracnose",
        "colletotrichum",
        "gloeosporioides",
        "capsici",
        "die back",
        "die-back",
        "fruit rot",
        "acervuli",
        "sunken black spots",
    ),
    "powdery_mildew": (
        "powdery mildew",
        "oidium",
        "erysiphe",
        "levillula",
        "taurica",
        "white powdery patches",
        "white powdery coating",
    ),
    "downy_mildew": (
        "downy mildew",
        "pseudoperonospora",
        "cubensis",
        "plasmopara",
        "peronospora",
        "purplish downy growth",
    ),
    "fusarium_wilt": (
        "fusarium wilt",
        "fusarium oxysporum",
        "vascular browning",
        "vascular discoloration",
    ),
    "bacterial_wilt": (
        "bacterial wilt",
        "ralstonia solanacearum",
        "pseudomonas solanacearum",
        "bacterial ooze",
        "sudden wilting",
    ),
    "damping_off": (
        "damping off",
        "damping-off",
        "pythium aphanidermatum",
        "collar rot seedling",
    ),
    "yellow_vein_mosaic": (
        "yellow vein mosaic",
        "yvmv",
        "vein clearing",
        "yellow network of veins",
    ),
    "leaf_curl": (
        "leaf curl",
        "tomato leaf curl",
        "chilli leaf curl",
        "tylcv",
        "upward curling crinkling",
    ),
    "panama_wilt": (
        "panama wilt",
        "panama disease",
        "fusarium oxysporum f. sp. cubense",
        "splitting of pseudostem",
    ),
    "sigatoka": (
        "sigatoka",
        "yellow sigatoka",
        "black sigatoka",
        "mycosphaerella musicola",
    ),
    "bunchy_top": (
        "bunchy top",
        "banana bunchy top",
        "bbtv",
        "morse code streaks",
        "rosette crown",
    ),
    "rhizome_rot": (
        "rhizome rot",
        "soft rot of rhizome",
    ),
    "purple_blotch": (
        "purple blotch",
        "alternaria porri",
    ),
    "basal_rot": (
        "basal rot",
        "fusarium oxysporum cepae",
    ),
    "black_spot": (
        "black spot",
        "diplocarpon rosae",
        "feathery black lesions",
    ),
    "rust": (
        "rust",
        "puccinia",
        "rust pustules",
        "uredosori",
    ),
}


class _CacheEntry:
    __slots__ = (
        "crop_norm",
        "disease_norm",
        "lang_norm",
        "weather_band",
        "canonical_diseases",
        "tokens",
        "trigrams",
        "image_hash",
        "response_data",
    )

    def __init__(
        self,
        crop_norm: str,
        disease_norm: str,
        lang_norm: str,
        weather_band: str,
        canonical_diseases: Set[str],
        tokens: Set[str],
        trigrams: Dict[str, int],
        image_hash: Optional[str],
        response_data: Dict[str, Any],
    ):
        self.crop_norm = crop_norm
        self.disease_norm = disease_norm
        self.lang_norm = lang_norm
        self.weather_band = weather_band
        self.canonical_diseases = canonical_diseases
        self.tokens = tokens
        self.trigrams = trigrams
        self.image_hash = image_hash
        self.response_data = response_data


_ANSWER_CACHE: "OrderedDict[Tuple[str, str, str, str], _CacheEntry]" = OrderedDict()
_LAST_PYTEST_NODE: Optional[str] = None


def _sync_pytest_isolation() -> None:
    """Reset cache automatically when pytest transitions between separate test functions,
    while preserving cache across multiple calls within the same test function."""
    global _LAST_PYTEST_NODE
    current = os.environ.get("PYTEST_CURRENT_TEST")
    if current:
        # Strip phase suffix like ' (setup)', ' (call)', ' (teardown)'
        node_id = current.split(" (")[0]
        if _LAST_PYTEST_NODE is not None and _LAST_PYTEST_NODE != node_id:
            _ANSWER_CACHE.clear()
        _LAST_PYTEST_NODE = node_id


def clear_answer_cache() -> None:
    """Clear all entries from the Layer 0 in-memory answer cache."""
    _ANSWER_CACHE.clear()


def compute_weather_band(
    weather_summary: Optional[WeatherSummary],
    explicit_weather_band: Optional[str] = None,
) -> str:
    """Bucket weather conditions into a deterministic weather band for Layer 0 caching."""
    if explicit_weather_band and explicit_weather_band.strip():
        return explicit_weather_band.strip().lower()
    if weather_summary is None:
        return "none"

    temp_str = (weather_summary.temperature or "").strip()
    temp_match = re.search(r"(-?\d+(?:\.\d+)?)", temp_str)
    if temp_match:
        temp_c = float(temp_match.group(1))
        if temp_c < 20.0:
            temp_band = "cool"
        elif temp_c <= 32.0:
            temp_band = "warm"
        else:
            temp_band = "hot"
    else:
        temp_band = "unknown_temp"

    rain_str = (weather_summary.rain_chance or "").strip().lower()
    if "high" in rain_str:
        rain_band = "high_rain"
    elif "low" in rain_str:
        rain_band = "low_rain"
    elif "moderate" in rain_str or "medium" in rain_str:
        rain_band = "moderate_rain"
    else:
        rain_band = re.sub(r"[^a-z0-9]+", "_", rain_str).strip("_") or "unknown_rain"

    return f"{temp_band}_{rain_band}"


def _extract_crop_and_disease(
    crop_type: str, farmer_comment: Optional[str]
) -> Tuple[str, str]:
    """Normalize crop name and extract disease/symptom text from crop_type + farmer_comment."""
    raw_crop = (crop_type or "").strip().lower()
    raw_crop = re.sub(r"^diseases\s+of\s+", "", raw_crop).strip()
    raw_crop = _CROP_ALIASES.get(raw_crop, raw_crop)

    comment_part = (farmer_comment or "").strip().lower()
    matched_crop = raw_crop
    extra_disease_from_crop = ""

    # Check if crop_type contains both a known crop name and a disease suffix (e.g. "Tomato Early Blight")
    for known in sorted(CORPUS_CROPS, key=len, reverse=True):
        k_lower = known.lower()
        if raw_crop == k_lower:
            matched_crop = k_lower
            break
        if raw_crop.startswith(k_lower + " "):
            matched_crop = k_lower
            extra_disease_from_crop = raw_crop[len(k_lower) :].strip()
            break

    for alias, target in _CROP_ALIASES.items():
        if raw_crop.startswith(alias + " "):
            matched_crop = target
            extra_disease_from_crop = raw_crop[len(alias) :].strip()
            break

    combined_disease = " ".join(
        part for part in (extra_disease_from_crop, comment_part) if part
    ).strip()
    combined_disease = re.sub(r"\s+", " ", combined_disease)
    return matched_crop, combined_disease


def _extract_canonical_diseases(text: str) -> Set[str]:
    """Map raw symptom/disease text to canonical agronomic disease identifiers."""
    if not text:
        return set()
    lowered = text.lower()
    found: Set[str] = set()
    for canonical_id, phrases in _DISEASE_SYNONYM_GROUPS.items():
        for phrase in phrases:
            if phrase in lowered:
                found.add(canonical_id)
                break
    return found


def _meaningful_tokens(text: str, crop_norm: str = "") -> Set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    crop_words = set(re.findall(r"[a-z0-9]+", (crop_norm or "").lower()))
    return {
        w
        for w in words
        if len(w) > 2 and w not in _STOPWORDS and w not in crop_words
    }


def _char_trigrams(text: str) -> Dict[str, int]:
    cleaned = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if len(cleaned) < 3:
        return {cleaned: 1} if cleaned else {}
    counts: Dict[str, int] = {}
    for i in range(len(cleaned) - 2):
        tg = cleaned[i : i + 3]
        counts[tg] = counts.get(tg, 0) + 1
    return counts


def _cosine_dict(a: Dict[str, int], b: Dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _semantic_similarity(
    query_tokens: Set[str],
    query_trigrams: Dict[str, int],
    entry: _CacheEntry,
) -> float:
    if not query_tokens and not entry.tokens:
        return 1.0
    if not query_tokens or not entry.tokens:
        return 0.0

    intersection = len(query_tokens & entry.tokens)
    union = len(query_tokens | entry.tokens)
    token_jaccard = intersection / union if union else 0.0
    trigram_cos = _cosine_dict(query_trigrams, entry.trigrams)
    return 0.6 * token_jaccard + 0.4 * trigram_cos


def get_cached_answer(
    crop_type: str,
    disease_or_comment: Optional[str],
    language: str = "en",
    weather_band: str = "none",
    image_hash: Optional[str] = None,
    weather_summary: Optional[WeatherSummary] = None,
) -> Optional[VerifiedDiagnosticResponse]:
    """Layer 0: Check exact and semantic cache for matching (crop, disease, language, weather_band)."""
    _sync_pytest_isolation()
    crop_norm, disease_norm = _extract_crop_and_disease(crop_type, disease_or_comment)
    lang_norm = (language or "en").strip().lower()
    w_band = (weather_band or "none").strip().lower()

    # Do not match across unknown/not-sure crops unless image_hash matches
    is_unsure = crop_norm in {"not sure", "not_sure", "unsure", "unknown", "general", "", "unknown crop"}
    if is_unsure and not disease_norm and not image_hash:
        return None

    exact_key = (crop_norm, disease_norm or (image_hash or ""), lang_norm, w_band)
    if exact_key in _ANSWER_CACHE:
        entry = _ANSWER_CACHE[exact_key]
        _ANSWER_CACHE.move_to_end(exact_key)
        return _clone_as_cached_response(entry.response_data, weather_summary)

    # Also check exact match on (crop_norm, disease_norm, lang_norm, w_band) when disease_norm is empty
    fallback_exact_key = (crop_norm, disease_norm, lang_norm, w_band)
    if not is_unsure and fallback_exact_key in _ANSWER_CACHE:
        entry = _ANSWER_CACHE[fallback_exact_key]
        _ANSWER_CACHE.move_to_end(fallback_exact_key)
        return _clone_as_cached_response(entry.response_data, weather_summary)

    if not disease_norm:
        return None

    # Semantic matching across cached entries with the same (crop, language, weather_band)
    query_canonical = _extract_canonical_diseases(disease_norm)
    query_tokens = _meaningful_tokens(disease_norm, crop_norm)
    query_trigrams = _char_trigrams(" ".join(sorted(query_tokens)) or disease_norm)

    best_entry: Optional[_CacheEntry] = None
    best_score = 0.0

    for entry in _ANSWER_CACHE.values():
        if entry.crop_norm != crop_norm or entry.lang_norm != lang_norm or entry.weather_band != w_band:
            continue

        # 1. Canonical agronomic disease equivalence (e.g. "Alternaria solani" == "early blight concentric rings")
        if query_canonical and entry.canonical_diseases and (query_canonical & entry.canonical_diseases):
            best_entry = entry
            best_score = 1.0
            break

        # 2. Lexical + character n-gram semantic similarity
        sim = _semantic_similarity(query_tokens, query_trigrams, entry)
        if sim >= SEMANTIC_SIMILARITY_THRESHOLD and sim > best_score:
            best_score = sim
            best_entry = entry

    if best_entry is not None:
        logger.info(
            "Layer 0 semantic cache hit for crop=%s, query=%r (score=%.2f)",
            crop_norm,
            disease_norm,
            best_score,
        )
        return _clone_as_cached_response(best_entry.response_data, weather_summary)

    return None


def _clone_as_cached_response(
    response_data: Dict[str, Any],
    weather_summary: Optional[WeatherSummary] = None,
) -> VerifiedDiagnosticResponse:
    cloned = dict(response_data)
    cloned["served_by"] = "cache"
    cloned["degraded"] = False
    cloned["is_refusal"] = False
    if weather_summary is not None:
        cloned["weather_summary"] = weather_summary.model_dump()
    return VerifiedDiagnosticResponse(**cloned)


def store_cached_answer(
    crop_type: str,
    disease_or_comment: Optional[str],
    language: str,
    weather_band: str,
    response: VerifiedDiagnosticResponse,
    image_hash: Optional[str] = None,
) -> None:
    """Store a verified diagnostic answer in Layer 0 cache for instant future retrieval."""
    if not response.is_verified or response.served_by == "refusal" or response.is_refusal:
        return

    _sync_pytest_isolation()
    crop_norm, disease_norm = _extract_crop_and_disease(crop_type, disease_or_comment)
    lang_norm = (language or "en").strip().lower()
    w_band = (weather_band or "none").strip().lower()

    combined_disease_text = f"{disease_norm} {response.pathogen}".strip().lower()
    canonical_diseases = _extract_canonical_diseases(combined_disease_text)
    tokens = _meaningful_tokens(combined_disease_text, crop_norm)
    trigrams = _char_trigrams(" ".join(sorted(tokens)) or combined_disease_text)

    serialized = response.model_dump()
    entry = _CacheEntry(
        crop_norm=crop_norm,
        disease_norm=disease_norm,
        lang_norm=lang_norm,
        weather_band=w_band,
        canonical_diseases=canonical_diseases,
        tokens=tokens,
        trigrams=trigrams,
        image_hash=image_hash,
        response_data=serialized,
    )

    keys_to_store = [(crop_norm, disease_norm, lang_norm, w_band)]
    if image_hash:
        keys_to_store.append((crop_norm, disease_norm or image_hash, lang_norm, w_band))

    for key in keys_to_store:
        _ANSWER_CACHE[key] = entry
        _ANSWER_CACHE.move_to_end(key)

    while len(_ANSWER_CACHE) > MAX_CACHE_ENTRIES:
        _ANSWER_CACHE.popitem(last=False)


# ══════════════════════════════════════════════════════════════════════════════
# Crop Auto-Detection Helper (When "Not sure" is selected)
# ══════════════════════════════════════════════════════════════════════════════

async def predict_crop_from_image(
    image_bytes: bytes,
    mime_type: str,
    farmer_comment: Optional[str] = None,
) -> str:
    """Run the vision model first to predict the crop from the image when 'Not sure' is selected."""
    # Divert non-essential pre-prediction call if quota > 85% or circuit breaker is tripped
    if quota_ledger.should_divert_non_essential() or circuit_breaker.is_tripped():
        logger.info("Diverting non-essential crop auto-detection due to quota (>85%) or open circuit breaker.")
        return farmer_fallback_query(farmer_comment)

    try:
        quota_ledger.record_call()
        resp = await asyncio.wait_for(
            _client.aio.models.generate_content(
                model=_MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    _CROP_PREDICT_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            ),
            timeout=min(GEMINI_TIMEOUT_SECONDS, 9.0),
        )
        circuit_breaker.record_success()
        parsed = json.loads((resp.text or "{}").strip())
        predicted = str(parsed.get("predicted_crop", "")).strip()
        if predicted:
            logger.info("Vision model predicted crop for 'Not sure': %s", predicted)
            return predicted
    except Exception as exc:
        circuit_breaker.record_failure(exc)
        logger.warning("Crop prediction from image failed (%s); falling back to farmer comment.", exc)
    return farmer_fallback_query(farmer_comment)


def farmer_fallback_query(farmer_comment: Optional[str] = None) -> str:
    if farmer_comment and farmer_comment.strip():
        return farmer_comment.strip()
    return "Unknown Crop"


# ══════════════════════════════════════════════════════════════════════════════
# Grounding & Validation Helpers (Shared across Layers 1 & 2)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_explicit_phi_from_context(context_text: str) -> Optional[int]:
    """Return an integer Pre-Harvest Interval (days) ONLY if explicitly stated in the retrieved text."""
    patterns = [
        r"(?:pre[-\s]?harvest\s+interval|phi|waiting\s+period(?:\s+before\s+harvest)?)\s*(?:is|of|:|-|=)?\s*(\d+)\s*days?",
        r"(\d+)\s*days?\s*(?:pre[-\s]?harvest\s+interval|phi|waiting\s+period\s+before\s+harvest)",
        r"harvest\s+after\s+(\d+)\s*days?\s+of\s+(?:last\s+)?(?:spray|application)",
    ]
    lowered = context_text.lower()
    for pat in patterns:
        m = re.search(pat, lowered)
        if m:
            return int(m.group(1))
    return None

def _windows_around(name: str, context: str, size: int = 250) -> List[str]:
    """Return the pieces of context text that sit around each mention of a chemical."""
    windows = []
    start = 0
    while True:
        pos = context.find(name, start)
        if pos == -1:
            break
        windows.append(context[max(0, pos - size): pos + len(name) + size])
        start = pos + 1
    return windows


def _numbers_found_in_windows(text: str, windows: List[str]) -> bool:
    """True only if every number in text appears in one window of the manual text."""
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if not numbers:
        return True
    for window in windows:
        if all(re.search(rf"(?<![\d.]){re.escape(n)}(?!\d|\.\d)", window) for n in numbers):
            return True
    return False
def _sanitize_and_ground_llm_result(
    raw_result: Dict[str, Any],
    scored_chunks: List[Tuple[str, str, float]],
    citation_ids: List[str],
    weather_summary: Optional[WeatherSummary],
    served_by: ServedByLayer,
    degraded: bool,
) -> VerifiedDiagnosticResponse:
    """Filter chemical hallucinations against retrieved context and enforce PHI safety."""
    combined_context_lower = " ".join(text.lower() for _, text, _ in scored_chunks)
    explicit_context_phi = _extract_explicit_phi_from_context(combined_context_lower)

    grounded_dosages: List[Dict[str, Any]] = []
    raw_dosages = raw_result.get("safe_dosages")
    if isinstance(raw_dosages, list):
        for dosage in raw_dosages:
            if not isinstance(dosage, dict):
                continue
            chem_name = str(dosage.get("chemical_name", "")).strip()
            chem_lower = chem_name.lower()
            if chem_lower and chem_lower in combined_context_lower:
                windows = _windows_around(chem_lower, combined_context_lower)

                dose_text = str(dosage.get("dosage", "")).strip()
                unit_text = str(dosage.get("unit", "")).strip() or "per manual"
                if not dose_text or not _numbers_found_in_windows(dose_text, windows):
                    dose_text = "As per manual - confirm with your local agriculture officer"
                    unit_text = "per manual"

                freq_text = str(dosage.get("max_frequency", "")).strip()
                if not freq_text or not _numbers_found_in_windows(freq_text, windows):
                    freq_text = "As recommended in manual"

                phi_val = dosage.get("pre_harvest_interval_days")
                if phi_val is not None and not re.search(
                    rf"\b{re.escape(str(phi_val))}\s*days?\b", combined_context_lower
                ):
                    phi_val = None

                grounded_dosages.append(
                    {
                        "chemical_name": chem_name,
                        "dosage": dose_text,
                        "unit": unit_text,
                        "max_frequency": freq_text,
                        "pre_harvest_interval_days": int(phi_val) if isinstance(phi_val, (int, float)) else None,
                    }
                )
            else:
                logger.warning("STRIPPED UNGROUNDED CHEMICAL HALLUCINATION: %s", chem_name)

    confidence_raw = raw_result.get("confidence", scored_chunks[0][2] if scored_chunks else 0.75)
    try:
        confidence_val = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence_val = float(scored_chunks[0][2]) if scored_chunks else 0.75

    organic_recs = raw_result.get("organic_recommendations")
    if not isinstance(organic_recs, list):
        organic_recs = [str(organic_recs)] if organic_recs else []
    else:
        organic_recs = [str(x) for x in organic_recs if x]

    preventive = raw_result.get("preventive_measures")
    if not isinstance(preventive, list):
        preventive = [str(preventive)] if preventive else []
    else:
        preventive = [str(x) for x in preventive if x]

    verified_treatment = str(raw_result.get("verified_treatment", "")).strip()
    pathogen = str(raw_result.get("pathogen", "")).strip()
    if not pathogen or not verified_treatment:
        raise ValueError("Model response missing required 'pathogen' or 'verified_treatment' fields.")

    disclaimer = str(
        raw_result.get(
            "disclaimer",
            "Grounded in TNAU Agricultural Extension Manual. Confirm chemical dosages with your local agriculture officer.",
        )
    ).strip()

    return VerifiedDiagnosticResponse(
        pathogen=pathogen,
        confidence=confidence_val,
        verified_treatment=verified_treatment,
        safe_dosages=[SafeDosage(**d) for d in grounded_dosages],
        organic_recommendations=organic_recs,
        preventive_measures=preventive,
        disclaimer=disclaimer,
        is_verified=bool(raw_result.get("is_verified", True)),
        served_by=served_by,
        degraded=degraded,
        is_refusal=False,
        weather_summary=weather_summary,
        citations=citation_ids,
    )


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: Gemini Primary (8–10s Timeout, Max 2 Retries, Jittered Backoff + Retry-After)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_retry_after(exc: BaseException) -> Optional[float]:
    """Extract Retry-After delay (in seconds) from HTTP/API exceptions if present."""
    headers: Optional[Any] = None
    resp = getattr(exc, "response", None)
    if resp is not None:
        headers = getattr(resp, "headers", None)
    if headers is None:
        headers = getattr(exc, "headers", None)

    raw_val: Optional[Any] = None
    if headers is not None and hasattr(headers, "get"):
        raw_val = headers.get("Retry-After") or headers.get("retry-after")
    elif isinstance(headers, dict):
        for k, v in headers.items():
            if str(k).lower() == "retry-after":
                raw_val = v
                break

    if raw_val is None:
        raw_val = getattr(exc, "retry_after", None)

    if raw_val is not None:
        try:
            return max(0.0, float(raw_val))
        except (TypeError, ValueError):
            try:
                dt = parsedate_to_datetime(str(raw_val))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                delta = (dt - datetime.now(timezone.utc)).total_seconds()
                return max(0.0, float(delta))
            except Exception:
                pass

    # Fallback: check exception message for 'Retry-After: <seconds>' or 'retry after <seconds>'
    msg = str(exc)
    m = re.search(r"retry[-_\s]?after[:\s=]+(\d+(?:\.\d+)?)", msg, re.IGNORECASE)
    if m:
        return max(0.0, float(m.group(1)))

    return None


def _compute_backoff_delay(retry_index: int, retry_after: Optional[float]) -> float:
    """Compute jittered exponential backoff delay, honoring Retry-After when present."""
    jitter = random.uniform(0.05, 0.35)
    exp_backoff = (0.5 * (2 ** retry_index)) + jitter
    if retry_after is not None:
        return min(max(float(retry_after), 0.0), MAX_SINGLE_WAIT_SECONDS)
    return exp_backoff


async def call_gemini_primary(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    scored_chunks: List[Tuple[str, str, float]],
    citation_ids: List[str],
    weather_summary: Optional[WeatherSummary] = None,
    timeout_seconds: Optional[float] = None,
    max_retries: Optional[int] = None,
    is_probe: bool = False,
) -> VerifiedDiagnosticResponse:
    """Layer 1: Call Gemini primary model with an 8–10s timeout and up to 2 retries
    with jittered exponential backoff, honoring the Retry-After header and updating
    the Quota Ledger & Circuit Breaker."""
    effective_timeout = float(
        timeout_seconds
        if timeout_seconds is not None
        else getattr(settings, "GEMINI_TIMEOUT_SECONDS", GEMINI_TIMEOUT_SECONDS)
    )
    if is_probe:
        # Single probe request when circuit breaker is in HALF_OPEN state
        effective_retries = 0
    else:
        effective_retries = int(
            max_retries
            if max_retries is not None
            else getattr(settings, "GEMINI_MAX_RETRIES", GEMINI_MAX_RETRIES)
        )
        # Cap retries at 2 per specification (1 initial attempt + up to 2 retries = 3 total attempts)
        effective_retries = max(0, min(2, effective_retries))

    last_exc: Optional[BaseException] = None
    total_attempts = 1 + effective_retries
    started_at = asyncio.get_running_loop().time()

    for attempt_idx in range(total_attempts):
        time_left = LAYER1_TOTAL_BUDGET_SECONDS - (asyncio.get_running_loop().time() - started_at)
        if attempt_idx > 0 and time_left < 1.0:
            logger.warning("Layer 1 time budget used up; failing over.")
            break
        attempt_timeout = max(1.0, min(effective_timeout, time_left))
        if attempt_idx > 0 and circuit_breaker.is_tripped():
            logger.warning("Circuit breaker tripped during retry loop; aborting remaining Gemini retries.")
            break

        try:
            quota_ledger.record_call()
            response = await asyncio.wait_for(
                _client.aio.models.generate_content(
                    model=_MODEL,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                ),
                timeout=attempt_timeout,
            )
            raw_text = (response.text or "").strip()
            parsed = json.loads(raw_text)
            sanitized = _sanitize_and_ground_llm_result(
                raw_result=parsed,
                scored_chunks=scored_chunks,
                citation_ids=citation_ids,
                weather_summary=weather_summary,
                served_by="gemini",
                degraded=False,
            )
            circuit_breaker.record_success()
            return sanitized
        except Exception as exc:
            last_exc = exc
            new_cb_state = circuit_breaker.record_failure(exc)
            if new_cb_state == "OPEN":
                logger.warning(
                    "Circuit breaker is now OPEN after Gemini error (%s). Failing over immediately.",
                    exc,
                )
                break
            if attempt_idx < effective_retries:
                retry_after = _extract_retry_after(exc)
                if retry_after is not None and retry_after > MAX_SINGLE_WAIT_SECONDS:
                    logger.warning("Gemini asked for a long wait (%s s); failing over now.", retry_after)
                    break
                delay = _compute_backoff_delay(attempt_idx, retry_after)
                if (asyncio.get_running_loop().time() - started_at) + delay >= LAYER1_TOTAL_BUDGET_SECONDS:
                    break
                logger.warning(
                    "Layer 1 (Gemini) attempt %d/%d failed (%s). Retrying in %.2fs (retry_after=%s)...",
                    attempt_idx + 1,
                    total_attempts,
                    exc,
                    delay,
                    retry_after,
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "Layer 1 (Gemini) exhausted all %d attempts (%s). Failing over to Layer 2.",
                    total_attempts,
                    exc,
                )

    raise RuntimeError(f"Layer 1 Gemini primary failed: {last_exc}") from last_exc


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: Low-Memory Local Fallback (Ollama qwen2.5-coder:1.5b, num_ctx=2048, <=5s)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Parse JSON from model response, stripping markdown code fences if present."""
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


async def call_ollama_secondary(
    prompt: str,
    scored_chunks: List[Tuple[str, str, float]],
    citation_ids: List[str],
    weather_summary: Optional[WeatherSummary] = None,
    timeout_seconds: Optional[float] = None,
) -> VerifiedDiagnosticResponse:
    """Layer 2: Query local Ollama model (default qwen2.5-coder:1.5b) with strict num_ctx=2048
    to keep RAM < 1.2 GB and a hard 5-second timeout."""
    ollama_base_url = os.getenv(
        "OLLAMA_BASE_URL",
        getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"),
    ).rstrip("/")
    ollama_model = os.getenv(
        "OLLAMA_MODEL",
        getattr(settings, "OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
    ) or DEFAULT_OLLAMA_MODEL
    num_ctx = min(
        int(os.getenv("OLLAMA_NUM_CTX", getattr(settings, "OLLAMA_NUM_CTX", OLLAMA_NUM_CTX))),
        OLLAMA_NUM_CTX,
    )
    effective_timeout = min(
        float(
            timeout_seconds
            if timeout_seconds is not None
            else os.getenv("OLLAMA_TIMEOUT_SECONDS", getattr(settings, "OLLAMA_TIMEOUT_SECONDS", OLLAMA_TIMEOUT_SECONDS))
        ),
        5.0,
    )

    payload = {
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "num_ctx": num_ctx,
            "temperature": 0.1,
        },
    }

    async def _do_ollama_request() -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=effective_timeout) as client:
            resp = await client.post(f"{ollama_base_url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json()

    data = await asyncio.wait_for(_do_ollama_request(), timeout=effective_timeout)
    response_text = data.get("response", "")
    parsed = _extract_json_object(response_text if isinstance(response_text, str) else json.dumps(response_text))

    return _sanitize_and_ground_llm_result(
        raw_result=parsed,
        scored_chunks=scored_chunks,
        citation_ids=citation_ids,
        weather_summary=weather_summary,
        served_by="secondary_local",
        degraded=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3: Deterministic Extractive Answer (No LLM, Template-Based from Top Chunk)
# ══════════════════════════════════════════════════════════════════════════════

_KNOWN_CHEMICALS: Tuple[str, ...] = (
    "Mancozeb",
    "Carbendazim",
    "Copper oxychloride",
    "Chlorothalonil",
    "Propiconazole",
    "Hexaconazole",
    "Tebuconazole",
    "Azoxystrobin",
    "Metalaxyl",
    "Fosetyl-Al",
    "Wettable sulphur",
    "Sulphur",
    "Zineb",
    "Captan",
    "Thiram",
    "Thiophanate methyl",
    "Bordeaux mixture",
    "Streptomycin sulphate",
    "Tetracycline",
    "Tricyclazole",
    "Edifenphos",
    "Dinocap",
    "Tridemorph",
    "Benomyl",
    "Carboxin",
    "Dimethoate",
    "Imidacloprid",
)


def _extract_disease_name_from_chunk(
    chunk_text: str, crop_type: str, farmer_comment: Optional[str]
) -> str:
    """Deterministically extract Disease Name from the top retrieved chunk."""
    lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]

    # Pattern 1: Numbered disease header in TNAU manual, e.g. "1. Anthracnose :Colletotrichum gloeosporioides"
    for line in lines:
        m = re.match(r"^\d+\.\s*([A-Za-z][A-Za-z0-9\s\-/()]+?)\s*:\s*([A-Za-z][A-Za-z0-9\s.\-()]+)$", line)
        if m:
            disease_title = m.group(1).strip()
            causal_agent = m.group(2).strip()
            return f"{disease_title} ({causal_agent})"

        m2 = re.match(r"^\d+\.\s*([A-Za-z][A-Za-z0-9\s\-/()]{2,60})$", line)
        if m2 and "management" not in line.lower():
            return m2.group(1).strip()

    # Pattern 2: Explicit "Disease: <name>" or "<Disease> caused by <Pathogen>"
    m_caused = re.search(
        r"([A-Z][A-Za-z\s\-]{2,35}(?:blight|wilt|rot|mildew|spot|mosaic|curl|anthracnose|rust|smut|scab|canker|damping[\s\-]off))\s*(?:\(|:|caused\s+by\s+)([A-Z][a-z]+\s+[a-z]+)?",
        chunk_text,
        flags=re.IGNORECASE,
    )
    if m_caused:
        d_name = m_caused.group(1).strip().title()
        pathogen = (m_caused.group(2) or "").strip()
        return f"{d_name} ({pathogen})" if pathogen else d_name

    # Pattern 3: Check known disease synonym groups in chunk text or farmer_comment
    combined = f"{chunk_text} {farmer_comment or ''}"
    for canonical_id, phrases in _DISEASE_SYNONYM_GROUPS.items():
        for phrase in phrases:
            if phrase in combined.lower():
                pretty_name = canonical_id.replace("_", " ").title()
                return f"{crop_type} — {pretty_name}" if crop_type else pretty_name

    # Fallback: use crop_type + first descriptive header line
    for line in lines:
        if not re.match(r"^\d+$", line) and len(line) > 5 and "dr." not in line.lower():
            cleaned_line = re.sub(r"\s+", " ", line).strip(" .:-")
            if len(cleaned_line) <= 80:
                return f"{crop_type} — {cleaned_line}" if crop_type.lower() not in cleaned_line.lower() else cleaned_line
            break

    return f"{crop_type} Disease (TNAU Manual Match)".strip()


def _extract_dosages_from_chunk(
    chunk_text: str, explicit_phi: Optional[int]
) -> List[SafeDosage]:
    """Deterministically extract grounded chemical dosages that literally appear in the chunk."""
    dosages: List[SafeDosage] = []
    seen_chems: Set[str] = set()

    # Extract frequency if mentioned in chunk
    freq_match = re.search(
        r"((?:twice|thrice|\d+\s+times)?\s*at\s+\d+[\s\-]*days?\s+intervals?|repeat(?:ed)?\s+after\s+\d+\s+days?|twice|at\s+recommended\s+intervals)",
        chunk_text,
        flags=re.IGNORECASE,
    )
    default_freq = freq_match.group(1).strip().capitalize() if freq_match else "As per TNAU extension schedule"

    for chem in _KNOWN_CHEMICALS:
        pattern = re.compile(
            rf"\b({re.escape(chem)})\b[^.\n]{{0,45}}?(\d+(?:\.\d+)?)\s*(%|g/lit(?:re)?|g/l|ml/lit(?:re)?|ml/l|g/kg|kg/ha)",
            flags=re.IGNORECASE,
        )
        m = pattern.search(chunk_text)
        if m:
            chem_key = chem.lower()
            if chem_key in seen_chems:
                continue
            seen_chems.add(chem_key)
            dosages.append(
                SafeDosage(
                    chemical_name=m.group(1),
                    dosage=m.group(2),
                    unit=m.group(3),
                    max_frequency=default_freq,
                    pre_harvest_interval_days=explicit_phi,
                )
            )
            continue

        # Also check parenthesized dosage right after chemical name, e.g., "Carbendazim (0.1%)"
        pattern_paren = re.compile(
            rf"\b({re.escape(chem)})\s*\(\s*(\d+(?:\.\d+)?)\s*(%|g/lit(?:re)?|g/l|ml/lit(?:re)?|ml/l|g/kg|kg/ha)\s*\)",
            flags=re.IGNORECASE,
        )
        m2 = pattern_paren.search(chunk_text)
        if m2:
            chem_key = chem.lower()
            if chem_key in seen_chems:
                continue
            seen_chems.add(chem_key)
            dosages.append(
                SafeDosage(
                    chemical_name=m2.group(1),
                    dosage=m2.group(2),
                    unit=m2.group(3),
                    max_frequency=default_freq,
                    pre_harvest_interval_days=explicit_phi,
                )
            )

    return dosages


def _extract_treatment_sentences(chunk_text: str, dosages: List[SafeDosage]) -> str:
    """Extract actionable treatment & dosage sentences from the top chunk."""
    normalized = re.sub(r"\s+", " ", chunk_text).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]

    action_keywords = (
        "spray", "apply", "drench", "treat", "management", "control",
        "fungicide", "carbendazim", "mancozeb", "copper", "bordeaux",
        "pseudomonas", "trichoderma", "neem", "remove", "sanitation", "prun",
    )
    matched_sentences = [
        s for s in sentences if any(kw in s.lower() for kw in action_keywords)
    ]

    if matched_sentences:
        treatment_text = " ".join(matched_sentences[:3])
    else:
        treatment_text = normalized[:350].strip()

    if dosages:
        dosage_summary = "; ".join(
            f"{d.chemical_name} {d.dosage} {d.unit} ({d.max_frequency})"
            for d in dosages
        )
        if dosage_summary.lower() not in treatment_text.lower():
            treatment_text = f"{treatment_text} Verified Dosages: {dosage_summary}."

    return treatment_text


def build_extractive_rag_answer(
    crop_type: str,
    farmer_comment: Optional[str],
    scored_chunks: List[Tuple[str, str, float]],
    weather_summary: Optional[WeatherSummary] = None,
    language: str = "en",
) -> VerifiedDiagnosticResponse:
    """Layer 3 (Deterministic Extractive Answer - No LLM):
    Bypass all language models. Take the top retrieved chunk from ChromaDB/BM25 and
    assemble the diagnosis using the required template:
    - Disease Name
    - Treatment & Dosage
    - Pre-Harvest Interval (PHI)
    - Source Citation
    """
    if not scored_chunks:
        raise ValueError("Cannot build Layer 3 extractive answer without retrieved chunks.")

    top_chunk_id, top_chunk_text, top_score = scored_chunks[0]
    if not top_chunk_text or not top_chunk_text.strip():
        raise ValueError("Top retrieved chunk is empty.")

    citation_ids = [cid for cid, _, _ in scored_chunks]

    # 1. Disease Name
    disease_name = _extract_disease_name_from_chunk(top_chunk_text, crop_type, farmer_comment)

    # 2. Pre-Harvest Interval (PHI) — strictly extracted from text, never guessed
    explicit_phi = _extract_explicit_phi_from_context(top_chunk_text)
    if explicit_phi is not None:
        phi_display = f"{explicit_phi} days"
    else:
        phi_display = "Not explicitly stated in source manual (null) — confirm with local agriculture officer before harvest"

    # 3. Treatment & Dosage
    safe_dosages = _extract_dosages_from_chunk(top_chunk_text, explicit_phi)
    treatment_and_dosage = _extract_treatment_sentences(top_chunk_text, safe_dosages)

    # 4. Source Citation
    source_citation = f"[{top_chunk_id}] TNAU Major Diseases of Horticultural Crops Manual"

    # Assemble diagnosis using the exact required 4-field template
    templated_diagnosis = (
        f"Disease Name: {disease_name}\n"
        f"Treatment & Dosage: {treatment_and_dosage} [{top_chunk_id}]\n"
        f"Pre-Harvest Interval (PHI): {phi_display}\n"
        f"Source Citation: {source_citation}"
    )

    # Extract organic & preventive bullets deterministically if present in top chunk
    organic_recs: List[str] = []
    if re.search(r"pseudomonas\s+fluorescens", top_chunk_text, re.IGNORECASE):
        organic_recs.append(f"Biological control: Apply Pseudomonas fluorescens as per manual [{top_chunk_id}].")
    if re.search(r"trichoderma\s+viride", top_chunk_text, re.IGNORECASE):
        organic_recs.append(f"Biological control: Apply Trichoderma viride as per manual [{top_chunk_id}].")
    if re.search(r"neem\s+(?:cake|oil)", top_chunk_text, re.IGNORECASE):
        organic_recs.append(f"Organic amendment: Apply Neem cake / Neem oil as described in [{top_chunk_id}].")

    preventive_measures: List[str] = [
        f"Field sanitation: Remove and destroy infected plant debris [{top_chunk_id}].",
        "Confirm chemical dosage and pre-harvest interval with your local Agriculture Extension Officer.",
    ]

    return VerifiedDiagnosticResponse(
        pathogen=disease_name,
        confidence=round(max(0.0, min(1.0, float(top_score))), 4),
        verified_treatment=templated_diagnosis,
        safe_dosages=safe_dosages,
        organic_recommendations=organic_recs,
        preventive_measures=preventive_measures,
        disclaimer=(
            "Degraded Mode (Deterministic Extractive RAG — No LLM): Assembled directly from the top verified "
            f"TNAU manual passage [{top_chunk_id}]. Consult Kisan Call Centre ({KISAN_CALL_CENTRE_NUMBER}) "
            "or your local KVK before chemical application."
        ),
        is_verified=True,
        served_by="extractive_rag",
        degraded=True,
        is_refusal=False,
        weather_summary=weather_summary,
        citations=citation_ids,
    )


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4: Honest Refusal (Low Confidence or All Previous Layers Failed)
# ══════════════════════════════════════════════════════════════════════════════

def build_honest_refusal(
    crop_type: str,
    top_score: float = 0.0,
    language: str = "en",
    weather_summary: Optional[WeatherSummary] = None,
    reason_override: Optional[str] = None,
) -> VerifiedDiagnosticResponse:
    """Layer 4 (Honest Refusal): Return a safe, honest refusal when retrieval confidence is
    below threshold or all previous layers fail, providing the Kisan Call Centre number
    (1800-180-1551) and directing to the local KVK."""
    crop_label = (crop_type or "Unknown Crop").strip()
    bounded_score = round(max(0.0, min(1.0, float(top_score))), 4)

    if (language or "en").lower() == "ta":
        pathogen_label = "பாதுகாப்பான மறுப்பு — உறுதியான தகவல் இல்லை (Honest Refusal)"
        refusal_message = reason_override or (
            f"'{crop_label}' பயிருக்கான சரிபார்க்கப்பட்ட வேளாண் கையேட்டுத் தகவல்கள் போதுமான அளவு பொருந்தவில்லை "
            f"(நம்பகத்தன்மை: {bounded_score:.2f} < {REFUSAL_THRESHOLD}). "
            f"இந்த அமைப்பால் பாதுகாப்பாகப் பதிலளிக்க இயலாது (Cannot answer safely). "
            f"உடனடி நிபுணர் ஆலோசனைக்கு கிசான் அழைப்பு மையத்தை (Kisan Call Centre) {KISAN_CALL_CENTRE_NUMBER} என்ற கட்டணமில்லா எண்ணில் தொடர்பு கொள்ளவும் "
            "அல்லது உங்கள் அருகிலுள்ள வேளாண் அறிவியல் நிலையத்தை (Local KVK - Krishi Vigyan Kendra) அணுகவும்."
        )
        preventive = [
            f"கிசான் அழைப்பு மையம் (Kisan Call Centre): {KISAN_CALL_CENTRE_NUMBER} (கட்டணமில்லா எண்).",
            "அருகிலுள்ள வேளாண் அறிவியல் நிலையம் (Local KVK) அல்லது வேளாண் விரிவாக்க அதிகாரியை அணுகவும்.",
        ]
        disclaimer = (
            f"பாதுகாப்பு மறுப்பு (Layer 4 Refusal): தவறான மருந்து அளவுகளைத் தவிர்க்க AI பதில் நிறுத்தப்பட்டுள்ளது. "
            f"Kisan Call Centre: {KISAN_CALL_CENTRE_NUMBER} | Local KVK."
        )
    else:
        pathogen_label = "Cannot Answer Safely — Honest Refusal"
        refusal_message = reason_override or (
            f"The system cannot answer safely for '{crop_label}' because retrieval confidence "
            f"({bounded_score:.2f}) is below the safety threshold ({REFUSAL_THRESHOLD}) or verified "
            "diagnostic generation could not be completed. To protect your crop from unverified chemical "
            f"dosages, please call the Kisan Call Centre at {KISAN_CALL_CENTRE_NUMBER} (Toll-Free) "
            "or visit your local Krishi Vigyan Kendra (KVK) and consult an agricultural extension officer."
        )
        preventive = [
            f"Call the Kisan Call Centre at {KISAN_CALL_CENTRE_NUMBER} (Toll-Free) for verified expert guidance.",
            "Visit your local Krishi Vigyan Kendra (KVK) or State Department of Agriculture office with a leaf sample.",
        ]
        disclaimer = (
            f"Safety Guardrail Refusal: System cannot answer safely without verified manual grounding. "
            f"Contact Kisan Call Centre ({KISAN_CALL_CENTRE_NUMBER}) or your local KVK."
        )

    return VerifiedDiagnosticResponse(
        pathogen=pathogen_label,
        confidence=bounded_score,
        verified_treatment=refusal_message,
        safe_dosages=[],
        organic_recommendations=[],
        preventive_measures=preventive,
        disclaimer=disclaimer,
        is_verified=False,
        served_by="refusal",
        degraded=True,
        is_refusal=True,
        weather_summary=weather_summary,
        citations=[],
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main Orchestrator: 5-Layer Resilient Answer Pipeline
# ══════════════════════════════════════════════════════════════════════════════

def _build_rag_prompt(
    effective_crop_type: str,
    language: str,
    context: str,
    operational_context: Optional[str] = None,
    weather_summary: Optional[WeatherSummary] = None,
    farmer_comment: Optional[str] = None,
) -> str:
    system_prompt = _BASE_PROMPT_TA if (language or "en").lower() == "ta" else _BASE_PROMPT
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
        prompt += (
            f"Local Weather: Temp {weather_summary.temperature}, "
            f"Rain Risk: {weather_summary.rain_chance}, "
            f"Spray Note: {weather_summary.spray_advisory}\n"
        )
    if farmer_comment:
        prompt += f"Farmer Comment: {farmer_comment}\n"
    prompt += f"\nExtension Context:\n{context}\n"
    return prompt


async def apply_guardrail(
    image_bytes: bytes,
    mime_type: str,
    crop_type: str,
    language: str = "en",
    farmer_comment: Optional[str] = None,
    operational_context: Optional[str] = None,
    weather_summary: Optional[WeatherSummary] = None,
    weather_band: Optional[str] = None,
    is_essential: bool = True,
) -> VerifiedDiagnosticResponse:
    """Execute the 5-Layer Resilient Answer Pipeline with Concurrency & Quota Controls:
    - Layer 0: Exact & Semantic Cache (0 API calls, 0 model compute)
    - Concurrency Gate: asyncio.Semaphore(3) to protect the 8 GB RAM budget
    - Quota Ledger Gate: Diverts non-essential calls to Layer 0 or Layer 3 when usage > 85%
    - Circuit Breaker Gate: Trips after 3 consecutive 429/503 errors from Gemini; diverts to Layer 2/3 for 60s before sending 1 probe request
    - Layer 1: Gemini Primary (8–10s timeout, up to 2 retries with jittered exponential backoff + Retry-After)
    - Layer 2: Low-Memory Local Fallback via Ollama (qwen2.5-coder:1.5b, num_ctx=2048, <=5s timeout)
    - Layer 3: Deterministic Extractive Answer from ChromaDB/BM25 top chunk (No LLM)
    - Layer 4: Honest Refusal with Kisan Call Centre (1800-180-1551) & local KVK routing
    """
    computed_w_band = compute_weather_band(weather_summary, explicit_weather_band=weather_band)
    image_hash = hashlib.sha256(image_bytes).hexdigest()[:16] if image_bytes else None

    normalized_crop = (crop_type or "").strip()

    # ── LAYER 0 (Pre-check before any API or retrieval compute) ───────────────
    cached = get_cached_answer(
        crop_type=normalized_crop,
        disease_or_comment=farmer_comment,
        language=language,
        weather_band=computed_w_band,
        image_hash=image_hash,
        weather_summary=weather_summary,
    )
    if cached is not None:
        logger.info("Serving diagnosis from Layer 0 (Cache) for crop=%r", normalized_crop)
        return cached

    # ── Concurrency Control: Max 3 concurrent heavy requests on 8 GB machine ──
    async with HEAVY_REQUEST_SEMAPHORE:
        # Resolve "Not sure" crop selection
        if normalized_crop.lower() in {"not sure", "not_sure", "unsure", "unknown", "general", ""}:
            effective_crop_type = await predict_crop_from_image(
                image_bytes=image_bytes,
                mime_type=mime_type,
                farmer_comment=farmer_comment,
            )
            # Re-check Layer 0 cache using the predicted crop
            cached_after_predict = get_cached_answer(
                crop_type=effective_crop_type,
                disease_or_comment=farmer_comment,
                language=language,
                weather_band=computed_w_band,
                image_hash=image_hash,
                weather_summary=weather_summary,
            )
            if cached_after_predict is not None:
                logger.info("Serving diagnosis from Layer 0 (Cache) after crop prediction=%r", effective_crop_type)
                return cached_after_predict
        else:
            effective_crop_type = normalized_crop

        # Ensure bare corpus crop names (e.g. "Pepper") match corpus section headers when no comment is given
        retrieval_crop_query = effective_crop_type
        if (
            not farmer_comment
            and any(effective_crop_type.lower() == c.lower() for c in CORPUS_CROPS)
        ):
            retrieval_crop_query = f"Diseases of {effective_crop_type}"

        # ── Hybrid Retrieval (ChromaDB + BM25 + CrossEncoder Reranking) ───────
        try:
            scored_chunks = await query_extension_context_scored(
                retrieval_crop_query, farmer_comment=farmer_comment, n_results=5
            )
        except Exception as exc:
            logger.error("Retrieval failed unexpectedly (%s); routing to Layer 4 refusal.", exc)
            return build_honest_refusal(
                crop_type=effective_crop_type,
                top_score=0.0,
                language=language,
                weather_summary=weather_summary,
            )

        # ── LAYER 4 Gate: Retrieval confidence below safety threshold ─────────
        top_score = scored_chunks[0][2] if scored_chunks else 0.0
        if not scored_chunks or top_score < REFUSAL_THRESHOLD:
            logger.info(
                "Retrieval score %.4f < %.2f for crop=%r; returning Layer 4 Honest Refusal.",
                top_score,
                REFUSAL_THRESHOLD,
                effective_crop_type,
            )
            return build_honest_refusal(
                crop_type=effective_crop_type,
                top_score=top_score,
                language=language,
                weather_summary=weather_summary,
            )

        # ── Quota Ledger Diversion (>85% daily usage diverts non-essential calls to Layer 0 / Layer 3) ──
        effective_essential = bool(is_essential and bool(image_bytes))
        if (not effective_essential and quota_ledger.should_divert_non_essential()) or quota_ledger.is_quota_exhausted():
            logger.info(
                "Quota ledger high-water mark reached; diverting request directly to Layer 3 (Extractive RAG)."
            )
            try:
                extractive_diverted = build_extractive_rag_answer(
                    crop_type=effective_crop_type,
                    farmer_comment=farmer_comment,
                    scored_chunks=scored_chunks,
                    weather_summary=weather_summary,
                    language=language,
                )
                store_cached_answer(
                    crop_type=effective_crop_type,
                    disease_or_comment=farmer_comment,
                    language=language,
                    weather_band=computed_w_band,
                    response=extractive_diverted,
                    image_hash=image_hash,
                )
                return extractive_diverted
            except Exception as exc:
                logger.error("Diverted Layer 3 extractive answer failed (%s); falling back to Layer 4.", exc)
                return build_honest_refusal(
                    crop_type=effective_crop_type,
                    top_score=top_score,
                    language=language,
                    weather_summary=weather_summary,
                )

        # Build citation-tagged RAG context shared by Layer 1 (Gemini) and Layer 2 (Ollama)
        citation_ids = [chunk_id for chunk_id, _, _ in scored_chunks]
        context = "\n\n---\n\n".join(
            f"[{chunk_id}] {text}" for chunk_id, text, _ in scored_chunks
        )
        prompt = _build_rag_prompt(
            effective_crop_type=effective_crop_type,
            language=language,
            context=context,
            operational_context=operational_context,
            weather_summary=weather_summary,
            farmer_comment=farmer_comment,
        )

        # ── LAYER 1: Gemini Primary (Protected by Circuit Breaker) ────────────
        cb_allowed, cb_is_probe = circuit_breaker.allow_request()
        if cb_allowed:
            try:
                gemini_resp = await call_gemini_primary(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    prompt=prompt,
                    scored_chunks=scored_chunks,
                    citation_ids=citation_ids,
                    weather_summary=weather_summary,
                    is_probe=cb_is_probe,
                )
                store_cached_answer(
                    crop_type=effective_crop_type,
                    disease_or_comment=farmer_comment,
                    language=language,
                    weather_band=computed_w_band,
                    response=gemini_resp,
                    image_hash=image_hash,
                )
                return gemini_resp
            except Exception as layer1_exc:
                logger.warning("Layer 1 (Gemini) unavailable (%s). Failing over to Layer 2 (Ollama).", layer1_exc)
        else:
            logger.warning(
                "Circuit breaker is OPEN (%.1fs remaining until probe); diverting directly to Layer 2/Layer 3.",
                circuit_breaker.seconds_until_probe(),
            )

        # ── LAYER 2: Low-RAM Local Fallback (Ollama qwen2.5-coder:1.5b, <=5s) ─
        try:
            ollama_resp = await call_ollama_secondary(
                prompt=prompt,
                scored_chunks=scored_chunks,
                citation_ids=citation_ids,
                weather_summary=weather_summary,
            )
            store_cached_answer(
                crop_type=effective_crop_type,
                disease_or_comment=farmer_comment,
                language=language,
                weather_band=computed_w_band,
                response=ollama_resp,
                image_hash=image_hash,
            )
            return ollama_resp
        except Exception as layer2_exc:
            logger.warning(
                "Layer 2 (Ollama local fallback) unavailable or timed out (%s). Failing over to Layer 3 (Extractive RAG).",
                layer2_exc,
            )

        # ── LAYER 3: Deterministic Extractive Answer (No LLM) ─────────────────
        try:
            extractive_resp = build_extractive_rag_answer(
                crop_type=effective_crop_type,
                farmer_comment=farmer_comment,
                scored_chunks=scored_chunks,
                weather_summary=weather_summary,
                language=language,
            )
            store_cached_answer(
                crop_type=effective_crop_type,
                disease_or_comment=farmer_comment,
                language=language,
                weather_band=computed_w_band,
                response=extractive_resp,
                image_hash=image_hash,
            )
            return extractive_resp
        except Exception as layer3_exc:
            logger.error("Layer 3 (Extractive RAG) failed (%s). Failing over to Layer 4 (Honest Refusal).", layer3_exc)

        # ── LAYER 4: Honest Refusal (All previous layers failed) ──────────────
        return build_honest_refusal(
            crop_type=effective_crop_type,
            top_score=top_score,
            language=language,
            weather_summary=weather_summary,
        )

