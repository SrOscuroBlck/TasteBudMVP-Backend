import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from sqlmodel import Session

from config.database import engine
from services.infrastructure.index_maintenance_service import IndexMaintenanceService
from utils.logger import setup_logger

logger = setup_logger(__name__)


class ScheduledIndexMaintenance:
    def __init__(self, interval_hours: int = 24):
        self.interval_hours = interval_hours
        self.maintenance_service = IndexMaintenanceService()
        self.running = False
        self.task: Optional[asyncio.Task] = None
    
    async def run_scheduled_rebuild(self):
        self.running = True
        
        logger.info(
            "Scheduled index maintenance started",
            extra={"interval_hours": self.interval_hours}
        )
        
        while self.running:
            try:
                await asyncio.sleep(self.interval_hours * 3600)
                
                if not self.running:
                    break
                
                logger.info("Starting scheduled index rebuild")
                
                with Session(engine) as session:
                    result = self.maintenance_service.rebuild_full_index(
                        session=session,
                        dimension=64,
                        index_name="current"
                    )
                    
                    if result.success:
                        logger.info(
                            "Scheduled index rebuild completed successfully",
                            extra={
                                "items_indexed": result.items_indexed,
                                "duration_seconds": result.build_duration_seconds
                            }
                        )
                    else:
                        logger.error(
                            "Scheduled index rebuild failed",
                            extra={"error": result.error_message}
                        )
                
            except asyncio.CancelledError:
                logger.info("Scheduled index maintenance cancelled")
                break
            except Exception as e:
                logger.error(
                    "Unexpected error in scheduled index maintenance",
                    extra={"error": str(e)},
                    exc_info=True
                )
                await asyncio.sleep(3600)
    
    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run_scheduled_rebuild())
            logger.info("Scheduled index maintenance task created")
    
    async def stop(self):
        self.running = False
        
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Scheduled index maintenance stopped")


scheduled_maintenance = None


@asynccontextmanager
async def lifespan_with_scheduled_maintenance(app, interval_hours: int = 24):
    global scheduled_maintenance
    
    scheduled_maintenance = ScheduledIndexMaintenance(interval_hours=interval_hours)
    scheduled_maintenance.start()
    
    yield
    
    await scheduled_maintenance.stop()
