"""
Phase 2 Task 1 Verification Suite: Layered Answer Pipeline (tests/test_layered_pipeline.py).

Verifies:
- Every response includes `served_by` (cache, gemini, secondary_local, extractive_rag, refusal) and `degraded` (bool).
- Layer 0 (Cache): Exact and semantic caching across (crop, disease, language, weather_band) with 0 API calls or model compute.
- Layer 1 (Gemini Primary): 8–10s timeout, up to 2 retries with jittered exponential backoff, honoring Retry-After header.
- Layer 2 (Low-Memory Local Fallback): Targets Ollama `qwen2.5-coder:1.5b` (configurable via .env), sets `num_ctx: 2048`, receives the same retrieved RAG context, and fails over within 5s to Layer 3 if unavailable.
- Layer 3 (Deterministic Extractive Answer - No LLM): Assembles diagnosis from top retrieved chunk using template (Disease Name, Treatment & Dosage, Pre-Harvest Interval (PHI), Source Citation).
- Layer 4 (Honest Refusal): Returns honest refusal with Kisan Call Centre (1800-180-1551) and local KVK routing when retrieval confidence < threshold or all previous layers fail.
"""
import asyncio
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

import httpx
import pytest

# Add backend directory to sys.path so imports match backend runtime
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from schemas.diagnostic import WeatherSummary  # noqa: E402
from services import rag_guardrail  # noqa: E402
from services.rag_guardrail import (  # noqa: E402
    DEFAULT_OLLAMA_MODEL,
    GEMINI_MAX_RETRIES,
    GEMINI_TIMEOUT_SECONDS,
    KISAN_CALL_CENTRE_NUMBER,
    OLLAMA_NUM_CTX,
    OLLAMA_TIMEOUT_SECONDS,
    apply_guardrail,
    clear_answer_cache,
)

SAMPLE_IMAGE_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
SAMPLE_WEATHER = WeatherSummary(
    temperature="28°C",
    rain_chance="Low (0.0mm)",
    spray_advisory="Optimal weather for foliar spraying.",
)
SAMPLE_CHUNKS: List[Tuple[str, str, float]] = [
    (
        "doc_7",
        (
            "1. Early Blight : Alternaria solani\n"
            "Symptoms: Dark brown spots with concentric rings on leaves.\n"
            "Management: Remove and destroy infected plant debris. "
            "Spray Mancozeb (0.2%) or Carbendazim (0.1%) twice at 15 days interval. "
            "Pre-harvest interval is 7 days."
        ),
        0.88,
    ),
    (
        "doc_8",
        "Biological control: Apply Pseudomonas fluorescens @ 10 g/kg of seed.",
        0.71,
    ),
]


@pytest.fixture(autouse=True)
def clean_cache():
    clear_answer_cache()
    yield
    clear_answer_cache()


