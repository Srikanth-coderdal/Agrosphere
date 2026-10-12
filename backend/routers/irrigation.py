from fastapi import APIRouter, Depends
from models.user import User
from schemas.irrigation import IrrigationRequest, IrrigationResponse
from services.auth_service import get_current_user
from services.irrigation_service import calculate_irrigation

router = APIRouter()


@router.post("/calculate", response_model=IrrigationResponse, summary="Calculate smart irrigation requirements")
async def irrigation_calculate(
    req: IrrigationRequest,
    current_user: User = Depends(get_current_user),
) -> IrrigationResponse:
    """
    Accepts crop, soil, and weather inputs.
    Returns 100% deterministic FAO-56 water requirements and irrigation schedule with zero LLM dependency.
    Requires authentication.
    """
    return await calculate_irrigation(req)
