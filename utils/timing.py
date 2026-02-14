import time
from typing import Optional, Dict, Any
from contextlib import contextmanager

from utils.logger import setup_logger

logger = setup_logger(__name__)


class StageTimer:
    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id
        self.stages: Dict[str, Dict[str, Any]] = {}
        self.current_stage: Optional[str] = None
        self.current_stage_start: Optional[float] = None
    
    @contextmanager
    def stage(self, stage_name: str):
        self.start_stage(stage_name)
        try:
            yield
        finally:
            self.end_stage()
    
    def start_stage(self, stage_name: str):
        self.current_stage = stage_name
        self.current_stage_start = time.time()
        
        logger.debug(
            f"Stage started: {stage_name}",
            extra={
                "stage": stage_name,
                "correlation_id": self.correlation_id
            }
        )
    
    def end_stage(self):
        if self.current_stage and self.current_stage_start:
            duration_ms = (time.time() - self.current_stage_start) * 1000
            
            self.stages[self.current_stage] = {
                "duration_ms": round(duration_ms, 2),
                "timestamp": time.time()
            }
            
            logger.debug(
                f"Stage completed: {self.current_stage}",
                extra={
                    "stage": self.current_stage,
                    "duration_ms": round(duration_ms, 2),
                    "correlation_id": self.correlation_id
                }
            )
            
            self.current_stage = None
            self.current_stage_start = None
    
    def get_summary(self) -> Dict[str, Any]:
        total_duration = sum(
            stage_data["duration_ms"]
            for stage_data in self.stages.values()
        )
        
        return {
            "stages": self.stages,
            "total_duration_ms": round(total_duration, 2),
            "stage_count": len(self.stages)
        }
    
    def log_summary(self, operation_name: str):
        summary = self.get_summary()
        
        logger.info(
            f"{operation_name} timing summary",
            extra={
                "operation": operation_name,
                "total_duration_ms": summary["total_duration_ms"],
                "stage_count": summary["stage_count"],
                "stages": summary["stages"],
                "correlation_id": self.correlation_id
            }
        )


@contextmanager
def timed_stage(stage_name: str, correlation_id: Optional[str] = None):
    start_time = time.time()
    
    logger.debug(
        f"Stage started: {stage_name}",
        extra={"stage": stage_name, "correlation_id": correlation_id}
    )
    
    try:
        yield
    finally:
        duration_ms = (time.time() - start_time) * 1000
        
        logger.debug(
            f"Stage completed: {stage_name}",
            extra={
                "stage": stage_name,
                "duration_ms": round(duration_ms, 2),
                "correlation_id": correlation_id
            }
        )