# ── 1. Layer 0: Exact & Semantic Cache (0 API Calls, 0 Model Compute) ─────────
def test_layer0_exact_and_semantic_cache_zero_compute(monkeypatch):
    retrieval_calls = 0
    gemini_calls = 0

    async def mock_retrieval(crop_type: str, farmer_comment=None, n_results: int = 5):
        nonlocal retrieval_calls
        retrieval_calls += 1
        return SAMPLE_CHUNKS

    class DummyResp:
        text = json.dumps(
            {
                "pathogen": "Alternaria solani (Early Blight)",
                "confidence": 0.92,
                "verified_treatment": "Spray Mancozeb 0.2% [doc_7].",
                "safe_dosages": [
                    {
                        "chemical_name": "Mancozeb",
                        "dosage": "0.2",
                        "unit": "%",
                        "max_frequency": "Twice at 15 days interval",
                        "pre_harvest_interval_days": 7,
                    }
                ],
                "organic_recommendations": ["Apply Pseudomonas fluorescens [doc_8]."],
                "preventive_measures": ["Remove infected debris [doc_7]."],
                "disclaimer": "Verified per TNAU Manual.",
                "is_verified": True,
            }
        )

    async def mock_gemini_generate(*args, **kwargs):
        nonlocal gemini_calls
        gemini_calls += 1
        return DummyResp()

    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", mock_gemini_generate)

    # First call: served by Layer 1 (gemini) and populates Layer 0 cache
    first = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            language="en",
            farmer_comment="Early blight concentric rings on leaves",
            weather_summary=SAMPLE_WEATHER,
        )
    )
    assert first.served_by == "gemini"
    assert first.degraded is False
    assert retrieval_calls == 1
    assert gemini_calls == 1

    # Second call (Exact match): 0 retrieval calls, 0 Gemini calls -> served_by="cache"
    second_exact = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            language="en",
            farmer_comment="Early blight concentric rings on leaves",
            weather_summary=SAMPLE_WEATHER,
        )
    )
    assert second_exact.served_by == "cache"
    assert second_exact.degraded is False
    assert second_exact.pathogen == "Alternaria solani (Early Blight)"
    assert retrieval_calls == 1  # 0 additional retrieval/reranker compute
    assert gemini_calls == 1     # 0 additional LLM API calls

    # Third call (Semantic match: different phrasing of the same disease, same crop/lang/weather band)
    third_semantic = asyncio.run(
        apply_guardrail(
            image_bytes=b"different_image_bytes_for_semantic_query",
            mime_type="image/jpeg",
            crop_type="Tomato",
            language="en",
            farmer_comment="alternaria solani target board symptoms on my tomato plant",
            weather_summary=SAMPLE_WEATHER,
        )
    )
    assert third_semantic.served_by == "cache"
    assert third_semantic.degraded is False
    assert third_semantic.pathogen == "Alternaria solani (Early Blight)"
    assert retrieval_calls == 1  # Still 0 additional model compute
    assert gemini_calls == 1     # Still 0 additional API calls

    # Fourth call (Different weather band -> High rain instead of Low rain): must NOT hit Low-rain cache
    high_rain_weather = WeatherSummary(
        temperature="28°C",
        rain_chance="High (12.0mm)",
        spray_advisory="Postpone spraying due to rain.",
    )
    fourth_diff_weather = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            language="en",
            farmer_comment="Early blight concentric rings on leaves",
            weather_summary=high_rain_weather,
        )
    )
    assert fourth_diff_weather.served_by == "gemini"
    assert gemini_calls == 2


# ── 2. Layer 1: Gemini Timeout (8–10s), Max 2 Retries, Jittered Backoff & Retry-After ──
def test_layer1_retries_with_retry_after_header_and_succeeds(monkeypatch):
    assert 8.0 <= GEMINI_TIMEOUT_SECONDS <= 10.0
    assert GEMINI_MAX_RETRIES == 2

    sleep_delays: List[float] = []
    attempts = 0

    async def mock_sleep(delay: float):
        sleep_delays.append(delay)

    class RateLimitedError(Exception):
        def __init__(self, retry_after_val: str):
            super().__init__("429 Too Many Requests")
            self.headers = {"Retry-After": retry_after_val}

    class SuccessResp:
        text = json.dumps(
            {
                "pathogen": "Alternaria solani",
                "confidence": 0.90,
                "verified_treatment": "Spray Mancozeb 0.2% [doc_7].",
                "safe_dosages": [],
                "organic_recommendations": [],
                "preventive_measures": [],
                "disclaimer": "TNAU Manual.",
                "is_verified": True,
            }
        )

    async def flaky_gemini(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitedError("1.5")
        if attempts == 2:
            raise RuntimeError("Transient 503 error without Retry-After")
        return SuccessResp()

    async def mock_retrieval(*args, **kwargs):
        return SAMPLE_CHUNKS

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", flaky_gemini)

    result = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="early blight",
        )
    )

    assert attempts == 3  # 1 initial + 2 retries
    assert len(sleep_delays) == 2
    # First retry honored Retry-After: 1.5s
    assert sleep_delays[0] == pytest.approx(1.5)
    # Second retry used jittered exponential backoff (0.5 * 2^1 + jitter in [0.05, 0.35])
    assert 1.05 <= sleep_delays[1] <= 1.35
    assert result.served_by == "gemini"
    assert result.degraded is False


