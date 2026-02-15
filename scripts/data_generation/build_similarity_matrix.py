from sqlmodel import Session, select
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.database import engine
from models import MenuItem
from services.infrastructure.similarity_matrix_service import SimilarityMatrixService
from utils.logger import setup_logger
from config.settings import settings

logger = setup_logger(__name__)


def build_similarity_matrix(output_path: Optional[str] = None):
    logger.info("="* 60)
    logger.info("SIMILARITY MATRIX BUILDER")
    logger.info("="* 60)
    
    with Session(engine) as db_session:
        logger.info("Fetching all menu items from database...")
        
        statement = select(MenuItem).where(MenuItem.features.isnot(None))
        items = db_session.exec(statement).all()
        
        if not items:
            logger.error("No items with features found in database")
            return
        
        logger.info(f"Found {len(items)} items with features")
        
        service = SimilarityMatrixService()
        
        logger.info("Building similarity matrix...")
        service.build_matrix(items)
        
        if output_path is None:
            output_path = settings.FAISS_INDEX_PATH + "similarity_matrix.pkl"
        
        logger.info(f"Saving matrix to {output_path}...")
        service.save_to_disk(output_path)
        
        logger.info("="* 60)
        logger.info("MATRIX BUILD COMPLETE")
        logger.info("="* 60)
        
        logger.info(f"Sample lookups:")
        if len(items) >= 2:
            item1, item2 = items[0], items[1]
            similarity = service.get_similarity(item1.id, item2.id)
            logger.info(
                f"Similarity between '{item1.name}' and '{item2.name}': {round(similarity, 3)}"
            )
            
            top_similar = service.get_top_similar(item1.id, top_k=5)
            logger.info(f"Top 5 similar items to '{item1.name}':")
            for similar_id, sim_score in top_similar:
                similar_item = db_session.get(MenuItem, similar_id)
                if similar_item:
                    logger.info(f"  - {similar_item.name}: {round(sim_score, 3)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Build taste similarity matrix for menu items"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for similarity matrix (default: data/faiss_indexes/similarity_matrix.pkl)"
    )
    
    args = parser.parse_args()
    
    build_similarity_matrix(output_path=args.output)
