from typing import List
from pydantic import BaseModel, Field


class YieldRequest(BaseModel):
    crop_type: str = Field(..., description="Crop to predict yield for (e.g. Tomato, Wheat, Rice, Maize, Potato).")
    field_size_hectares: float = Field(..., gt=0, description="Total cultivated area in hectares.")
    region_location: str = Field(..., description="Geographic region (e.g. 'Punjab, India', 'California, USA').")
    fertilizer_used_kg: float = Field(..., ge=0.0, description="Total fertilizer applied in kilograms.")
    irrigation_type: str = Field(..., description="Irrigation method (e.g. Drip, Sprinkler, Flood, Rainfed).")
    soil_ph: float = Field(..., ge=0.0, le=14.0, description="Measured soil pH level.")


class MarketPriceInfo(BaseModel):
    market_name: str = Field(..., description="Name of local or regional market.")
    current_price_per_ton: float = Field(..., ge=0, description="Current price per metric ton in USD.")
    trend: str = Field(..., description="Price direction (e.g. Rising, Stable, Falling).")


class YieldResponse(BaseModel):
    estimated_yield_tons: float = Field(..., ge=0, description="Total estimated crop yield in metric tons.")
    yield_per_hectare_tons: float = Field(..., ge=0, description="Yield per hectare in metric tons.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Model confidence in yield estimate (0.0–1.0).")
    projected_revenue_usd: float = Field(..., ge=0, description="Projected revenue in USD based on market prices.")
    local_market_prices: List[MarketPriceInfo] = Field(default_factory=list, description="Nearby market price listings.")
    market_insights: str = Field(..., description="AI-generated regional market analysis narrative.")
    optimization_tips: List[str] = Field(default_factory=list, description="Actionable tips to maximize yield and ROI.")
