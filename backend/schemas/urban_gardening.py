from typing import List, Literal
from pydantic import BaseModel, Field


class UrbanGardeningRequest(BaseModel):
    plant_type: str = Field(..., description="Name of the plant (e.g. Basil, Mint, Tomato, Succulent).")
    space_type: Literal["balcony", "indoor", "rooftop"] = Field(..., description="Available gardening space type.")
    sunlight_hours: float = Field(..., ge=0.0, le=24.0, description="Average daily sunlight hours the space receives.")
    container_size: float = Field(..., gt=0, description="Container/pot volume in liters.")
    language: str = Field(default="en", description="Response language code (e.g. 'en' or 'ta').")


class UrbanGardeningResponse(BaseModel):
    care_schedule: str = Field(..., description="Overall weekly care routine summary.")
    watering_frequency: str = Field(..., description="Recommended watering frequency and amount.")
    sunlight_recommendations: str = Field(..., description="Sunlight suitability assessment and tips.")
    soil_mix: str = Field(..., description="Recommended soil or growing medium mix.")
    actionable_tips: List[str] = Field(default_factory=list, description="Specific actionable care tips.")
