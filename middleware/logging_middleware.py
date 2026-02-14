from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import uuid
from typing import Callable

from utils.logger import setup_logger

logger = setup_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID")
        
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        request.state.correlation_id = correlation_id
        
        response = await call_next(request)
        
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        correlation_id = getattr(request.state, "correlation_id", None)
        
        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "correlation_id": correlation_id,
                "client_host": request.client.host if request.client else None
            }
        )
        
        response = await call_next(request)
        
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "correlation_id": correlation_id
            }
        )
        
        response.headers["X-Request-Duration-Ms"] = str(round(duration_ms, 2))
        
        return response
