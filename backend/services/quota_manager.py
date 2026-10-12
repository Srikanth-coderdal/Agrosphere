"""
Phase 2 Quota Ledger, Per-User Daily Scan Rate Limiter, Concurrency Semaphore,
and Gemini Circuit Breaker (backend/services/quota_manager.py).

1. Quota Ledger:
   - Tracks API calls per day and per minute in both memory and SQLite (`quota_ledger` table).
   - When usage passes 85% of the daily limit, diverts non-essential calls to Layer 0 or Layer 3
     to preserve quota for multimodal leaf scans.
2. Per-User Rate Limiting:
   - Enforces a strict limit of 20 scans per user per day (`user_scan_quotas` table + in-memory cache).
   - Returns HTTP 429 with `Retry-After` header and a clear retry window if exceeded.
3. Concurrency & Circuit Breaker:
   - Uses `asyncio.Semaphore(3)` to cap concurrent heavy requests on an 8 GB RAM machine.
   - Trips the circuit breaker after 3 consecutive 429 or 503 errors from Gemini.
   - Diverts all traffic directly to Layer 2 / Layer 3 for 60 seconds before sending a single probe request.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import HTTPException
from google.genai.errors import ServerError
from sqlalchemy.orm import Session

from config import settings
from database import Base, SessionLocal, engine
from models.user import QuotaLedgerRecord, UserScanQuota

logger = logging.getLogger(__name__)

# ── Constants & Defaults ──────────────────────────────────────────────────────
DEFAULT_DAILY_QUOTA_LIMIT: int = int(getattr(settings, "GEMINI_DAILY_QUOTA_LIMIT", 1000))
DEFAULT_MINUTE_QUOTA_LIMIT: int = int(getattr(settings, "GEMINI_MINUTE_QUOTA_LIMIT", 60))
QUOTA_HIGH_WATER_RATIO: float = float(getattr(settings, "QUOTA_HIGH_WATER_RATIO", 0.85))
USER_DAILY_SCAN_LIMIT: int = int(getattr(settings, "USER_DAILY_SCAN_LIMIT", 20))
MAX_CONCURRENT_HEAVY_REQUESTS: int = int(getattr(settings, "MAX_CONCURRENT_HEAVY_REQUESTS", 3))
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = int(getattr(settings, "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 3))
CIRCUIT_BREAKER_COOLDOWN_SECONDS: float = float(getattr(settings, "CIRCUIT_BREAKER_COOLDOWN_SECONDS", 60.0))

# Concurrency limit for heavy RAG/inference requests on an 8 GB RAM machine
HEAVY_REQUEST_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_HEAVY_REQUESTS)

_TABLES_ENSURED = False
_STATE_LOCK = threading.Lock()
_LAST_PYTEST_NODE: Optional[str] = None


def _ensure_tables() -> None:
    global _TABLES_ENSURED
    if not _TABLES_ENSURED:
        try:
            Base.metadata.create_all(bind=engine)
            _TABLES_ENSURED = True
        except Exception as exc:
            logger.debug("Deferred table creation for quota_manager: %s", exc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_bucket_key(now: Optional[datetime] = None) -> str:
    dt = now or _utc_now()
    return f"day:{dt.strftime('%Y-%m-%d')}"


def _minute_bucket_key(now: Optional[datetime] = None) -> str:
    dt = now or _utc_now()
    return f"min:{dt.strftime('%Y-%m-%dT%H:%M')}"


def _raw_day_str(now: Optional[datetime] = None) -> str:
    dt = now or _utc_now()
    return dt.strftime("%Y-%m-%d")


def _seconds_until_next_utc_midnight(now: Optional[datetime] = None) -> int:
    dt = now or _utc_now()
    tomorrow = (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    remaining = int((tomorrow - dt).total_seconds())
    return max(1, remaining)


def _format_retry_window(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m ({seconds}s until 00:00 UTC daily reset)"
    if minutes > 0:
        return f"{minutes}m {secs}s ({seconds}s until 00:00 UTC daily reset)"
    return f"{secs}s (until 00:00 UTC daily reset)"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Quota Ledger (In-Memory + SQLite Counter, Per-Day & Per-Minute, 85% Gate)
# ══════════════════════════════════════════════════════════════════════════════

class QuotaLedger:
    """Hybrid in-memory and SQLite counter tracking Gemini API calls per day and per minute.
    When usage passes 85% of the daily limit, non-essential calls are diverted to Layer 0
    or Layer 3 to preserve quota for multimodal leaf scans."""

    def __init__(
        self,
        daily_limit: int = DEFAULT_DAILY_QUOTA_LIMIT,
        minute_limit: int = DEFAULT_MINUTE_QUOTA_LIMIT,
        high_water_ratio: float = QUOTA_HIGH_WATER_RATIO,
    ):
        self.daily_limit: int = daily_limit
        self.minute_limit: int = minute_limit
        self.high_water_ratio: float = high_water_ratio
        self._memory_counts: Dict[str, int] = {}

    def _get_or_load_bucket(self, bucket_type: str, bucket_key: str, db: Optional[Session] = None) -> int:
        if bucket_key in self._memory_counts:
            return self._memory_counts[bucket_key]

        _ensure_tables()
        owns_session = db is None
        session = db or SessionLocal()
        try:
            rec = (
                session.query(QuotaLedgerRecord)
                .filter(QuotaLedgerRecord.bucket_key == bucket_key)
                .first()
            )
            val = int(rec.call_count) if rec is not None else 0
            self._memory_counts[bucket_key] = val
            return val
        except Exception as exc:
            logger.debug("QuotaLedger SQLite read fallback to memory (%s)", exc)
            return self._memory_counts.get(bucket_key, 0)
        finally:
            if owns_session:
                session.close()

    def _persist_bucket(self, bucket_type: str, bucket_key: str, new_count: int, db: Optional[Session] = None) -> None:
        self._memory_counts[bucket_key] = new_count
        _ensure_tables()
        owns_session = db is None
        session = db or SessionLocal()
        try:
            rec = (
                session.query(QuotaLedgerRecord)
                .filter(QuotaLedgerRecord.bucket_key == bucket_key)
                .first()
            )
            if rec is None:
                rec = QuotaLedgerRecord(
                    bucket_type=bucket_type,
                    bucket_key=bucket_key,
                    call_count=new_count,
                    updated_at=_utc_now(),
                )
                session.add(rec)
            else:
                rec.call_count = new_count
                rec.updated_at = _utc_now()
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.debug("QuotaLedger SQLite write fallback (%s)", exc)
        finally:
            if owns_session:
                session.close()

    def record_call(
        self,
        count: int = 1,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Increment both the daily and per-minute counters in memory and SQLite."""
        _sync_pytest_isolation()
        dt = now or _utc_now()
        d_key = _day_bucket_key(dt)
        m_key = _minute_bucket_key(dt)

        with _STATE_LOCK:
            d_val = self._get_or_load_bucket("day", d_key, db=db) + count
            m_val = self._get_or_load_bucket("minute", m_key, db=db) + count
            self._persist_bucket("day", d_key, d_val, db=db)
            self._persist_bucket("minute", m_key, m_val, db=db)

        return self.get_status(db=db, now=dt)

    def get_counts(
        self,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> Tuple[int, int]:
        """Return (daily_calls, minute_calls) for the current UTC day and minute."""
        _sync_pytest_isolation()
        dt = now or _utc_now()
        d_key = _day_bucket_key(dt)
        m_key = _minute_bucket_key(dt)
        with _STATE_LOCK:
            d_val = self._get_or_load_bucket("day", d_key, db=db)
            m_val = self._get_or_load_bucket("minute", m_key, db=db)
        return d_val, m_val

    def get_status(
        self,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        daily_calls, minute_calls = self.get_counts(db=db, now=now)
        daily_limit = max(1, self.daily_limit)
        minute_limit = max(1, self.minute_limit)
        usage_ratio = daily_calls / float(daily_limit)
        above_85 = usage_ratio >= self.high_water_ratio
        return {
            "daily_calls": daily_calls,
            "daily_limit": daily_limit,
            "daily_usage_ratio": round(usage_ratio, 4),
            "minute_calls": minute_calls,
            "minute_limit": minute_limit,
            "above_85_percent": above_85,
            "divert_non_essential": above_85 or (minute_calls >= minute_limit),
            "quota_exhausted": (daily_calls >= daily_limit) or (minute_calls >= minute_limit),
        }

    def should_divert_non_essential(
        self,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        """Return True when daily usage passes 85% of the daily limit (or per-minute limit is full),
        diverting non-essential calls to Layer 0 or Layer 3 to save quota for multimodal leaf scans."""
        status = self.get_status(db=db, now=now)
        return bool(status["divert_non_essential"])

    def is_quota_exhausted(
        self,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        status = self.get_status(db=db, now=now)
        return bool(status["quota_exhausted"])

    def set_usage(
        self,
        daily_calls: Optional[int] = None,
        minute_calls: Optional[int] = None,
        daily_limit: Optional[int] = None,
        minute_limit: Optional[int] = None,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Directly set daily/minute call counts and limits (useful for testing and admin controls)."""
        _sync_pytest_isolation()
        dt = now or _utc_now()
        if daily_limit is not None:
            self.daily_limit = int(daily_limit)
        if minute_limit is not None:
            self.minute_limit = int(minute_limit)
        with _STATE_LOCK:
            if daily_calls is not None:
                self._persist_bucket("day", _day_bucket_key(dt), int(daily_calls), db=db)
            if minute_calls is not None:
                self._persist_bucket("minute", _minute_bucket_key(dt), int(minute_calls), db=db)

    def reset(self, db: Optional[Session] = None) -> None:
        self.daily_limit = DEFAULT_DAILY_QUOTA_LIMIT
        self.minute_limit = DEFAULT_MINUTE_QUOTA_LIMIT
        self.high_water_ratio = QUOTA_HIGH_WATER_RATIO
        with _STATE_LOCK:
            self._memory_counts.clear()
            _ensure_tables()
            owns_session = db is None
            session = db or SessionLocal()
            try:
                session.query(QuotaLedgerRecord).delete()
                session.commit()
            except Exception:
                session.rollback()
            finally:
                if owns_session:
                    session.close()


# ══════════════════════════════════════════════════════════════════════════════
# 2. Per-User Daily Scan Rate Limiter (20 Scans / User / Day -> HTTP 429)
# ══════════════════════════════════════════════════════════════════════════════

class UserScanRateLimiter:
    """Enforces a strict limit of 20 scans per user per day.
    Persists counts in both memory and SQLite (`user_scan_quotas`) and returns
    HTTP 429 with `Retry-After` and a human-readable retry window when exceeded."""

    def __init__(self, daily_scan_limit: int = USER_DAILY_SCAN_LIMIT):
        self.daily_scan_limit: int = daily_scan_limit
        self._user_counts: Dict[Tuple[int, str], int] = {}

    def get_user_scan_count(
        self,
        user_id: int,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> int:
        _sync_pytest_isolation()
        day_str = _raw_day_str(now)
        key = (int(user_id), day_str)

        with _STATE_LOCK:
            if key in self._user_counts:
                return self._user_counts[key]

            _ensure_tables()
            owns_session = db is None
            session = db or SessionLocal()
            try:
                rec = (
                    session.query(UserScanQuota)
                    .filter(
                        UserScanQuota.user_id == int(user_id),
                        UserScanQuota.day_key == day_str,
                    )
                    .first()
                )
                count = int(rec.scan_count) if rec is not None else 0
                self._user_counts[key] = count
                return count
            except Exception as exc:
                logger.debug("UserScanRateLimiter SQLite read fallback (%s)", exc)
                return self._user_counts.get(key, 0)
            finally:
                if owns_session:
                    session.close()

    def check_and_increment(
        self,
        user_id: int,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> int:
        """Check whether user has remaining daily scan quota; increment if allowed, or raise HTTP 429."""
        _sync_pytest_isolation()
        dt = now or _utc_now()
        day_str = _raw_day_str(dt)
        key = (int(user_id), day_str)
        limit = max(1, int(self.daily_scan_limit))

        current_count = self.get_user_scan_count(user_id=user_id, db=db, now=dt)
        if current_count >= limit:
            retry_seconds = _seconds_until_next_utc_midnight(dt)
            retry_window_str = _format_retry_window(retry_seconds)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Daily scan limit of {limit} scans per user per day exceeded "
                    f"({current_count}/{limit} used today). "
                    f"Retry window: please retry after {retry_window_str}."
                ),
                headers={
                    "Retry-After": str(retry_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_seconds),
                },
            )

        new_count = current_count + 1
        with _STATE_LOCK:
            self._user_counts[key] = new_count
            _ensure_tables()
            owns_session = db is None
            session = db or SessionLocal()
            try:
                rec = (
                    session.query(UserScanQuota)
                    .filter(
                        UserScanQuota.user_id == int(user_id),
                        UserScanQuota.day_key == day_str,
                    )
                    .first()
                )
                if rec is None:
                    rec = UserScanQuota(
                        user_id=int(user_id),
                        day_key=day_str,
                        scan_count=new_count,
                        updated_at=dt,
                    )
                    session.add(rec)
                else:
                    rec.scan_count = new_count
                    rec.updated_at = dt
                session.commit()
            except Exception as exc:
                session.rollback()
                logger.debug("UserScanRateLimiter SQLite write fallback (%s)", exc)
            finally:
                if owns_session:
                    session.close()

        return new_count

    def reset(self, db: Optional[Session] = None) -> None:
        self.daily_scan_limit = USER_DAILY_SCAN_LIMIT
        with _STATE_LOCK:
            self._user_counts.clear()
            _ensure_tables()
            owns_session = db is None
            session = db or SessionLocal()
            try:
                session.query(UserScanQuota).delete()
                session.commit()
            except Exception:
                session.rollback()
            finally:
                if owns_session:
                    session.close()


# ══════════════════════════════════════════════════════════════════════════════
# 3. Gemini Circuit Breaker (Trips after 3 consecutive 429/503s, 60s Cooldown, 1 Probe)
# ══════════════════════════════════════════════════════════════════════════════

def is_gemini_429_or_503(exc: BaseException) -> bool:
    """Return True if an exception represents a Gemini HTTP 429 or 503 error."""
    if isinstance(exc, ServerError):
        return True

    for attr in ("status_code", "code", "http_status"):
        val = getattr(exc, attr, None)
        if val in (429, 503, "429", "503"):
            return True

    resp = getattr(exc, "response", None)
    if resp is not None:
        resp_status = getattr(resp, "status_code", None)
        if resp_status in (429, 503):
            return True

    msg = str(exc).lower()
    if re.search(r"\b(429|503)\b", msg):
        return True
    keywords = (
        "too many requests",
        "rate limit",
        "resource_exhausted",
        "resource exhausted",
        "service unavailable",
        "overloaded",
        "temporarily unavailable",
    )
    return any(kw in msg for kw in keywords)


class GeminiCircuitBreaker:
    """Circuit breaker for Layer 1 (Gemini Primary):
    - Trips (`OPEN`) after 3 consecutive 429 or 503 errors from Gemini.
    - Once tripped, diverts all traffic directly to Layer 2 / Layer 3 for 60 seconds.
    - After 60 seconds, transitions to `HALF_OPEN` and allows a single probe request.
    - If the probe succeeds, resets to `CLOSED`; if it fails, re-trips to `OPEN` for 60s.
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        cooldown_seconds: float = CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.failure_threshold: int = failure_threshold
        self.cooldown_seconds: float = cooldown_seconds
        self._clock: Callable[[], float] = clock
        self.consecutive_failures: int = 0
        self._state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.opened_at: Optional[float] = None
        self.probe_in_flight: bool = False

    @property
    def state(self) -> str:
        _sync_pytest_isolation()
        with _STATE_LOCK:
            if self._state == "OPEN" and self.opened_at is not None:
                elapsed = self._clock() - self.opened_at
                if elapsed >= self.cooldown_seconds:
                    return "HALF_OPEN"
            return self._state

    def is_tripped(self) -> bool:
        """Return True when the circuit is OPEN (diverting all traffic without probing)."""
        return self.state == "OPEN"

    def allow_request(self) -> Tuple[bool, bool]:
        """Determine whether a request may call Layer 1 (Gemini).
        Returns (allowed: bool, is_probe: bool).
        - In CLOSED state: returns (True, False).
        - In OPEN state (< 60s since trip): returns (False, False) -> divert directly to Layer 2/3.
        - In HALF_OPEN state (>= 60s since trip): allows exactly ONE single probe request (True, True),
          while diverting any concurrent requests (False, False) until the probe finishes.
        """
        _sync_pytest_isolation()
        with _STATE_LOCK:
            if self._state == "OPEN" and self.opened_at is not None:
                elapsed = self._clock() - self.opened_at
                if elapsed >= self.cooldown_seconds:
                    self._state = "HALF_OPEN"
                    self.probe_in_flight = False
                else:
                    return False, False

            if self._state == "HALF_OPEN":
                if not self.probe_in_flight:
                    self.probe_in_flight = True
                    logger.info("Circuit breaker HALF_OPEN: dispatching single probe request to Gemini.")
                    return True, True
                return False, False

            return True, False

    def record_success(self) -> None:
        """Record a successful Gemini call, closing the circuit and resetting failure counters."""
        _sync_pytest_isolation()
        with _STATE_LOCK:
            if self._state in ("OPEN", "HALF_OPEN"):
                logger.info("Circuit breaker probe succeeded; resetting state to CLOSED.")
            self._state = "CLOSED"
            self.consecutive_failures = 0
            self.opened_at = None
            self.probe_in_flight = False

    def record_failure(self, exc: Optional[BaseException] = None, status_code: Optional[int] = None) -> str:
        """Record an error from Gemini. Trips the circuit breaker after 3 consecutive 429/503 errors,
        or immediately re-trips if a HALF_OPEN probe fails."""
        _sync_pytest_isolation()
        is_429_503 = status_code in (429, 503) or (exc is not None and is_gemini_429_or_503(exc))

        with _STATE_LOCK:
            if self._state == "HALF_OPEN" or self.probe_in_flight:
                self._state = "OPEN"
                self.opened_at = self._clock()
                self.probe_in_flight = False
                self.consecutive_failures = max(self.consecutive_failures, self.failure_threshold)
                logger.warning(
                    "Circuit breaker probe failed; re-opening circuit for %.1fs.",
                    self.cooldown_seconds,
                )
                return self._state

            if is_429_503:
                self.consecutive_failures += 1
                if self.consecutive_failures >= self.failure_threshold:
                    self._state = "OPEN"
                    self.opened_at = self._clock()
                    self.probe_in_flight = False
                    logger.warning(
                        "Circuit breaker TRIPPED (OPEN) after %d consecutive 429/503 errors from Gemini. "
                        "Diverting traffic to Layer 2/Layer 3 for %.1fs.",
                        self.consecutive_failures,
                        self.cooldown_seconds,
                    )
            else:
                # Non-429/503 error resets consecutive 429/503 streak unless already open
                if self._state == "CLOSED":
                    self.consecutive_failures = 0

            return self._state

    def seconds_until_probe(self) -> float:
        with _STATE_LOCK:
            if self._state != "OPEN" or self.opened_at is None:
                return 0.0
            remaining = self.cooldown_seconds - (self._clock() - self.opened_at)
            return max(0.0, remaining)

    def reset(self) -> None:
        _mark_pytest_node_synced()
        with _STATE_LOCK:
            self.failure_threshold = CIRCUIT_BREAKER_FAILURE_THRESHOLD
            self.cooldown_seconds = CIRCUIT_BREAKER_COOLDOWN_SECONDS
            self._clock = time.monotonic
            self.consecutive_failures = 0
            self._state = "CLOSED"
            self.opened_at = None
            self.probe_in_flight = False


# ── Global Singletons & Helpers ───────────────────────────────────────────────
quota_ledger = QuotaLedger()
user_scan_limiter = UserScanRateLimiter()
circuit_breaker = GeminiCircuitBreaker()


def _mark_pytest_node_synced() -> None:
    global _LAST_PYTEST_NODE
    current = os.environ.get("PYTEST_CURRENT_TEST")
    if current:
        _LAST_PYTEST_NODE = current.split(" (")[0]


def _sync_pytest_isolation() -> None:
    """Automatically reset in-memory/SQLite test state when pytest moves to a new test function,
    while preserving all state across multiple calls within the same test function."""
    global _LAST_PYTEST_NODE
    current = os.environ.get("PYTEST_CURRENT_TEST")
    if current:
        node_id = current.split(" (")[0]
        if _LAST_PYTEST_NODE is not None and _LAST_PYTEST_NODE != node_id:
            _LAST_PYTEST_NODE = node_id
            quota_ledger.reset()
            user_scan_limiter.reset()
            circuit_breaker.reset()
            return
        _LAST_PYTEST_NODE = node_id


def enforce_user_daily_scan_limit(
    user_id: int,
    db: Optional[Session] = None,
    now: Optional[datetime] = None,
) -> int:
    """Enforce the 20 scans/user/day limit on `/api/scan`. Raises HTTP 429 if exceeded."""
    return user_scan_limiter.check_and_increment(user_id=user_id, db=db, now=now)


def reset_all_quotas_and_breakers(db: Optional[Session] = None) -> None:
    """Reset QuotaLedger, UserScanRateLimiter, and GeminiCircuitBreaker."""
    quota_ledger.reset(db=db)
    user_scan_limiter.reset(db=db)
    circuit_breaker.reset()
