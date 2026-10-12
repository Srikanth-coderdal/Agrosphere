import os
import secrets
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel

# Load backend/.env strictly first, then fall back to find_dotenv() if needed
_BACKEND_ENV_PATH = Path(__file__).resolve().parent / ".env"
if _BACKEND_ENV_PATH.exists():
    load_dotenv(dotenv_path=_BACKEND_ENV_PATH)
else:
    load_dotenv(find_dotenv())


class Settings(BaseModel):
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    GEMINI_TIMEOUT_SECONDS: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "9.0"))
    GEMINI_MAX_RETRIES: int = int(os.getenv("GEMINI_MAX_RETRIES", "2"))
    GEMINI_DAILY_QUOTA_LIMIT: int = int(os.getenv("GEMINI_DAILY_QUOTA_LIMIT", "1000"))
    GEMINI_MINUTE_QUOTA_LIMIT: int = int(os.getenv("GEMINI_MINUTE_QUOTA_LIMIT", "60"))
    QUOTA_HIGH_WATER_RATIO: float = float(os.getenv("QUOTA_HIGH_WATER_RATIO", "0.85"))
    USER_DAILY_SCAN_LIMIT: int = int(os.getenv("USER_DAILY_SCAN_LIMIT", "20"))
    MAX_CONCURRENT_HEAVY_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_HEAVY_REQUESTS", "3"))
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3"))
    CIRCUIT_BREAKER_COOLDOWN_SECONDS: float = float(os.getenv("CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60.0"))
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "2048"))
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "5.0"))
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY") or secrets.token_hex(32)


settings = Settings()


