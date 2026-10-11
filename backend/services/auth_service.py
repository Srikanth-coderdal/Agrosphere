"""
Authentication service: user registration, login, rate limiting, JWT verification, and token revocation.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import time
from typing import Optional, Set
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.user import RevokedToken, User
from schemas.auth import UserCreate

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY: str = settings.JWT_SECRET_KEY
ALGORITHM: str = "HS256"
ALLOWED_ALGORITHMS = ("HS256",)
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 60 minutes

# Login brute-force rate limit settings
RATE_LIMIT_WINDOW_SECONDS: int = 60
MAX_LOGIN_ATTEMPTS_PER_WINDOW: int = 5

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# In-memory cache synced with SQLite RevokedToken store for fast O(1) lookup
_revoked_jtis: Set[str] = set()
_revoked_token_hashes: Set[str] = set()

# Sliding-window login attempt tracker: key -> list of monotonic timestamps
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── Rate limiting helpers ─────────────────────────────────────────────────────
def reset_rate_limiter() -> None:
    """Clear in-memory rate-limit counters (used in test fixtures)."""
    _login_attempts.clear()


def check_login_rate_limit(key: str) -> None:
    """Enforce brute-force defence on login/auth endpoints."""
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    attempts = [ts for ts in _login_attempts[key] if ts > cutoff]
    _login_attempts[key] = attempts
    if len(attempts) >= MAX_LOGIN_ATTEMPTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait 60 seconds before retrying.",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
        )


def record_login_attempt(key: str) -> None:
    """Record a login attempt against the sliding window."""
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    _login_attempts[key] = [ts for ts in _login_attempts[key] if ts > cutoff] + [now]


# ── Password helpers (bcrypt with per-user salt) ──────────────────────────────
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Token Revocation (Denylist Store) ─────────────────────────────────────────
def revoke_token(token: str, db: Optional[Session] = None) -> None:
    """Persistently revoke a JWT in the database denylist and in-memory set."""
    token_hash = _hash_token(token)
    jti = token_hash
    try:
        unverified = jwt.get_unverified_claims(token)
        if isinstance(unverified, dict) and unverified.get("jti"):
            jti = str(unverified["jti"])
    except Exception:
        jti = token_hash

    _revoked_jtis.add(jti)
    _revoked_token_hashes.add(token_hash)

    if db is not None:
        existing = (
            db.query(RevokedToken)
            .filter((RevokedToken.jti == jti) | (RevokedToken.token_hash == token_hash))
            .first()
        )
        if not existing:
            db.add(RevokedToken(jti=jti, token_hash=token_hash))
            db.commit()


def is_token_revoked(token: str, jti: Optional[str] = None, db: Optional[Session] = None) -> bool:
    """Check whether a token or its JTI is present in the revocation denylist."""
    token_hash = _hash_token(token)
    if token_hash in _revoked_token_hashes:
        return True
    if jti and jti in _revoked_jtis:
        return True

    if db is not None:
        query = db.query(RevokedToken).filter(RevokedToken.token_hash == token_hash)
        if jti:
            query = db.query(RevokedToken).filter(
                (RevokedToken.jti == jti) | (RevokedToken.token_hash == token_hash)
            )
        record = query.first()
        if record is not None:
            _revoked_jtis.add(record.jti)
            _revoked_token_hashes.add(record.token_hash)
            return True

    return False


# ── JWT helpers ───────────────────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.setdefault("jti", uuid.uuid4().hex)
    to_encode.setdefault("iat", int(now.timestamp()))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, db: Optional[Session] = None) -> dict:
    if not token or not isinstance(token, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Explicitly inspect header and reject alg=none or any unexpected algorithm
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token header.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    alg = str(header.get("alg", "")).strip()
    if not alg or alg.lower() == "none" or alg not in ALLOWED_ALGORITHMS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Disallowed or insecure JWT algorithm.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=list(ALLOWED_ALGORITHMS),
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if is_token_revoked(token=token, jti=payload.get("jti"), db=db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ── User CRUD ─────────────────────────────────────────────────────────────────
def register_user(db: Session, payload: UserCreate) -> User:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{payload.email}' already exists.",
        )
    user = User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(
    db: Session,
    email: str,
    password: str,
    client_ip: str = "global",
) -> User:
    rate_key_email = f"email:{email.lower().strip()}"
    rate_key_ip = f"ip:{client_ip}"
    check_login_rate_limit(rate_key_email)
    check_login_rate_limit(rate_key_ip)

    user: Optional[User] = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        record_login_attempt(rate_key_email)
        record_login_attempt(rate_key_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(token, db=db)
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    try:
        uid = int(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user ID in token.") from exc

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")
    return user
