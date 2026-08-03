from typing import Optional, List, Literal, Dict
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# 1. Crop Disease Scanner
# ─────────────────────────────────────────────

class ScanRequest(BaseModel):
    """Image bytes are sent via multipart/form-data; only optional comment here."""
    farmer_comment: Optional[str] = Field(default=None, description="Farmer's observation about the crop.")


class ScanResponse(BaseModel):
    disease_name: str = Field(..., description="Identified disease or 'Healthy'.")
    status: Literal["Healthy", "Diseased", "Unclear"] = Field(..., description="Overall crop health status.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Model confidence (0.0 – 1.0).")
    visible_symptoms: List[str] = Field(default_factory=list, description="Observed symptoms on the crop.")
    organic_remedies: List[str] = Field(default_factory=list, description="Organic/natural treatment options.")
    chemical_remedies: List[str] = Field(default_factory=list, description="Chemical treatment options.")
    preventive_measures: List[str] = Field(default_factory=list, description="Steps to prevent future infection.")


# ─────────────────────────────────────────────
# 2. Smart Irrigation Advisor
# ─────────────────────────────────────────────

class IrrigationRequest(BaseModel):
    crop_type: str = Field(..., description="Type of crop being irrigated.")
    field_area_acres: float = Field(..., gt=0, description="Total field area in acres.")
    soil_type: str = Field(..., description="Soil classification (e.g. Clay, Sandy, Loamy).")
    growth_stage: str = Field(..., description="Current crop growth stage (e.g. Seedling, Vegetative, Flowering).")
    irrigation_system: str = Field(..., description="Irrigation method used (e.g. Drip, Sprinkler, Flood).")
    current_soil_moisture: Optional[str] = Field(default=None, description="Current soil moisture reading or description.")


class IrrigationResponse(BaseModel):
    daily_water_requirement_liters: float = Field(..., ge=0, description="Recommended daily water volume in liters.")
    recommended_schedule: str = Field(..., description="Human-readable irrigation schedule.")
    system_efficiency_score: float = Field(..., ge=0.0, le=1.0, description="Efficiency rating of the irrigation system.")
    optimization_tips: List[str] = Field(default_factory=list, description="Actionable tips to improve irrigation efficiency.")


# ─────────────────────────────────────────────
# 3. Crop Yield Predictor & Optimizer
# ─────────────────────────────────────────────

class YieldRequest(BaseModel):
    crop_type: str = Field(..., description="Type of crop to predict yield for.")
    field_area_acres: float = Field(..., gt=0, description="Total field area in acres.")
    seed_variety: Optional[str] = Field(default=None, description="Specific seed variety if known.")
    npk_ratios: str = Field(..., description="NPK fertilizer ratio applied (e.g. '14-14-14').")
    historical_yield_tons: Optional[float] = Field(default=None, ge=0, description="Previous season's yield in tons.")
    soil_ph: Optional[float] = Field(default=None, ge=0.0, le=14.0, description="Measured soil pH level.")


class YieldResponse(BaseModel):
    predicted_yield_tons: float = Field(..., ge=0, description="Total predicted yield in tons.")
    yield_per_acre: float = Field(..., ge=0, description="Predicted yield per acre in tons.")
    harvest_window_recommendation: str = Field(..., description="Recommended harvest time window.")
    crop_rotation_suggestions: List[str] = Field(default_factory=list, description="Suggested crops for next season rotation.")
    soil_health_advice: List[str] = Field(default_factory=list, description="Advice to maintain or improve soil health.")


# ─────────────────────────────────────────────
# 4. Urban Gardening Advisor
# ─────────────────────────────────────────────

class CareSchedule(BaseModel):
    watering: str = Field(..., description="Watering frequency and instructions.")
    fertilizing: str = Field(..., description="Fertilizing schedule and instructions.")
    pruning: str = Field(..., description="Pruning schedule and instructions.")


class UrbanRequest(BaseModel):
    plant_name: str = Field(..., description="Name of the plant to grow.")
    space_type: str = Field(..., description="Available space type (e.g. Balcony, Indoor Window, Rooftop).")
    sunlight_hours_per_day: float = Field(..., ge=0, le=24, description="Average daily sunlight hours available.")
    container_size_liters: float = Field(..., gt=0, description="Container or pot volume in liters.")
    growing_medium: str = Field(..., description="Growing medium used (e.g. Soil Mix, Coco Peat, Hydroponics).")


class UrbanResponse(BaseModel):
    suitability_score: float = Field(..., ge=0.0, le=1.0, description="How suitable the space is for the plant (0.0 – 1.0).")
    care_schedule: CareSchedule = Field(..., description="Structured care schedule for watering, fertilizing, and pruning.")
    container_recommendation: str = Field(..., description="Recommended container type, size, or material.")
    common_issues: List[str] = Field(default_factory=list, description="Common problems to watch out for.")
