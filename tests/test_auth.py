"""
Phase 5 Authentication & Authorization Verification Suite (tests/test_auth.py).

Covers:
1. Password hashing with per-user salt (bcrypt) & wrong password rejection (401)
2. JWT secret length/env loading, fixed algorithm (HS256), and explicit alg=none rejection (401)
3. Tampered token rejection (401)
4. Expired token rejection (401)
5. Replayed token after logout rejected via persistent RevokedToken denylist store (401)
6. Missing token rejected on every non-public route (/api/scan, /api/irrigation/calculate,
   /api/v1/yield-estimator/predict, /api/v1/urban-gardening/advise, /api/v1/auth/me,
   /api/v1/auth/users/{id}, /api/weather, /api/v1/auth/logout) (401)
7. Cross-user access blocked (User A requesting User B's profile -> 403 Forbidden)
8. Brute-force login rate limiting (429 Too Many Requests)
"""
import base64
from datetime import timedelta
import json
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

# Add backend directory to sys.path so imports match backend runtime
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
from models.user import RevokedToken, User  # noqa: E402
from services.auth_service import (  # noqa: E402
    ALGORITHM,
    ALLOWED_ALGORITHMS,
    MAX_LOGIN_ATTEMPTS_PER_WINDOW,
    SECRET_KEY,
    create_access_token,
    hash_password,
    reset_rate_limiter,
    verify_password,
)


@pytest.fixture(autouse=True)
def setup_test_state():
    """Ensure DB tables exist and rate-limit state is clean before each test."""
    Base.metadata.create_all(bind=engine)
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _create_unique_user(client: TestClient, prefix: str = "farmer") -> dict:
    email = f"{prefix}_{uuid.uuid4().hex[:10]}@agrosphere.org"
    password = "StrongPassword!2026"
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": f"Test {prefix.capitalize()}",
            "email": email,
            "password": password,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {"id": data["id"], "email": email, "password": password, "full_name": data["full_name"]}


def _login_user(client: TestClient, email: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ── 1. Password Storage (bcrypt per-user salt) & Wrong Password ──────────────
def test_bcrypt_per_user_salt_and_wrong_password(client: TestClient):
    user = _create_unique_user(client, "saltcheck")

    # Verify two hashes of the identical password produce distinct salted bcrypt hashes
    hash_1 = hash_password(user["password"])
    hash_2 = hash_password(user["password"])
    assert hash_1 != hash_2
    assert hash_1.startswith("$2b$") or hash_1.startswith("$2a$")
    assert verify_password(user["password"], hash_1)
    assert not verify_password("WrongPassword!999", hash_1)

    # Verify wrong password via /api/v1/auth/login returns 401
    bad_resp = client.post(
        "/api/v1/auth/login",
        data={"username": user["email"], "password": "WrongPassword!999"},
    )
    assert bad_resp.status_code == 401
    assert "incorrect" in bad_resp.json()["detail"].lower()


# ── 2. JWT Secret Strength, Fixed Algorithm, and Explicit alg=none Rejection ─
def test_jwt_secret_and_alg_none_rejected(client: TestClient):
    user = _create_unique_user(client, "algnone")

    # Secret must not be the old hardcoded placeholder and must be >= 32 characters
    assert SECRET_KEY != "agrosphere-secret-key-change-in-production"
    assert len(SECRET_KEY) >= 32
    assert ALGORITHM == "HS256"
    assert ALLOWED_ALGORITHMS == ("HS256",)

    # Forge an alg=none token for the valid user
    for alg_value in ("none", "None", "NONE", "HS384"):
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps({"alg": alg_value, "typ": "JWT"}).encode())
            .decode()
            .rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(
                json.dumps({"sub": str(user["id"]), "exp": 9999999999}).encode()
            )
            .decode()
            .rstrip("=")
        )
        forged_token = f"{header_b64}.{payload_b64}."
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {forged_token}"},
        )
        assert resp.status_code == 401, f"Token with alg={alg_value} was not rejected!"


