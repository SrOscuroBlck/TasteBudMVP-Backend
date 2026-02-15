from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from sqlmodel import Session, select
from typing import Dict, Any
from datetime import datetime

from config.database import get_session
from models.restaurant import MenuItem
from services.features.faiss_service import FAISSService
from services.infrastructure.similarity_matrix_service import SimilarityMatrixService
from utils.logger import setup_logger

router = APIRouter(prefix="/admin/rebuild", tags=["Admin - Index Maintenance"])
logger = setup_logger(__name__)


rebuild_status = {
    "faiss_64d": {"status": "idle", "last_run": None, "items_count": 0, "error": None},
    "faiss_1536d": {"status": "idle", "last_run": None, "items_count": 0, "error": None},
    "similarity_matrix": {"status": "idle", "last_run": None, "items_count": 0, "error": None}
}


def rebuild_faiss_64d(session: Session):
    global rebuild_status
    rebuild_status["faiss_64d"]["status"] = "running"
    
    try:
        items = session.exec(
            select(MenuItem).where(MenuItem.reduced_embedding.is_not(None))
        ).all()
        
        if not items:
            rebuild_status["faiss_64d"]["status"] = "idle"
            rebuild_status["faiss_64d"]["error"] = "No items with reduced_embedding found"
            return
        
        embeddings = [item.reduced_embedding for item in items]
        item_ids = [item.id for item in items]
        
        faiss_service = FAISSService()
        faiss_service.build_index(embeddings, item_ids, dimension=64)
        faiss_service.save("current")
        
        rebuild_status["faiss_64d"]["status"] = "completed"
        rebuild_status["faiss_64d"]["last_run"] = datetime.utcnow().isoformat()
        rebuild_status["faiss_64d"]["items_count"] = len(items)
        rebuild_status["faiss_64d"]["error"] = None
        
        logger.info("FAISS 64D index rebuilt", extra={"items_count": len(items)})
        
    except Exception as e:
        rebuild_status["faiss_64d"]["status"] = "failed"
        rebuild_status["faiss_64d"]["error"] = str(e)
        logger.error("FAISS 64D rebuild failed", extra={"error": str(e)}, exc_info=True)


def rebuild_faiss_1536d(session: Session):
    global rebuild_status
    rebuild_status["faiss_1536d"]["status"] = "running"
    
    try:
        items = session.exec(
            select(MenuItem).where(MenuItem.embedding.is_not(None))
        ).all()
        
        if not items:
            rebuild_status["faiss_1536d"]["status"] = "idle"
            rebuild_status["faiss_1536d"]["error"] = "No items with embedding found"
            return
        
        embeddings = [item.embedding for item in items]
        item_ids = [item.id for item in items]
        
        faiss_service = FAISSService()
        faiss_service.build_index(embeddings, item_ids, dimension=1536)
        faiss_service.save("current")
        
        rebuild_status["faiss_1536d"]["status"] = "completed"
        rebuild_status["faiss_1536d"]["last_run"] = datetime.utcnow().isoformat()
        rebuild_status["faiss_1536d"]["items_count"] = len(items)
        rebuild_status["faiss_1536d"]["error"] = None
        
        logger.info("FAISS 1536D index rebuilt", extra={"items_count": len(items)})
        
    except Exception as e:
        rebuild_status["faiss_1536d"]["status"] = "failed"
        rebuild_status["faiss_1536d"]["error"] = str(e)
        logger.error("FAISS 1536D rebuild failed", extra={"error": str(e)}, exc_info=True)


def rebuild_similarity_matrix(session: Session):
    global rebuild_status
    rebuild_status["similarity_matrix"]["status"] = "running"
    
    try:
        items = session.exec(
            select(MenuItem).where(MenuItem.features.is_not(None))
        ).all()
        
        if not items:
            rebuild_status["similarity_matrix"]["status"] = "idle"
            rebuild_status["similarity_matrix"]["error"] = "No items with features found"
            return
        
        similarity_service = SimilarityMatrixService()
        similarity_service.build_matrix(items)
        similarity_service.save_to_disk("data/faiss_indexes/similarity_matrix.pkl")
        
        rebuild_status["similarity_matrix"]["status"] = "completed"
        rebuild_status["similarity_matrix"]["last_run"] = datetime.utcnow().isoformat()
        rebuild_status["similarity_matrix"]["items_count"] = len(items)
        rebuild_status["similarity_matrix"]["error"] = None
        
        logger.info("Similarity matrix rebuilt", extra={"items_count": len(items)})
        
    except Exception as e:
        rebuild_status["similarity_matrix"]["status"] = "failed"
        rebuild_status["similarity_matrix"]["error"] = str(e)
        logger.error("Similarity matrix rebuild failed", extra={"error": str(e)}, exc_info=True)


@router.post("/faiss-64d")
def trigger_faiss_64d_rebuild(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    if rebuild_status["faiss_64d"]["status"] == "running":
        raise HTTPException(status_code=409, detail="FAISS 64D rebuild already in progress")
    
    background_tasks.add_task(rebuild_faiss_64d, session)
    
    return {
        "message": "FAISS 64D index rebuild started",
        "status": "running"
    }


@router.post("/faiss-1536d")
def trigger_faiss_1536d_rebuild(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    if rebuild_status["faiss_1536d"]["status"] == "running":
        raise HTTPException(status_code=409, detail="FAISS 1536D rebuild already in progress")
    
    background_tasks.add_task(rebuild_faiss_1536d, session)
    
    return {
        "message": "FAISS 1536D index rebuild started",
        "status": "running"
    }


@router.post("/similarity-matrix")
def trigger_similarity_matrix_rebuild(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    if rebuild_status["similarity_matrix"]["status"] == "running":
        raise HTTPException(status_code=409, detail="Similarity matrix rebuild already in progress")
    
    background_tasks.add_task(rebuild_similarity_matrix, session)
    
    return {
        "message": "Similarity matrix rebuild started",
        "status": "running"
    }


@router.post("/all")
def trigger_all_rebuilds(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    tasks = []
    
    if rebuild_status["faiss_64d"]["status"] != "running":
        background_tasks.add_task(rebuild_faiss_64d, session)
        tasks.append("faiss_64d")
    
    if rebuild_status["faiss_1536d"]["status"] != "running":
        background_tasks.add_task(rebuild_faiss_1536d, session)
        tasks.append("faiss_1536d")
    
    if rebuild_status["similarity_matrix"]["status"] != "running":
        background_tasks.add_task(rebuild_similarity_matrix, session)
        tasks.append("similarity_matrix")
    
    if not tasks:
        raise HTTPException(status_code=409, detail="All rebuilds already in progress")
    
    return {
        "message": "Rebuild tasks started",
        "tasks": tasks,
        "status": "running"
    }


@router.get("/status")
def get_rebuild_status() -> Dict[str, Any]:
    return rebuild_status