# ── 3. Layer 2: Low-Memory Local Fallback (Ollama qwen2.5-coder:1.5b, num_ctx=2048) ──
def test_layer2_ollama_fallback_uses_qwen_and_num_ctx_2048(monkeypatch):
    assert DEFAULT_OLLAMA_MODEL == "qwen2.5-coder:1.5b"
    assert OLLAMA_NUM_CTX == 2048
    assert OLLAMA_TIMEOUT_SECONDS <= 5.0

    captured_ollama_payload: Dict[str, Any] = {}

    async def mock_retrieval(*args, **kwargs):
        return SAMPLE_CHUNKS

    async def failing_gemini(*args, **kwargs):
        raise RuntimeError("Gemini API 503 Unavailable")

    async def noop_sleep(_delay: float):
        pass

    class MockAsyncClient:
        def __init__(self, timeout=None, **kwargs):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, json: Dict[str, Any] = None, **kwargs):
            captured_ollama_payload["url"] = url
            captured_ollama_payload["json"] = json
            captured_ollama_payload["timeout"] = self.timeout

            class Resp:
                status_code = 200

                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "response": json_module.dumps(
                            {
                                "pathogen": "Alternaria solani (Early Blight)",
                                "confidence": 0.85,
                                "verified_treatment": "Spray Mancozeb (0.2%) twice at 15 days interval [doc_7].",
                                "safe_dosages": [
                                    {
                                        "chemical_name": "Mancozeb",
                                        "dosage": "0.2",
                                        "unit": "%",
                                        "max_frequency": "Twice at 15 days interval",
                                        "pre_harvest_interval_days": 7,
                                    },
                                    {
                                        "chemical_name": "UngroundedFakeChem",
                                        "dosage": "99",
                                        "unit": "L",
                                        "max_frequency": "Daily",
                                        "pre_harvest_interval_days": 1,
                                    },
                                ],
                                "organic_recommendations": ["Pseudomonas fluorescens [doc_8]"],
                                "preventive_measures": ["Remove infected debris [doc_7]"],
                                "disclaimer": "Local fallback grounded in TNAU context.",
                                "is_verified": True,
                            }
                        )
                    }

            import json as json_module
            return Resp()

    monkeypatch.setattr(asyncio, "sleep", noop_sleep)
    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", failing_gemini)
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    result = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="concentric rings on leaves",
        )
    )

    assert result.served_by == "secondary_local"
    assert result.degraded is True
    assert result.is_verified is True
    # Verify Ollama model, num_ctx=2048, timeout <= 5s, and shared RAG context
    sent_json = captured_ollama_payload["json"]
    assert sent_json["model"] == "qwen2.5-coder:1.5b"
    assert sent_json["options"]["num_ctx"] == 2048
    assert captured_ollama_payload["timeout"] <= 5.0
    assert "[doc_7]" in sent_json["prompt"]
    assert "Alternaria solani" in sent_json["prompt"]
    # Verify chemical hallucination stripping still protects Layer 2 output
    assert len(result.safe_dosages) == 1
    assert result.safe_dosages[0].chemical_name == "Mancozeb"


# ── 4. Layer 3: Deterministic Extractive Answer (No LLM) on Layer 1 + 2 Failure ──
def test_layer3_deterministic_extractive_rag_when_gemini_and_ollama_fail(monkeypatch):
    async def mock_retrieval(*args, **kwargs):
        return SAMPLE_CHUNKS

    async def failing_gemini(*args, **kwargs):
        raise RuntimeError("Gemini primary unreachable")

    async def failing_ollama(*args, **kwargs):
        raise httpx.ConnectError("Ollama is not running on port 11434")

    async def noop_sleep(_delay: float):
        pass

    monkeypatch.setattr(asyncio, "sleep", noop_sleep)
    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", failing_gemini)
    monkeypatch.setattr(rag_guardrail, "call_ollama_secondary", failing_ollama)

    result = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="early blight",
        )
    )

    assert result.served_by == "extractive_rag"
    assert result.degraded is True
    assert result.is_verified is True
    assert result.is_refusal is False
    # Must contain all 4 required template sections
    assert "Disease Name:" in result.verified_treatment
    assert "Treatment & Dosage:" in result.verified_treatment
    assert "Pre-Harvest Interval (PHI):" in result.verified_treatment
    assert "Source Citation:" in result.verified_treatment
    assert "[doc_7]" in result.verified_treatment
    assert "doc_7" in result.citations
    # Grounded dosages extracted deterministically from top chunk
    chem_names = [d.chemical_name for d in result.safe_dosages]
    assert "Mancozeb" in chem_names
    assert "Carbendazim" in chem_names
    assert result.safe_dosages[0].pre_harvest_interval_days == 7


