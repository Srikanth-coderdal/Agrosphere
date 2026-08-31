from contextlib import asynccontextmanager
from typing import Optional
import httpx

from dotenv import load_dotenv, find_dotenv

# Automatically locate and load root or local .env
load_dotenv(find_dotenv())

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Base, engine
from models import user as _user_model  # noqa: F401 — registers User table with Base
from routers import auth, irrigation, urban_gardening, yield_estimator
from schemas.diagnostic import VerifiedDiagnosticResponse, WeatherSummary
from services.rag_guardrail import apply_guardrail

# ── DB table auto-creation on startup ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Agrosphere Backend API",
    description="AI-powered agricultural assistant — Disease Scan, Irrigation, Yield, Urban Gardening & Auth.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(irrigation.router,       prefix="/api/irrigation",                tags=["Irrigation"])
app.include_router(urban_gardening.router,  prefix="/api/v1/urban-gardening",        tags=["Urban Gardening"])
app.include_router(yield_estimator.router,  prefix="/api/v1/yield-estimator",        tags=["Yield Estimator"])
app.include_router(auth.router,             prefix="/api/v1/auth",                   tags=["Authentication"])

# ── Allowed image types ───────────────────────────────────────────────────────
_ALLOWED_EXTENSIONS   = {".jpg", ".jpeg", ".png", ".webp"}
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

_MIME_MAP = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
}


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "gemini_api_key_configured": bool(settings.GEMINI_API_KEY),
    }


# ── Crop Disease Scanner ──────────────────────────────────────────────────────
@app.post("/api/scan", response_model=VerifiedDiagnosticResponse, tags=["Disease Scanner"])
async def scan_crop(
    image: UploadFile = File(..., description="Crop leaf image (.jpg, .jpeg, .png, .webp)"),
    crop_type: str = Form(..., description="Type of crop being analyzed"),
    latitude: Optional[float] = Form(None, description="GPS Latitude"),
    longitude: Optional[float] = Form(None, description="GPS Longitude"),
    language: str = Form("en", description="Response language code (e.g. 'en' or 'ta')."),
    farmer_comment: Optional[str] = Form(None, description="Optional farmer observation text"),
    operational_context: Optional[str] = Form(None, description="Operational context mode (Commercial vs Urban)"),
    context_mode: Optional[str] = Form(None, description="Operational context mode alias"),
):
    content_type = (image.content_type or "").lower()
    filename = image.filename or ""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    if content_type not in _ALLOWED_CONTENT_TYPES and ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{content_type or ext}'. Allowed: jpg, jpeg, png, webp.",
        )

    mime_type = content_type if content_type in _ALLOWED_CONTENT_TYPES else _MIME_MAP.get(ext, "image/jpeg")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    op_context = operational_context or context_mode

    weather_summary: Optional[WeatherSummary] = None
    if latitude is not None and longitude is not None:
        try:
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_params = {
                "latitude": latitude,
                "longitude": longitude,
                "daily": "precipitation_sum,temperature_2m_max",
                "current": "temperature_2m",
                "forecast_days": 3,
                "timezone": "auto",
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                w_resp = await client.get(weather_url, params=weather_params)
                if w_resp.status_code == 200:
                    w_data = w_resp.json()
                    curr_temp = w_data.get("current", {}).get("temperature_2m")
                    if curr_temp is None:
                        daily_temps = w_data.get("daily", {}).get("temperature_2m_max", [])
                        curr_temp = daily_temps[0] if daily_temps else 25.0

                    precip_list = w_data.get("daily", {}).get("precipitation_sum", [])
                    precip_24h = float(precip_list[0]) if precip_list else 0.0

                    if precip_24h > 2.0:
                        spray_adv = f"⚠️ Rain forecast in next 24h ({precip_24h:.1f}mm). Postpone chemical/organic foliar spraying to prevent wash-off."
                        rain_label = f"High ({precip_24h:.1f}mm)"
                    else:
                        spray_adv = f"Optimal weather for foliar spraying and treatments. Minimal rain risk in next 24h ({precip_24h:.1f}mm)."
                        rain_label = f"Low ({precip_24h:.1f}mm)"

                    weather_summary = WeatherSummary(
                        temperature=f"{round(float(curr_temp))}°C",
                        rain_chance=rain_label,
                        spray_advisory=spray_adv,
                    )
        except Exception as e:
            # Weather fetch shouldn't block the scan diagnosis
            pass

    return await apply_guardrail(
        image_bytes=image_bytes,
        mime_type=mime_type,
        crop_type=crop_type,
        language=language,
        farmer_comment=farmer_comment,
        operational_context=op_context,
        weather_summary=weather_summary,
    )

# ── Weather Endpoint ────────────────────────────────────────────────────────
@app.get("/api/weather", tags=["Weather"])
async def get_weather(
    latitude: float = Query(..., description="GPS Latitude"),
    longitude: float = Query(..., description="GPS Longitude"),
):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m",
        "daily": "precipitation_sum",
        "timezone": "auto",
        "forecast_days": 3
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            return {
                "current_temperature": data.get("current", {}).get("temperature_2m"),
                "current_humidity": data.get("current", {}).get("relative_humidity_2m"),
                "precipitation_forecast": data.get("daily", {}).get("precipitation_sum")
            }
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Weather API error: {str(e)}")