# ── 3. Tampered Token Rejection ──────────────────────────────────────────────
def test_tampered_token_rejected(client: TestClient):
    user_a = _create_unique_user(client, "tamper_a")
    user_b = _create_unique_user(client, "tamper_b")
    valid_token = _login_user(client, user_a["email"], user_a["password"])

    parts = valid_token.split(".")
    assert len(parts) == 3

    # Tamper 1: Alter the payload to impersonate user_b while keeping user_a's signature
    forged_payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": str(user_b["id"]), "exp": 9999999999}).encode()
        )
        .decode()
        .rstrip("=")
    )
    tampered_payload_token = f"{parts[0]}.{forged_payload}.{parts[2]}"
    resp1 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered_payload_token}"},
    )
    assert resp1.status_code == 401

    # Tamper 2: Flip characters in the signature
    bad_sig = parts[2][:-4] + ("aaaa" if parts[2][-4:] != "aaaa" else "bbbb")
    tampered_sig_token = f"{parts[0]}.{parts[1]}.{bad_sig}"
    resp2 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered_sig_token}"},
    )
    assert resp2.status_code == 401


# ── 4. Expired Token Rejection ───────────────────────────────────────────────
def test_expired_token_rejected(client: TestClient):
    user = _create_unique_user(client, "expired")
    expired_token = create_access_token(
        data={"sub": str(user["id"])},
        expires_delta=timedelta(minutes=-5),
    )
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401


# ── 5. Replayed Token After Logout (Persistent Denylist Verification) ────────
def test_replayed_token_after_logout_rejected(client: TestClient):
    user = _create_unique_user(client, "logout_replay")
    token = _login_user(client, user["email"], user["password"])

    # Token works before logout
    pre_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pre_resp.status_code == 200

    # Logout revokes the token in the persistent RevokedToken denylist table
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 200

    # Verify token revocation is persisted in the SQLite database table (not just cookie deletion)
    db = SessionLocal()
    try:
        assert db.query(RevokedToken).count() >= 1
    finally:
        db.close()

    # Replaying the logged-out token via Authorization header MUST return 401
    replay_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay_me.status_code == 401

    replay_urban = client.post(
        "/api/v1/urban-gardening/advise",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "plant_type": "Tomato",
            "space_type": "balcony",
            "sunlight_hours": 6,
            "container_size": 15,
        },
    )
    assert replay_urban.status_code == 401


# ── 6. Missing Token Rejected on Every Non-Public Route ──────────────────────
@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("GET", "/api/v1/auth/me", {}),
        ("GET", "/api/v1/auth/users/1", {}),
        ("POST", "/api/v1/auth/logout", {}),
        (
            "POST",
            "/api/scan",
            {
                "files": {"image": ("leaf.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg")},
                "data": {"crop_type": "Tomato"},
            },
        ),
        (
            "POST",
            "/api/irrigation/calculate",
            {
                "json": {
                    "crop_type": "Tomato",
                    "growth_stage": "Initial",
                    "soil_type": "Loam",
                    "field_size_hectares": 1.0,
                    "soil_moisture_percentage": 40,
                    "temperature_celsius": 28,
                    "rainfall_probability_percent": 10,
                }
            },
        ),
        (
            "POST",
            "/api/v1/yield-estimator/predict",
            {
                "json": {
                    "crop_type": "Tomato",
                    "field_size_hectares": 1.0,
                    "soil_type": "loam",
                    "historical_yield_tons": 10.0,
                    "irrigation_type": "drip",
                    "weather_condition": "optimal",
                }
            },
        ),
        (
            "POST",
            "/api/v1/urban-gardening/advise",
            {
                "json": {
                    "plant_type": "Tomato",
                    "space_type": "balcony",
                    "sunlight_hours": 6,
                    "container_size": 15,
                }
            },
        ),
        ("GET", "/api/weather?latitude=13.08&longitude=80.27", {}),
        ("GET", "/api/scan/uploads", {}),
        ("DELETE", "/api/scan/uploads", {}),
        ("DELETE", "/api/scan/uploads/00000000-0000-0000-0000-000000000000", {}),
    ],
)
def test_missing_token_rejected_on_every_non_public_route(
    client: TestClient, method: str, path: str, kwargs: dict
):
    # Ensure no cookies or Authorization headers are sent
    client.cookies.clear()
    response = client.request(method, path, **kwargs)
    assert response.status_code == 401, (
        f"Expected 401 on {method} {path} without token, got {response.status_code}: {response.text}"
    )