# ── 5. Layer 4: Honest Refusal on Low Retrieval Confidence or Total Failure ──
def test_layer4_honest_refusal_low_confidence_and_all_layers_failed(monkeypatch):
    gemini_called = False

    async def low_score_retrieval(*args, **kwargs):
        return [("doc_99", "Unrelated text about ornamental flowers.", 0.12)]

    async def should_not_be_called(*args, **kwargs):
        nonlocal gemini_called
        gemini_called = True
        raise AssertionError("Gemini must not be called when retrieval score < REFUSAL_THRESHOLD")

    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", low_score_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", should_not_be_called)

    refusal_resp = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Dragonfruit",
            farmer_comment="unknown spots",
        )
    )

    assert gemini_called is False
    assert refusal_resp.served_by == "refusal"
    assert refusal_resp.degraded is True
    assert refusal_resp.is_verified is False
    assert refusal_resp.is_refusal is True
    assert KISAN_CALL_CENTRE_NUMBER in refusal_resp.verified_treatment
    assert "KVK" in refusal_resp.verified_treatment or "Krishi Vigyan Kendra" in refusal_resp.verified_treatment
    assert refusal_resp.safe_dosages == []


# ── 6. Quota Ledger: Per-Day / Per-Minute SQLite + Memory & >85% Non-Essential Diversion ──
def test_quota_ledger_sqlite_persistence_and_85_percent_diversion(monkeypatch):
    from database import SessionLocal
    from models.user import QuotaLedgerRecord
    from schemas.irrigation import IrrigationRequest
    from services import irrigation_service
    from services.quota_manager import quota_ledger

    quota_ledger.reset()
    quota_ledger.set_usage(daily_calls=0, minute_calls=0, daily_limit=100, minute_limit=60)

    # Record 2 calls and verify both in-memory and SQLite persistence
    status = quota_ledger.record_call(count=2)
    assert status["daily_calls"] == 2
    assert status["minute_calls"] == 2
    assert status["above_85_percent"] is False
    assert quota_ledger.should_divert_non_essential() is False

    db = SessionLocal()
    try:
        rows = db.query(QuotaLedgerRecord).all()
        bucket_types = {r.bucket_type: r.call_count for r in rows}
        assert bucket_types.get("day") == 2
        assert bucket_types.get("minute") == 2
    finally:
        db.close()

    # Advance usage to 86% of daily limit (86 / 100)
    quota_ledger.set_usage(daily_calls=86, minute_calls=5, daily_limit=100, minute_limit=60)
    assert quota_ledger.should_divert_non_essential() is True

    # Verify non-essential calls are diverted to Layer 0 / Layer 3 with 0 Gemini calls:
    # (a) Non-essential pre-detection (`predict_crop_from_image`) is bypassed
    pre_detect_called = False

    async def should_not_call_gemini(*args, **kwargs):
        nonlocal pre_detect_called
        pre_detect_called = True
        raise AssertionError("Non-essential Gemini call must be diverted when quota > 85%")

    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", should_not_call_gemini)
    detected = asyncio.run(rag_guardrail.predict_crop_from_image(SAMPLE_IMAGE_BYTES, "image/jpeg"))
    assert detected == "Unknown Crop"
    assert pre_detect_called is False

    # (b) Irrigation advisory (`calculate_irrigation`) runs 100% deterministically (0 Gemini calls)
    irr_req = IrrigationRequest(
        crop_type="Tomato",
        growth_stage="mid-stage",
        soil_type="loam",
        field_size_hectares=1.0,
        soil_moisture_percentage=40.0,
        temperature_celsius=30.0,
        rainfall_probability_percent=10.0,
        language="en",
    )
    irr_resp = asyncio.run(irrigation_service.calculate_irrigation(irr_req))
    assert irr_resp.water_required_liters > 0
    assert "Apply" in irr_resp.recommended_schedule

    # (c) Essential multimodal leaf scan (`apply_guardrail` with real image bytes) STILL gets Gemini quota at 86%
    multimodal_gemini_calls = 0

    class MultimodalResp:
        text = json.dumps(
            {
                "pathogen": "Alternaria solani (Early Blight)",
                "confidence": 0.93,
                "verified_treatment": "Spray Mancozeb 0.2% [doc_7].",
                "safe_dosages": [],
                "organic_recommendations": [],
                "preventive_measures": [],
                "disclaimer": "Verified.",
                "is_verified": True,
            }
        )

    async def mock_multimodal_gemini(*args, **kwargs):
        nonlocal multimodal_gemini_calls
        multimodal_gemini_calls += 1
        return MultimodalResp()

    async def mock_retrieval(*args, **kwargs):
        return SAMPLE_CHUNKS

    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", mock_multimodal_gemini)

    scan_resp = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="spots on leaf",
            is_essential=True,
        )
    )
    assert multimodal_gemini_calls == 1
    assert scan_resp.served_by == "gemini"
    assert scan_resp.degraded is False

    # (d) Non-essential pipeline call (`is_essential=False`) at >85% quota diverts directly to Layer 3 (0 Gemini calls)
    clear_answer_cache()
    diverted_resp = asyncio.run(
        apply_guardrail(
            image_bytes=b"",
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="early blight",
            is_essential=False,
        )
    )
    assert multimodal_gemini_calls == 1  # No additional Gemini call made
    assert diverted_resp.served_by == "extractive_rag"
    assert diverted_resp.degraded is True


