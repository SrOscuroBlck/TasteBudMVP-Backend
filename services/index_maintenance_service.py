from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from models.restaurant import MenuItem
from services.faiss_service import FAISSService
from services.embedding_service import EmbeddingService
from utils.logger import setup_logger

logger = setup_logger(__name__)


class IndexMaintenanceResult:
    def __init__(
        self,
        success: bool,
        items_indexed: int,
        dimension: int,
        build_duration_seconds: float,
        index_name: str,
        error_message: Optional[str] = None
    ):
        self.success = success
        self.items_indexed = items_indexed
        self.dimension = dimension
        self.build_duration_seconds = build_duration_seconds
        self.index_name = index_name
        self.error_message = error_message
        self.timestamp = datetime.utcnow()


class IndexMaintenanceService:
    def __init__(self):
        self.faiss_service = FAISSService()
        self.embedding_service = EmbeddingService()
    
    def rebuild_full_index(
        self,
        session: Session,
        dimension: int = 64,
        index_name: str = "current"
    ) -> IndexMaintenanceResult:
        start_time = datetime.utcnow()
        
        try:
            logger.info(
                "Starting full index rebuild",
                extra={"dimension": dimension, "index_name": index_name}
            )
            
            if dimension == 64:
                items = session.exec(
                    select(MenuItem).where(MenuItem.reduced_embedding.is_not(None))
                ).all()
                embedding_field = "reduced_embedding"
            elif dimension == 1536:
                items = session.exec(
                    select(MenuItem).where(MenuItem.embedding.is_not(None))
                ).all()
                embedding_field = "embedding"
            else:
                raise ValueError(f"unsupported dimension: {dimension}")
            
            if not items:
                error_msg = f"no items found with {embedding_field}"
                logger.warning(error_msg, extra={"dimension": dimension})
                return IndexMaintenanceResult(
                    success=False,
                    items_indexed=0,
                    dimension=dimension,
                    build_duration_seconds=0.0,
                    index_name=index_name,
                    error_message=error_msg
                )
            
            embeddings = []
            item_ids = []
            
            for item in items:
                embedding = getattr(item, embedding_field)
                if embedding is not None:
                    embeddings.append(embedding)
                    item_ids.append(item.id)
            
            if not embeddings:
                error_msg = "no valid embeddings extracted"
                logger.error(error_msg)
                return IndexMaintenanceResult(
                    success=False,
                    items_indexed=0,
                    dimension=dimension,
                    build_duration_seconds=0.0,
                    index_name=index_name,
                    error_message=error_msg
                )
            
            self.faiss_service.build_index(
                embeddings=embeddings,
                item_ids=item_ids,
                dimension=dimension
            )
            
            self.faiss_service.save(index_name)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                "Full index rebuild completed successfully",
                extra={
                    "items_indexed": len(embeddings),
                    "dimension": dimension,
                    "duration_seconds": duration,
                    "index_name": index_name
                }
            )
            
            return IndexMaintenanceResult(
                success=True,
                items_indexed=len(embeddings),
                dimension=dimension,
                build_duration_seconds=duration,
                index_name=index_name
            )
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            error_msg = str(e)
            
            logger.error(
                "Full index rebuild failed",
                extra={
                    "dimension": dimension,
                    "index_name": index_name,
                    "error": error_msg
                },
                exc_info=True
            )
            
            return IndexMaintenanceResult(
                success=False,
                items_indexed=0,
                dimension=dimension,
                build_duration_seconds=duration,
                index_name=index_name,
                error_message=error_msg
            )
    
    def rebuild_index_incremental(
        self,
        session: Session,
        since: datetime,
        dimension: int = 64,
        index_name: str = "current"
    ) -> IndexMaintenanceResult:
        start_time = datetime.utcnow()
        
        try:
            logger.info(
                "Starting incremental index rebuild",
                extra={
                    "dimension": dimension,
                    "index_name": index_name,
                    "since": since.isoformat()
                }
            )
            
            if dimension == 64:
                items = session.exec(
                    select(MenuItem)
                    .where(MenuItem.reduced_embedding.is_not(None))
                ).all()
                embedding_field = "reduced_embedding"
            elif dimension == 1536:
                items = session.exec(
                    select(MenuItem)
                    .where(MenuItem.embedding.is_not(None))
                ).all()
                embedding_field = "embedding"
            else:
                raise ValueError(f"unsupported dimension: {dimension}")
            
            if not items:
                error_msg = f"no items found with {embedding_field}"
                logger.warning(error_msg, extra={"dimension": dimension})
                return IndexMaintenanceResult(
                    success=False,
                    items_indexed=0,
                    dimension=dimension,
                    build_duration_seconds=0.0,
                    index_name=index_name,
                    error_message=error_msg
                )
            
            embeddings = []
            item_ids = []
            
            for item in items:
                embedding = getattr(item, embedding_field)
                if embedding is not None:
                    embeddings.append(embedding)
                    item_ids.append(item.id)
            
            if not embeddings:
                error_msg = "no valid embeddings extracted"
                logger.error(error_msg)
                return IndexMaintenanceResult(
                    success=False,
                    items_indexed=0,
                    dimension=dimension,
                    build_duration_seconds=0.0,
                    index_name=index_name,
                    error_message=error_msg
                )
            
            self.faiss_service.build_index(
                embeddings=embeddings,
                item_ids=item_ids,
                dimension=dimension
            )
            
            self.faiss_service.save(index_name)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                "Incremental index rebuild completed successfully",
                extra={
                    "items_indexed": len(embeddings),
                    "dimension": dimension,
                    "duration_seconds": duration,
                    "index_name": index_name
                }
            )
            
            return IndexMaintenanceResult(
                success=True,
                items_indexed=len(embeddings),
                dimension=dimension,
                build_duration_seconds=duration,
                index_name=index_name
            )
            
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            error_msg = str(e)
            
            logger.error(
                "Incremental index rebuild failed",
                extra={
                    "dimension": dimension,
                    "index_name": index_name,
                    "since": since.isoformat(),
                    "error": error_msg
                },
                exc_info=True
            )
            
            return IndexMaintenanceResult(
                success=False,
                items_indexed=0,
                dimension=dimension,
                build_duration_seconds=duration,
                index_name=index_name,
                error_message=error_msg
            )
    
    def should_rebuild_index(
        self,
        index_name: str = "current",
        dimension: int = 64,
        max_age_hours: int = 24
    ) -> bool:
        try:
            metadata_path = Path(self.faiss_service._index_dir) / f"{index_name}_{dimension}d.json"
            
            if not metadata_path.exists():
                logger.info(
                    "Index should be rebuilt: metadata file not found",
                    extra={"index_name": index_name, "dimension": dimension}
                )
                return True
            
            import json
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
            
            build_timestamp_str = metadata.get("build_timestamp")
            if not build_timestamp_str:
                logger.warning(
                    "Index should be rebuilt: no build timestamp in metadata",
                    extra={"index_name": index_name, "dimension": dimension}
                )
                return True
            
            build_timestamp = datetime.fromisoformat(build_timestamp_str)
            age_hours = (datetime.utcnow() - build_timestamp).total_seconds() / 3600
            
            should_rebuild = age_hours > max_age_hours
            
            logger.info(
                "Index age check completed",
                extra={
                    "index_name": index_name,
                    "dimension": dimension,
                    "age_hours": age_hours,
                    "max_age_hours": max_age_hours,
                    "should_rebuild": should_rebuild
                }
            )
            
            return should_rebuild
            
        except Exception as e:
            logger.error(
                "Failed to check index age",
                extra={
                    "index_name": index_name,
                    "dimension": dimension,
                    "error": str(e)
                },
                exc_info=True
            )
            return True
