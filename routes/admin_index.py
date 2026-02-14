from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session
from pydantic import BaseModel, Field
from typing import Optional

from config.database import get_session
from services.index_maintenance_service import IndexMaintenanceService, IndexMaintenanceResult
from utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/admin/index", tags=["admin"])


class IndexRebuildRequest(BaseModel):
    dimension: int = Field(default=64, ge=64, le=1536)
    index_name: str = Field(default="current", min_length=1, max_length=50)


class IndexRebuildResponse(BaseModel):
    success: bool
    message: str
    items_indexed: Optional[int] = None
    dimension: Optional[int] = None
    build_duration_seconds: Optional[float] = None
    index_name: Optional[str] = None
    timestamp: str


def rebuild_result_to_response(result: IndexMaintenanceResult) -> IndexRebuildResponse:
    if result.success:
        message = f"Index rebuilt successfully with {result.items_indexed} items"
    else:
        message = f"Index rebuild failed: {result.error_message}"
    
    return IndexRebuildResponse(
        success=result.success,
        message=message,
        items_indexed=result.items_indexed if result.success else None,
        dimension=result.dimension,
        build_duration_seconds=result.build_duration_seconds,
        index_name=result.index_name,
        timestamp=result.timestamp.isoformat()
    )


@router.post("/rebuild", response_model=IndexRebuildResponse)
def rebuild_index(
    request: IndexRebuildRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    logger.info(
        "Index rebuild requested",
        extra={
            "dimension": request.dimension,
            "index_name": request.index_name
        }
    )
    
    try:
        maintenance_service = IndexMaintenanceService()
        
        result = maintenance_service.rebuild_full_index(
            session=session,
            dimension=request.dimension,
            index_name=request.index_name
        )
        
        if not result.success:
            logger.error(
                "Index rebuild failed",
                extra={
                    "dimension": request.dimension,
                    "index_name": request.index_name,
                    "error": result.error_message
                }
            )
            raise HTTPException(
                status_code=500,
                detail=f"Index rebuild failed: {result.error_message}"
            )
        
        logger.info(
            "Index rebuild completed successfully",
            extra={
                "items_indexed": result.items_indexed,
                "dimension": request.dimension,
                "index_name": request.index_name,
                "duration_seconds": result.build_duration_seconds
            }
        )
        
        return rebuild_result_to_response(result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Unexpected error during index rebuild",
            extra={
                "dimension": request.dimension,
                "index_name": request.index_name,
                "error": str(e)
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during index rebuild: {str(e)}"
        )


@router.get("/status")
def get_index_status(session: Session = Depends(get_session)):
    try:
        maintenance_service = IndexMaintenanceService()
        
        status_64d = maintenance_service.should_rebuild_index(
            index_name="current",
            dimension=64,
            max_age_hours=24
        )
        
        status_1536d = maintenance_service.should_rebuild_index(
            index_name="current",
            dimension=1536,
            max_age_hours=24
        )
        
        return {
            "64d_index": {
                "should_rebuild": status_64d,
                "index_name": "current"
            },
            "1536d_index": {
                "should_rebuild": status_1536d,
                "index_name": "current"
            }
        }
    except Exception as e:
        logger.error(
            "Failed to check index status",
            extra={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check index status: {str(e)}"
        )
