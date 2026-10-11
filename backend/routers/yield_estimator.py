from fastapi import APIRouter, Depends
from models.user import User
from schemas.yield_estimator import YieldEstimatorRequest, YieldEstimatorResponse
from services.auth_service import get_current_user
from services.yield_estimator_service import predict_yield

router = APIRouter()


@router.post("/predict", response_model=YieldEstimatorResponse, summary="Predict crop yield algorithmically")
async def yield_predict(
    req: YieldEstimatorRequest,
    current_user: User = Depends(get_current_user),
) -> YieldEstimatorResponse:
    """
    Returns estimated yield in tons, confidence range, key yield drivers,
    and optimization suggestions using crop-tailored agricultural models and Gemini AI.
    Requires authentication.
    """
    return await predict_yield(req)
