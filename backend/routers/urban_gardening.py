from fastapi import APIRouter, Depends
from models.user import User
from schemas.urban_gardening import UrbanGardeningRequest, UrbanGardeningResponse
from services.auth_service import get_current_user
from services.urban_gardening_service import advise_urban_gardening

router = APIRouter()


@router.post("/advise", response_model=UrbanGardeningResponse, summary="Get urban gardening advice")
def urban_gardening_advise(
    req: UrbanGardeningRequest,
    current_user: User = Depends(get_current_user),
) -> UrbanGardeningResponse:
    """
    Returns rule-based care schedule, watering plan, sunlight assessment,
    soil mix recommendation, and actionable tips for container gardening.
    Requires authentication.
    """
    return advise_urban_gardening(req)
