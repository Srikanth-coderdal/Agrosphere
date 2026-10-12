import asyncio
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import Base, engine  # noqa: E402
from services import rag_guardrail  # noqa: E402
from services.rag_guardrail import call_gemini_primary  # noqa: E402


@pytest.fixture(autouse=True)
def make_tables():
    Base.metadata.create_all(bind=engine)
    yield


def test_long_retry_after_fails_over_without_sleeping(monkeypatch):
    sleeps = []
    attempts = 0

    async def fake_sleep(delay):
        sleeps.append(delay)

    class RateLimited(Exception):
        def __init__(self):
            super().__init__("429 Too Many Requests")
            self.headers = {"Retry-After": "60"}

    async def always_429(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise RateLimited()

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(rag_guardrail._client.aio.models, "generate_content", always_429)

    with pytest.raises(RuntimeError):
        asyncio.run(
            call_gemini_primary(
                image_bytes=b"x",
                mime_type="image/jpeg",
                prompt="test",
                scored_chunks=[("doc_1", "some manual text", 0.9)],
                citation_ids=["doc_1"],
            )
        )

    assert attempts == 1
    assert sleeps == []


def test_retry_wait_is_capped():
    assert rag_guardrail._compute_backoff_delay(0, 60.0) == rag_guardrail.MAX_SINGLE_WAIT_SECONDS
    assert rag_guardrail._compute_backoff_delay(0, 1.0) == 1.0
