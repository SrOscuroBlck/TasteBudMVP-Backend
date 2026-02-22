from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from typing import Dict, Any
from datetime import datetime

from config.database import get_session, engine
from models.restaurant import MenuItem, Restaurant
from models.user import User
from services.features.faiss_service import FAISSService
from utils.circuit_breaker import openai_circuit_breaker, embedding_circuit_breaker
from utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "tastebud-api"
    }


@router.get("/detailed")
def detailed_health_check(session: Session = Depends(get_session)):
    health_status: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "tastebud-api",
        "checks": {}
    }
    
    try:
        result = session.exec(select(func.count()).select_from(MenuItem)).one()
        health_status["checks"]["database"] = {
            "status": "healthy",
            "menu_items_count": result
        }
    except Exception as e:
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    try:
        faiss_service = FAISSService()
        
        try:
            faiss_service.load(index_name="current", dimension=64)
            health_status["checks"]["faiss_64d"] = {
                "status": "healthy",
                "index_size": faiss_service.index_size,
                "dimension": 64
            }
        except FileNotFoundError:
            health_status["checks"]["faiss_64d"] = {
                "status": "not_found",
                "message": "Index file not found"
            }
        except Exception as e:
            health_status["checks"]["faiss_64d"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
    except Exception as e:
        health_status["checks"]["faiss"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    health_status["checks"]["circuit_breakers"] = {
        "openai": openai_circuit_breaker.get_state(),
        "embedding": embedding_circuit_breaker.get_state()
    }
    
    return health_status


@router.get("/ready")
def readiness_check(session: Session = Depends(get_session)):
    checks_passed = True
    checks: Dict[str, Any] = {}
    
    try:
        session.exec(select(func.count()).select_from(MenuItem)).one()
        checks["database"] = {"status": "ready"}
    except Exception as e:
        checks["database"] = {"status": "not_ready", "error": str(e)}
        checks_passed = False
    
    try:
        faiss_service = FAISSService()
        faiss_service.load(index_name="current", dimension=64)
        checks["faiss"] = {"status": "ready", "index_size": faiss_service.index_size}
    except FileNotFoundError:
        checks["faiss"] = {"status": "not_ready", "reason": "index_not_found"}
        checks_passed = False
    except Exception as e:
        checks["faiss"] = {"status": "not_ready", "error": str(e)}
        checks_passed = False
    
    if openai_circuit_breaker.state.value == "open":
        checks["openai_circuit_breaker"] = {"status": "not_ready", "reason": "circuit_open"}
        checks_passed = False
    else:
        checks["openai_circuit_breaker"] = {"status": "ready"}
    
    return {
        "ready": checks_passed,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/live")
def liveness_check():
    return {
        "alive": True,
        "timestamp": datetime.utcnow().isoformat()
    }