# ── 7. Per-User Rate Limiting: 20 Scans / User / Day -> HTTP 429 with Retry Window ──
def test_per_user_rate_limit_20_scans_per_day_returns_429():
    from fastapi import HTTPException
    from services.quota_manager import USER_DAILY_SCAN_LIMIT, enforce_user_daily_scan_limit, user_scan_limiter

    user_scan_limiter.reset()
    assert USER_DAILY_SCAN_LIMIT == 20

    user_a_id = 701
    user_b_id = 702

    # First 20 scans for user A succeed
    for i in range(1, 21):
        count = enforce_user_daily_scan_limit(user_id=user_a_id)
        assert count == i

    # 21st scan for user A raises HTTP 429 with Retry-After header and clear retry window
    with pytest.raises(HTTPException) as exc_info:
        enforce_user_daily_scan_limit(user_id=user_a_id)

    err = exc_info.value
    assert err.status_code == 429
    assert "20 scans per user per day exceeded" in err.detail
    assert "Retry window:" in err.detail
    assert err.headers is not None
    assert "Retry-After" in err.headers
    assert int(err.headers["Retry-After"]) > 0
    assert err.headers.get("X-RateLimit-Limit") == "20"
    assert err.headers.get("X-RateLimit-Remaining") == "0"

    # User B still has a fresh 20-scan quota
    assert enforce_user_daily_scan_limit(user_id=user_b_id) == 1


# ── 8. Concurrency Control: asyncio.Semaphore(3) Caps Heavy Requests at 3 ──
def test_heavy_request_semaphore_limits_concurrency_to_3(monkeypatch):
    from services.quota_manager import HEAVY_REQUEST_SEMAPHORE, MAX_CONCURRENT_HEAVY_REQUESTS

    assert MAX_CONCURRENT_HEAVY_REQUESTS == 3
    assert isinstance(HEAVY_REQUEST_SEMAPHORE, asyncio.Semaphore)

    active_Now = 0
    peak_active = 0

    async def slow_retrieval(*args, **kwargs):
        nonlocal active_Now, peak_active
        active_Now += 1
        peak_active = max(peak_active, active_Now)
        await asyncio.sleep(0.03)
        active_Now -= 1
        return SAMPLE_CHUNKS

    class QuickResp:
        text = json.dumps(
            {
                "pathogen": "Alternaria solani",
                "confidence": 0.91,
                "verified_treatment": "Spray Mancozeb 0.2% [doc_7].",
                "safe_dosages": [],
                "organic_recommendations": [],
                "preventive_measures": [],
                "disclaimer": "Verified.",
                "is_verified": True,
            }
        )

    async def quick_gemini(*args, **kwargs):
        return QuickResp()

    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", slow_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", quick_gemini)

    async def run_6_concurrent_scans():
        tasks = [
            apply_guardrail(
                image_bytes=SAMPLE_IMAGE_BYTES + bytes([idx]),
                mime_type="image/jpeg",
                crop_type=f"Tomato_{idx}",
                farmer_comment=f"distinct query {idx}",
            )
            for idx in range(6)
        ]
        return await asyncio.gather(*tasks)

    results = asyncio.run(run_6_concurrent_scans())
    assert len(results) == 6
    assert 1 <= peak_active <= 3  # Strictly capped at 3 concurrent heavy requests


