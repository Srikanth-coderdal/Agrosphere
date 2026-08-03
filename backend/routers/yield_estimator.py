from fastapi import APIRouter
from schemas.yield_estimator import YieldEstimatorRequest, YieldEstimatorResponse
from services.yield_estimator_service import predict_yield

router = APIRouter()


@router.post("/predict", response_model=YieldEstimatorResponse, summary="Predict crop yield algorithmically")
def yield_predict(req: YieldEstimatorRequest) -> YieldEstimatorResponse:
    """
    Returns estimated yield in tons, confidence range, key yield drivers,
    and optimization suggestions using deterministic agricultural models.
    """
    return predict_yield(req)
