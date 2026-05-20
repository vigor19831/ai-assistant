"""Image analysis feature handlers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import AppState, get_state
from features.image_analysis.manager import ImageAnalysisManager
from features.image_analysis.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter(prefix="/image", tags=["image"])


def _get_manager(state: AppState = Depends(get_state)) -> ImageAnalysisManager:
    return ImageAnalysisManager(
        vision=state.vision,
        llm=state.llm,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_image(
    req: AnalyzeRequest,
    manager: ImageAnalysisManager = Depends(_get_manager),
) -> AnalyzeResponse:
    if not req.image_base64 and not req.image_url:
        raise HTTPException(status_code=400, detail="Provide image_base64 or image_url")
    try:
        result = await manager.analyze(
            image_base64=req.image_base64,
            image_url=req.image_url,
            prompt=req.prompt,
        )
        source = "llm" if manager.use_llm_vision else "vision"
        return AnalyzeResponse(
            description=result.text or "",
            source=source,
            metadata=req.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