# ── 9. Circuit Breaker: Trips After 3 Consecutive 429/503s, 60s Cooldown, Single Probe ──
def test_circuit_breaker_trips_after_3_errors_diverts_for_60s_and_probes(monkeypatch):
    from services.quota_manager import circuit_breaker

    fake_now = 1000.0

    def fake_clock() -> float:
        return fake_now

    circuit_breaker.reset()
    circuit_breaker._clock = fake_clock

    gemini_calls = 0

    class Gemini503Error(Exception):
        status_code = 503

        def __init__(self):
            super().__init__("503 Service Unavailable")

    async def failing_503_gemini(*args, **kwargs):
        nonlocal gemini_calls
        gemini_calls += 1
        raise Gemini503Error()

    async def failing_ollama(*args, **kwargs):
        raise httpx.ConnectError("Ollama offline")

    async def noop_sleep(_delay: float):
        pass

    async def mock_retrieval(*args, **kwargs):
        return SAMPLE_CHUNKS

    monkeypatch.setattr(asyncio, "sleep", noop_sleep)
    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", failing_503_gemini)
    monkeypatch.setattr(rag_guardrail, "call_ollama_secondary", failing_ollama)

    # 1st request: Gemini attempts 3 times (initial + 2 retries), all 503 -> trips circuit breaker!
    resp1 = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="query 1",
        )
    )
    assert gemini_calls == 3
    assert circuit_breaker.state == "OPEN"
    assert circuit_breaker.is_tripped() is True
    assert resp1.served_by == "extractive_rag"
    assert resp1.degraded is True

    # Within 60s cooldown (e.g., t = +30s): traffic is diverted directly to Layer 2/3 with 0 Gemini calls
    fake_now = 1030.0
    clear_answer_cache()
    resp_during_cooldown = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="query during cooldown",
        )
    )
    assert gemini_calls == 3  # 0 new Gemini calls while circuit is OPEN
    assert resp_during_cooldown.served_by == "extractive_rag"

    # At t = +60.5s: circuit transitions to HALF_OPEN and allows a SINGLE probe request (no retries)
    fake_now = 1060.5
    assert circuit_breaker.state == "HALF_OPEN"

    # Verify concurrent gating in HALF_OPEN: first caller gets (True, True), second gets (False, False)
    allowed_first, is_probe_first = circuit_breaker.allow_request()
    allowed_second, is_probe_second = circuit_breaker.allow_request()
    assert (allowed_first, is_probe_first) == (True, True)
    assert (allowed_second, is_probe_second) == (False, False)
    # Reset probe_in_flight so apply_guardrail can execute the probe
    circuit_breaker.probe_in_flight = False

    # Now let the probe request succeed -> circuit closes
    class ProbeSuccessResp:
        text = json.dumps(
            {
                "pathogen": "Alternaria solani (Early Blight)",
                "confidence": 0.94,
                "verified_treatment": "Spray Mancozeb 0.2% [doc_7].",
                "safe_dosages": [],
                "organic_recommendations": [],
                "preventive_measures": [],
                "disclaimer": "Verified.",
                "is_verified": True,
            }
        )

    async def probe_success_gemini(*args, **kwargs):
        nonlocal gemini_calls
        gemini_calls += 1
        return ProbeSuccessResp()

    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", probe_success_gemini)
    clear_answer_cache()
    probe_resp = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_IMAGE_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="probe after 60s",
        )
    )
    assert gemini_calls == 4  # Exactly 1 probe request sent
    assert probe_resp.served_by == "gemini"
    assert probe_resp.degraded is False
    assert circuit_breaker.state == "CLOSED"
    assert circuit_breaker.consecutive_failures == 0


