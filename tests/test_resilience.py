"""
Phase 2 Task 5: Failure Injection Tests (tests/test_resilience.py).

Automated resilience & failure-injection tests demonstrating:
1. Network Kill / 503 Injection:
   - Mock a Gemini 503 error (and network kill); assert the system falls back to
     Layer 2 (`secondary_local`) or Layer 3 (`extractive_rag`) within 3 seconds
     with `degraded=True`.
2. Circuit Breaker Trigger:
   - Send 3 failing requests; assert subsequent requests skip Gemini entirely
     (`0` Gemini calls) during the 60-second cooldown period.
3. Refusal Fallback:
   - Simulate an empty retrieval and API outage; assert Layer 4 returns HTTP 200/422
     providing the Kisan Call Centre number (`1800-180-1551`) and local KVK guidance.
"""
import asyncio
import io
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple
import uuid

from fastapi.testclient import TestClient
import httpx
from PIL import Image
import pytest

# Ensure backend directory is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
from services import rag_guardrail  # noqa: E402
from services.quota_manager import (  # noqa: E402
    circuit_breaker,
    reset_all_quotas_and_breakers,
)
from services.rag_guardrail import (  # noqa: E402
    KISAN_CALL_CENTRE_NUMBER,
    apply_guardrail,
    clear_answer_cache,
)


def _make_valid_jpeg_bytes() -> bytes:
    """Generate a valid in-memory RGB JPEG image that passes upload security checks."""
    img = Image.new("RGB", (64, 64), color=(34, 139, 34))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


SAMPLE_JPEG_BYTES = _make_valid_jpeg_bytes()

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
        0.89,
    ),
    (
        "doc_8",
        "Biological control: Apply Pseudomonas fluorescens @ 10 g/kg of seed.",
        0.74,
    ),
]


@pytest.fixture(autouse=True)
def reset_pipeline_state():
    clear_answer_cache()
    reset_all_quotas_and_breakers()
    yield
    clear_answer_cache()
    reset_all_quotas_and_breakers()


class Gemini503OutageError(Exception):
    """Simulated Gemini HTTP 503 Service Unavailable error."""
    status_code = 503

    def __init__(self, message: str = "503 Service Unavailable: Gemini backend overloaded"):
        super().__init__(message)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Network Kill / 503 Injection (Fallback to Layer 2 / Layer 3 within 3s, degraded=True)
# ══════════════════════════════════════════════════════════════════════════════

def test_network_kill_503_injection_fallback_to_layer2_within_3s(monkeypatch):
    """Mock a Gemini 503 error with local Ollama available; assert fallback to Layer 2
    (`secondary_local`) completes within 3 seconds with `degraded=True`."""

    async def mock_retrieval(*args, **kwargs):
        return SAMPLE_CHUNKS

    async def mock_gemini_503(*args, **kwargs):
        raise Gemini503OutageError("503 Service Unavailable")

    class MockOllamaClient:
        def __init__(self, timeout=None, **kwargs):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, json: Dict[str, Any] = None, **kwargs):
            class Resp:
                status_code = 200

                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "response": json_mod.dumps(
                            {
                                "pathogen": "Alternaria solani (Early Blight)",
                                "confidence": 0.86,
                                "verified_treatment": "Spray Mancozeb (0.2%) twice at 15 days interval [doc_7].",
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
                                "preventive_measures": ["Remove infected plant debris [doc_7]."],
                                "disclaimer": "Local fallback grounded in TNAU manual.",
                                "is_verified": True,
                            }
                        )
                    }

            import json as json_mod
            return Resp()

    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", mock_gemini_503)
    monkeypatch.setattr(httpx, "AsyncClient", MockOllamaClient)

    start_time = time.perf_counter()
    result = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_JPEG_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="concentric rings on leaves",
        )
    )
    elapsed = time.perf_counter() - start_time

    assert elapsed < 3.0, f"Expected fallback within 3.0s, took {elapsed:.2f}s"
    assert result.degraded is True
    assert result.served_by == "secondary_local"
    assert result.is_verified is True
    assert "Mancozeb" in result.verified_treatment


def test_network_kill_503_injection_fallback_to_layer3_within_3s(monkeypatch):
    """Mock a Gemini 503 error AND local Ollama network kill; assert fallback to Layer 3
    (`extractive_rag`) completes within 3 seconds with `degraded=True`."""

    async def mock_retrieval(*args, **kwargs):
        return SAMPLE_CHUNKS

    async def mock_gemini_503(*args, **kwargs):
        raise Gemini503OutageError("503 Service Unavailable — network kill")

    async def mock_ollama_network_kill(*args, **kwargs):
        raise httpx.ConnectError("Connection refused: Ollama not running on 127.0.0.1:11434")

    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", mock_gemini_503)
    monkeypatch.setattr(rag_guardrail, "call_ollama_secondary", mock_ollama_network_kill)

    start_time = time.perf_counter()
    result = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_JPEG_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="early blight spots",
        )
    )
    elapsed = time.perf_counter() - start_time

    assert elapsed < 3.0, f"Expected fallback within 3.0s, took {elapsed:.2f}s"
    assert result.degraded is True
    assert result.served_by == "extractive_rag"
    assert result.is_verified is True
    assert "Disease Name:" in result.verified_treatment
    assert "Treatment & Dosage:" in result.verified_treatment
    assert "Pre-Harvest Interval (PHI):" in result.verified_treatment
    assert "Source Citation:" in result.verified_treatment


# ══════════════════════════════════════════════════════════════════════════════
# 2. Circuit Breaker Trigger (3 Failing Requests -> Subsequent Skip Gemini in Cooldown)
# ══════════════════════════════════════════════════════════════════════════════

