from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import httpx

from dotenv import load_dotenv, find_dotenv

# Automatically locate and load backend/.env (or fallback to root .env)
_BACKEND_ENV_PATH = Path(__file__).resolve().parent / ".env"
if _BACKEND_ENV_PATH.exists():
    load_dotenv(dotenv_path=_BACKEND_ENV_PATH)
else:
    load_dotenv(find_dotenv())

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Base, engine, get_db
from models import user as _user_model  # noqa: F401 — registers User, RevokedToken, ConsentedUpload tables
from models.user import ConsentedUpload, User
from routers import auth, irrigation, urban_gardening, yield_estimator
from schemas.diagnostic import VerifiedDiagnosticResponse, WeatherSummary
from services.auth_service import get_current_user
from services.rag_guardrail import apply_guardrail
from services.upload_security import (
    MAX_UPLOAD_SIZE_BYTES,
    delete_all_consented_uploads_for_user,
    delete_consented_upload_by_id,
    store_consented_image,
    validate_and_sanitize_image,
)
from sqlalchemy.orm import Session

# Ensure tables exist even when TestClient is used without lifespan context
Base.metadata.create_all(bind=engine)

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
    consent_to_store: bool = Form(
        False,
        description="Explicit user opt-in consent to store the anonymized, metadata-stripped image to help improve the model.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Read bounded bytes (MAX_UPLOAD_SIZE_BYTES + 1) to prevent memory exhaustion on huge uploads
    raw_bytes = await image.read(MAX_UPLOAD_SIZE_BYTES + 1)
    sanitized_bytes, sanitized_mime = validate_and_sanitize_image(raw_bytes)

    # Do NOT retain images by default; store ONLY when explicit user consent is given
    stored_upload_id: Optional[str] = None
    if consent_to_store:
        stored_upload_id = store_consented_image(
            db=db,
            user_id=current_user.id,
            crop_type=crop_type,
            sanitized_bytes=sanitized_bytes,
        )

    op_context = operational_context or context_mode

    weather_summary: Optional[WeatherSummary] = None
    if latitude is not None and longitude is not None:
        try:
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_params = {
                "latitude": round(float(latitude), 2),
                "longitude": round(float(longitude), 2),
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
        except Exception:
            # Weather fetch shouldn't block the scan diagnosis
            weather_summary = None

    result = await apply_guardrail(
        image_bytes=sanitized_bytes,
        mime_type=sanitized_mime,
        crop_type=crop_type,
        language=language,
        farmer_comment=farmer_comment,
        operational_context=op_context,
        weather_summary=weather_summary,
    )
    if stored_upload_id:
        result.stored_upload_id = stored_upload_id
    return result


# ── User Consented Upload Management & Deletion on Request ────────────────────
@app.get("/api/scan/uploads", tags=["Disease Scanner"])
def list_consented_uploads(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all consented image uploads belonging to the current user."""
    records = (
        db.query(ConsentedUpload)
        .filter(ConsentedUpload.user_id == current_user.id)
        .order_by(ConsentedUpload.created_at.desc())
        .all()
    )
    return {
        "uploads": [
            {
                "upload_id": r.upload_id,
                "filename": r.filename,
                "crop_type": r.crop_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }


@app.delete("/api/scan/uploads/{upload_id}", tags=["Disease Scanner"])
def delete_consented_upload(
    upload_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a specific consented image upload on user request."""
    delete_consented_upload_by_id(db=db, user_id=current_user.id, upload_id=upload_id)
    return {"deleted": True, "upload_id": upload_id}


@app.delete("/api/scan/uploads", tags=["Disease Scanner"])
def delete_all_user_uploads(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete all stored consented image uploads for the authenticated user."""
    deleted_count = delete_all_consented_uploads_for_user(db=db, user_id=current_user.id)
    return {"deleted": True, "deleted_count": deleted_count}

# ── Weather Endpoint ────────────────────────────────────────────────────────
@app.get("/api/weather", tags=["Weather"])
async def get_weather(
    latitude: float = Query(..., description="GPS Latitude"),
    longitude: float = Query(..., description="GPS Longitude"),
    current_user: User = Depends(get_current_user),
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
    
    async with httpx.AsyncClient(timeout=5.0) as client:
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