# ── 10. Task 3: API Usage Optimization (100% Deterministic FAO-56, Yield & Urban Gardening) ──
def test_task3_deterministic_irrigation_yield_and_urban_zero_llm_dependency():
    import ast
    from schemas.irrigation import IrrigationRequest
    from schemas.urban_gardening import UrbanGardeningRequest
    from schemas.yield_estimator import YieldEstimatorRequest
    from services import irrigation_service, urban_gardening_service, yield_estimator_service

    # 1. Verify AST of all 3 services has ZERO LLM / network client imports
    for svc_mod in (irrigation_service, yield_estimator_service, urban_gardening_service):
        src_path = Path(svc_mod.__file__).resolve()
        source = src_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
        forbidden = {"google", "google.genai", "genai", "openai", "httpx", "requests"}
        assert imported_names.isdisjoint(forbidden), (
            f"{src_path.name} must have zero LLM/HTTP dependency, found {imported_names & forbidden}"
        )
        assert not hasattr(svc_mod, "_client"), f"{src_path.name} must not instantiate an LLM _client"

    # 2. Verify FAO-56 irrigation runs 100% deterministically (identical inputs -> identical outputs)
    irr_req = IrrigationRequest(
        crop_type="Tomato",
        growth_stage="mid-stage",
        soil_type="loam",
        field_size_hectares=2.0,
        soil_moisture_percentage=35.0,
        temperature_celsius=31.0,
        rainfall_probability_percent=20.0,
        language="en",
    )
    irr_1 = asyncio.run(irrigation_service.calculate_irrigation(irr_req))
    irr_2 = asyncio.run(irrigation_service.calculate_irrigation(irr_req))
    assert irr_1.model_dump() == irr_2.model_dump()
    assert irr_1.water_required_liters > 0
    assert len(irr_1.actionable_tips) >= 3

    # 3. Verify Yield Estimator runs 100% deterministically with crop-specific drivers
    yield_req = YieldEstimatorRequest(
        crop_type="Almonds",
        field_size_hectares=3.0,
        soil_type="loam",
        irrigation_type="drip",
        weather_condition="optimal",
        historical_yield_tons=6.0,
        language="en",
    )
    y_1 = asyncio.run(yield_estimator_service.predict_yield(yield_req))
    y_2 = asyncio.run(yield_estimator_service.predict_yield(yield_req))
    assert y_1.model_dump() == y_2.model_dump()
    assert y_1.estimated_yield_tons > 0
    assert any("chill" in d.lower() or "bloom" in d.lower() for d in y_1.key_yield_drivers)
    assert len(y_1.optimization_suggestions) == 4

    # 4. Verify Urban Gardening remains 100% rule-based
    ug_req = UrbanGardeningRequest(
        plant_type="Tomato",
        space_type="balcony",
        sunlight_hours=7.5,
        container_size=15.0,
        language="en",
    )
    ug_1 = urban_gardening_service.advise_urban_gardening(ug_req)
    ug_2 = urban_gardening_service.advise_urban_gardening(ug_req)
    assert ug_1.model_dump() == ug_2.model_dump()
    assert len(ug_1.actionable_tips) >= 4


# ── 11. Task 4: UI Degraded Status Banner Verification ──
def test_task4_ui_degraded_status_banner_display():
    scan_page_path = REPO_ROOT / "frontend" / "app" / "scan" / "page.tsx"
    banner_comp_path = REPO_ROOT / "frontend" / "app" / "components" / "DegradedStatusBanner.tsx"

    assert scan_page_path.exists()
    assert banner_comp_path.exists()

    scan_src = scan_page_path.read_text(encoding="utf-8")
    banner_src = banner_comp_path.read_text(encoding="utf-8")

    # Verify scan/page.tsx imports and renders DegradedStatusBanner with degraded & served_by props
    assert "DegradedStatusBanner" in scan_src
    assert "degraded={scanResult.degraded}" in scan_src
    assert "servedBy={scanResult.served_by}" in scan_src

    # Verify DegradedStatusBanner detects `degraded` and displays prominent fallback layer text
    assert 'data-testid="degraded-status-banner"' in banner_src
    assert "Generated via offline extractive backup" in banner_src
    assert "Generated via local fallback model" in banner_src
    assert "extractive_rag" in banner_src
    assert "secondary_local" in banner_src


