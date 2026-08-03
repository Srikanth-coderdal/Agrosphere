from fastapi import APIRouter
from schemas.urban_gardening import UrbanGardeningRequest, UrbanGardeningResponse
from services.urban_gardening_service import advise_urban_gardening

router = APIRouter()


@router.post("/advise", response_model=UrbanGardeningResponse, summary="Get urban gardening advice")
def urban_gardening_advise(req: UrbanGardeningRequest) -> UrbanGardeningResponse:
    """
    Returns rule-based care schedule, watering plan, sunlight assessment,
    soil mix recommendation, and actionable tips for container gardening.
    """
    return advise_urban_gardening(req)