def test_circuit_breaker_trigger_3_failing_requests_skip_gemini_during_cooldown(monkeypatch):
    """Send 3 failing requests; assert the circuit breaker trips to OPEN and all
    subsequent requests skip Gemini entirely during the 60-second cooldown period."""
    fake_now = 5000.0

    def fake_clock() -> float:
        return fake_now

    circuit_breaker.reset()
    circuit_breaker._clock = fake_clock

    gemini_call_count = 0

    async def mock_retrieval(*args, **kwargs):
        return SAMPLE_CHUNKS

    async def mock_gemini_503(*args, **kwargs):
        nonlocal gemini_call_count
        gemini_call_count += 1
        raise Gemini503OutageError("503 Service Unavailable")

    async def mock_ollama_offline(*args, **kwargs):
        raise httpx.ConnectError("Ollama offline")

    # Configure 0 retries per request so each failing request represents 1 Gemini 503 failure,
    # directly testing 3 consecutive failing requests tripping the breaker on the 3rd request.
    monkeypatch.setattr(rag_guardrail.settings, "GEMINI_MAX_RETRIES", 0)
    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", mock_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", mock_gemini_503)
    monkeypatch.setattr(rag_guardrail, "call_ollama_secondary", mock_ollama_offline)

    # Send 3 failing requests (each with distinct query/bytes to bypass Layer 0 cache)
    for i in range(1, 4):
        resp = asyncio.run(
            apply_guardrail(
                image_bytes=SAMPLE_JPEG_BYTES + bytes([i]),
                mime_type="image/jpeg",
                crop_type="Tomato",
                farmer_comment=f"failing request {i}",
            )
        )
        assert resp.degraded is True
        assert resp.served_by == "extractive_rag"

    # After 3 failing requests, Gemini was called exactly 3 times and circuit breaker is OPEN
    assert gemini_call_count == 3
    assert circuit_breaker.state == "OPEN"
    assert circuit_breaker.is_tripped() is True

    # Advance clock within the 60-second cooldown window (+25s and +50s)
    for offset in (25.0, 50.0):
        fake_now = 5000.0 + offset
        clear_answer_cache()
        subsequent_resp = asyncio.run(
            apply_guardrail(
                image_bytes=SAMPLE_JPEG_BYTES + bytes([int(offset)]),
                mime_type="image/jpeg",
                crop_type="Tomato",
                farmer_comment=f"cooldown request at {offset}s",
            )
        )
        assert subsequent_resp.degraded is True
        assert subsequent_resp.served_by == "extractive_rag"
        # Assert Gemini was completely skipped (still 3 total calls)
        assert gemini_call_count == 3


# ══════════════════════════════════════════════════════════════════════════════
# 3. Refusal Fallback (Empty Retrieval + API Outage -> Layer 4 HTTP 200/422 with Kisan Call Centre)
# ══════════════════════════════════════════════════════════════════════════════

def test_refusal_fallback_empty_retrieval_and_api_outage_returns_kisan_call_centre(monkeypatch):
    """Simulate an empty retrieval and API outage; assert Layer 4 returns HTTP 200/422
    providing the Kisan Call Centre number (1800-180-1551) and local KVK guidance."""

    async def empty_retrieval(*args, **kwargs):
        return []

    async def mock_gemini_outage(*args, **kwargs):
        raise Gemini503OutageError("503 Service Unavailable — total API outage")

    async def mock_ollama_outage(*args, **kwargs):
        raise httpx.ConnectError("Ollama offline")

    monkeypatch.setattr(rag_guardrail, "query_extension_context_scored", empty_retrieval)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", mock_gemini_outage)
    monkeypatch.setattr(rag_guardrail, "call_ollama_secondary", mock_ollama_outage)

    # 1. Direct pipeline verification
    direct_res = asyncio.run(
        apply_guardrail(
            image_bytes=SAMPLE_JPEG_BYTES,
            mime_type="image/jpeg",
            crop_type="Tomato",
            farmer_comment="unknown symptom during outage",
        )
    )
    assert direct_res.served_by == "refusal"
    assert direct_res.degraded is True
    assert direct_res.is_verified is False
    assert direct_res.is_refusal is True
    assert KISAN_CALL_CENTRE_NUMBER in direct_res.verified_treatment
    assert KISAN_CALL_CENTRE_NUMBER in direct_res.disclaimer
    assert "KVK" in direct_res.verified_treatment or "Krishi Vigyan Kendra" in direct_res.verified_treatment

    # 2. Full FastAPI HTTP endpoint (`POST /api/scan`) verification
    client = TestClient(app)
    unique_email = f"resilience_{uuid.uuid4().hex[:8]}@agrosphere.org"
    password = "StrongPassword123!"
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "Resilience Farmer",
            "email": unique_email,
            "password": password,
        },
    )
    assert signup_resp.status_code in (200, 201), signup_resp.text
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": unique_email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    http_resp = client.post(
        "/api/scan",
        headers={"Authorization": f"Bearer {token}"},
        files={"image": ("leaf.jpg", SAMPLE_JPEG_BYTES, "image/jpeg")},
        data={"crop_type": "Tomato", "farmer_comment": "empty retrieval outage test"},
    )
    assert http_resp.status_code in (200, 422)
    payload = http_resp.json()
    body_text = json.dumps(payload)
    assert KISAN_CALL_CENTRE_NUMBER in body_text
    if http_resp.status_code == 200:
        assert payload["served_by"] == "refusal"
        assert payload["degraded"] is True
        assert payload["is_refusal"] is True
        assert payload["is_verified"] is False
