import os
from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel

# Load root or local .env automatically using find_dotenv()
load_dotenv(find_dotenv())


class Settings(BaseModel):
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


settings = Settings()