# ── 7. Cross-User Access Control (IDOR Prevention) ───────────────────────────
def test_cross_user_access_forbidden(client: TestClient):
    user_a = _create_unique_user(client, "user_a")
    user_b = _create_unique_user(client, "user_b")
    token_a = _login_user(client, user_a["email"], user_a["password"])

    # User A can read their own profile
    own_resp = client.get(
        f"/api/v1/auth/users/{user_a['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert own_resp.status_code == 200
    assert own_resp.json()["email"] == user_a["email"]

    # User A attempting to read User B's profile is rejected with 403 Forbidden
    cross_resp = client.get(
        f"/api/v1/auth/users/{user_b['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert cross_resp.status_code == 403


# ── 8. Brute-Force Login Rate Limiting ───────────────────────────────────────
def test_login_rate_limiting_blocks_brute_force(client: TestClient):
    user = _create_unique_user(client, "ratelimit")

    # Exhaust allowed failed login attempts
    for _ in range(MAX_LOGIN_ATTEMPTS_PER_WINDOW):
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": user["email"], "password": "WrongPassword!123"},
        )
        assert resp.status_code == 401

    # Subsequent login attempts within the window must be blocked with 429 Too Many Requests
    blocked_resp = client.post(
        "/api/v1/auth/login",
        data={"username": user["email"], "password": user["password"]},
    )
    assert blocked_resp.status_code == 429
    assert "Retry-After" in blocked_resp.headers


# ── 9. Phase 6.1: Secrets Hygiene (.gitignore & No NEXT_PUBLIC_ Secrets) ─────
def test_phase_6_1_secrets_hygiene():
    gitignore_text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    gitignore_lines = [line.strip() for line in gitignore_text.splitlines()]
    assert ".env" in gitignore_lines, ".env must be listed in root .gitignore"

    # Ensure no frontend file or .env.example exposes backend secrets with NEXT_PUBLIC_
    forbidden_prefixes = ("NEXT_PUBLIC_GEMINI", "NEXT_PUBLIC_JWT", "NEXT_PUBLIC_SECRET")
    for env_file in (
        REPO_ROOT / ".env.example",
        REPO_ROOT / "frontend" / ".env.example",
        BACKEND_DIR / ".env",
    ):
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            for forbidden in forbidden_prefixes:
                assert forbidden not in content, f"Found {forbidden} in {env_file}"


# ── 10. Phase 6.2: Maximum Upload Size Enforcement (5 MB -> 413) ─────────────
def test_upload_max_file_size_enforced(client: TestClient):
    from services.upload_security import MAX_UPLOAD_SIZE_BYTES

    user = _create_unique_user(client, "upload_size")
    token = _login_user(client, user["email"], user["password"])

    oversized_payload = b"\xff\xd8\xff\xe0" + (b"A" * (MAX_UPLOAD_SIZE_BYTES + 1024))
    resp = client.post(
        "/api/scan",
        headers={"Authorization": f"Bearer {token}"},
        files={"image": ("huge_leaf.jpg", oversized_payload, "image/jpeg")},
        data={"crop_type": "Tomato"},
    )
    assert resp.status_code == 413, resp.text


# ── 11. Phase 6.2: Magic Bytes Verification via Pillow Decode (400) ──────────
def test_upload_magic_bytes_rejects_spoofed_files(client: TestClient):
    user = _create_unique_user(client, "upload_magic")
    token = _login_user(client, user["email"], user["password"])

    # Spoofed file: .jpg extension + image/jpeg MIME header, but HTML/script payload bytes
    spoofed_bytes = b"<html><script>alert('xss')</script>not a real image</html>"
    resp = client.post(
        "/api/scan",
        headers={"Authorization": f"Bearer {token}"},
        files={"image": ("evil_payload.jpg", spoofed_bytes, "image/jpeg")},
        data={"crop_type": "Tomato"},
    )
    assert resp.status_code == 400, resp.text
    assert "magic-byte verification failed" in resp.json()["detail"].lower()


# ── 12. Phase 6.2: Server-Side Re-Encoding & EXIF Metadata Stripping ─────────
def test_upload_reencodes_and_strips_exif_metadata():
    import io
    from PIL import Image
    from services.upload_security import validate_and_sanitize_image

    # Build a valid RGB image containing embedded EXIF metadata (e.g., Make/Model/Software/GPS)
    img = Image.new("RGB", (64, 64), color=(34, 139, 34))
    exif = img.getexif()
    exif[0x010F] = "CameraMaker"       # Make
    exif[0x0110] = "AgroPhonePro"      # Model
    exif[0x0131] = "MaliciousPayload"  # Software

    raw_buf = io.BytesIO()
    img.save(raw_buf, format="JPEG", exif=exif.tobytes())
    raw_bytes_with_exif = raw_buf.getvalue()

    # Confirm EXIF is present before sanitization
    pre_check = Image.open(io.BytesIO(raw_bytes_with_exif))
    assert len(pre_check.getexif()) > 0

    # Run server-side validation + re-encoding
    sanitized_bytes, sanitized_mime = validate_and_sanitize_image(raw_bytes_with_exif)
    assert sanitized_mime == "image/jpeg"
    assert sanitized_bytes != raw_bytes_with_exif

    # Confirm re-encoded image is valid JPEG and all EXIF tags have been stripped
    post_check = Image.open(io.BytesIO(sanitized_bytes))
    assert post_check.format == "JPEG"
    assert post_check.size == (64, 64)
    assert len(post_check.getexif()) == 0


# ── 13. Phase 6.2: Zero Default Retention, Opt-In UUID Storage & Deletion ────
def test_upload_consent_retention_and_deletion(client: TestClient, monkeypatch):
    import io
    from PIL import Image
    import main as main_module
    from schemas.diagnostic import SafeDosage, VerifiedDiagnosticResponse
    from services.upload_security import CONSENTED_UPLOADS_DIR

    async def _mock_apply_guardrail(
        image_bytes: bytes,
        mime_type: str,
        crop_type: str,
        language: str = "en",
        farmer_comment=None,
        operational_context=None,
        weather_summary=None,
    ) -> VerifiedDiagnosticResponse:
        # Verify the bytes passed to the AI pipeline are already sanitized JPEG bytes
        assert mime_type == "image/jpeg"
        checked = Image.open(io.BytesIO(image_bytes))
        assert checked.format == "JPEG"
        assert len(checked.getexif()) == 0
        return VerifiedDiagnosticResponse(
            pathogen="Alternaria solani (Early Blight)",
            confidence=0.93,
            verified_treatment="Spray Mancozeb 2 g/litre of water.",
            safe_dosages=[
                SafeDosage(
                    chemical_name="Mancozeb",
                    dosage="2",
                    unit="g/litre",
                    max_frequency="Twice at 15-day interval",
                    pre_harvest_interval_days=7,
                )
            ],
            organic_recommendations=["Neem cake application"],
            preventive_measures=["Crop rotation"],
            disclaimer="Verified against TNAU Horticultural Manual.",
            is_verified=True,
        )

    monkeypatch.setattr(main_module, "apply_guardrail", _mock_apply_guardrail)

    user_a = _create_unique_user(client, "consent_a")
    user_b = _create_unique_user(client, "consent_b")
    token_a = _login_user(client, user_a["email"], user_a["password"])
    token_b = _login_user(client, user_b["email"], user_b["password"])

    # Create a valid PNG image with a user-supplied filename containing path/PII characters
    img = Image.new("RGB", (48, 48), color=(20, 160, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    valid_png_bytes = buf.getvalue()

    # Case A: Default scan (consent_to_store omitted / False) -> NOT retained on disk
    resp_default = client.post(
        "/api/scan",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"image": ("../../farmer_private_photo.png", valid_png_bytes, "image/png")},
        data={"crop_type": "Tomato"},
    )
    assert resp_default.status_code == 200, resp_default.text
    assert resp_default.json()["stored_upload_id"] is None

    list_after_default = client.get(
        "/api/scan/uploads",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_after_default.status_code == 200
    assert list_after_default.json()["uploads"] == []

    # Case B: Explicit consent (consent_to_store=True) -> Saved with UUID filename as sanitized .jpg
    resp_consented = client.post(
        "/api/scan",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"image": ("../../farmer_private_photo.png", valid_png_bytes, "image/png")},
        data={"crop_type": "Tomato", "consent_to_store": "true"},
    )
    assert resp_consented.status_code == 200, resp_consented.text
    upload_id = resp_consented.json()["stored_upload_id"]
    assert upload_id is not None
    # Verify upload_id is a valid UUID4 hex and file on disk uses generated <uuid4_hex>.jpg name
    parsed_uuid = uuid.UUID(upload_id, version=4)
    assert parsed_uuid.hex == upload_id
    stored_path = CONSENTED_UPLOADS_DIR / f"{upload_id}.jpg"
    assert stored_path.is_file()

    # Case C: User B cannot delete User A's stored upload (403 Forbidden)
    cross_del = client.delete(
        f"/api/scan/uploads/{upload_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_del.status_code == 403
    assert stored_path.is_file()

    # Case D: User A deletes their stored upload on request -> removed from disk & DB
    own_del = client.delete(
        f"/api/scan/uploads/{upload_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert own_del.status_code == 200, own_del.text
    assert not stored_path.exists()

    list_after_delete = client.get(
        "/api/scan/uploads",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_after_delete.status_code == 200
    assert list_after_delete.json()["uploads"] == []

