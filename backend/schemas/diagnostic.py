from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator

class DiagnosticRequest(BaseModel):
    crop_type: str = Field(..., description="Crop being grown.")
    latitude: Optional[float] = Field(None, description="GPS Latitude")
    longitude: Optional[float] = Field(None, description="GPS Longitude")
    language: Literal['en', 'ta'] = Field('en', description="Response language")
    image: Optional[str] = Field(None, description="Base64 or URL (if used in JSON endpoints)")
    farmer_comment: Optional[str] = Field(None, description="Optional farmer observations.")

class SafeDosage(BaseModel):
    chemical_name: str = Field(..., description="Name of the active ingredient or product.")
    dosage: str = Field(..., description="Safe dosage instructions.")
    unit: str = Field(..., description="Unit of measurement.")
    max_frequency: str = Field(..., description="Maximum re-application frequency.")
    pre_harvest_interval_days: Optional[int] = Field(None, ge=0, description="Minimum days between last application and harvest. Null if not stated in the verified source manual — never estimate this value.")

class WeatherSummary(BaseModel):
    temperature: str = Field(..., description="Current temperature string, e.g. '28°C'.")
    rain_chance: str = Field(..., description="Rain forecast label, e.g. 'High (5.2mm)'.")
    spray_advisory: str = Field(..., description="Spray advisory based on precipitation forecast.")

class VerifiedDiagnosticResponse(BaseModel):
    pathogen: str = Field(..., description="Verified pathogen or condition label.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Final confidence score.")
    verified_treatment: str = Field(..., description="Treatment plan.")
    safe_dosages: List[SafeDosage] = Field(default_factory=list, description="Verified safe dosages.")
    organic_recommendations: List[str] = Field(default_factory=list, description="Organic recommendations.")
    preventive_measures: List[str] = Field(default_factory=list, description="Prevention advice.")
    disclaimer: str = Field(..., description="Safety disclaimer.")
    is_verified: bool = Field(..., description="True if verified.")
    weather_summary: Optional[WeatherSummary] = Field(None, description="Weather & spray advisory for the scan location.")
