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
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY") or secrets.token_hex(32)


settings = Settings()
