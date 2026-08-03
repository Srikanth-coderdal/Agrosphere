from typing import List, Literal, Tuple
from pydantic import BaseModel, Field


class YieldEstimatorRequest(BaseModel):
    crop_type: str = Field(..., description="Crop being grown (e.g. Wheat, Rice, Tomato, Maize, Potato).")
    field_size_hectares: float = Field(..., gt=0, description="Total field area in hectares.")
    soil_type: Literal["clay", "sandy", "loam", "silty", "chalky", "peaty"] = Field(..., description="Soil classification.")
    historical_yield_tons: float = Field(..., ge=0.0, description="Last season's total yield in tons (0 if first season).")
    irrigation_type: Literal["drip", "sprinkler", "flood", "rainfed"] = Field(..., description="Irrigation method in use.")
    weather_condition: Literal["optimal", "drought", "heavy_rain", "moderate"] = Field(..., description="Predominant weather condition this season.")


class YieldEstimatorResponse(BaseModel):
    estimated_yield_tons: float = Field(..., ge=0, description="Projected total yield in metric tons.")
    confidence_range: str = Field(..., description="Confidence interval string (e.g. '18.5 – 22.1 tons').")
    key_yield_drivers: List[str] = Field(default_factory=list, description="Top factors influencing the yield estimate.")
    optimization_suggestions: List[str] = Field(default_factory=list, description="Actionable steps to improve yield.")
