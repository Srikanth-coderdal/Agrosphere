from typing import Optional, List
from pydantic import BaseModel, Field


class IrrigationRequest(BaseModel):
    crop_type: str = Field(..., description="Crop being grown (e.g. Tomato, Wheat, Maize, Rice).")
    growth_stage: str = Field(..., description="Current crop growth stage (e.g. Initial, Crop Development, Mid-Stage, Late Stage).")
    soil_type: str = Field(..., description="Soil classification (e.g. Clay, Sandy, Loam, Silty).")
    field_size_hectares: float = Field(..., gt=0, description="Total field area in hectares.")
    soil_moisture_percentage: float = Field(..., ge=0.0, le=100.0, description="Current soil moisture as a percentage.")
    temperature_celsius: Optional[float] = Field(default=28.0, description="Ambient temperature in Celsius.")
    rainfall_probability_percent: Optional[float] = Field(default=10.0, ge=0.0, le=100.0, description="Probability of rainfall (%).")
    language: str = Field(default="en", description="Response language code (e.g. 'en' or 'ta').")


class IrrigationResponse(BaseModel):
    water_required_liters: float = Field(..., ge=0, description="Estimated water volume required in liters.")
    recommended_schedule: str = Field(..., description="Human-readable recommended irrigation schedule.")
    evapotranspiration_index: str = Field(..., description="ET index with unit (e.g. 'High (5.2 mm/day)').")
    weather_summary: str = Field(..., description="Brief AI-generated weather and condition summary.")
    actionable_tips: List[str] = Field(default_factory=list, description="Specific irrigation optimization tips.")
