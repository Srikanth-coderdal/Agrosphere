from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Base, engine
from models import user as _user_model  # noqa: F401 — registers User table with Base
from routers import auth, irrigation, urban_gardening, yield_estimator
from schemas_core import ScanResponse
from services.gemini_service import analyze_crop_image


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
@app.post("/api/scan", response_model=ScanResponse, tags=["Disease Scanner"])
async def scan_crop(
    image: UploadFile = File(..., description="Crop leaf image (.jpg, .jpeg, .png, .webp)"),
    farmer_comment: Optional[str] = Form(None, description="Optional farmer observation text"),
    language: str = Form("en", description="Response language code (e.g. 'en' or 'ta')."),
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

    result: dict = await analyze_crop_image(
        image_bytes=image_bytes,
        farmer_comment=farmer_comment,
        mime_type=mime_type,
        language=language,
    )
    return ScanResponse(**result)
