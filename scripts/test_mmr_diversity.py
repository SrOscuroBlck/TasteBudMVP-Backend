import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from sqlmodel import Session
from config.database import engine
from models import User, MenuItem
from services.mmr_service import MMRService, DiversityConstraints
from utils.logger import setup_logger

logger = setup_logger(__name__)


def test_mmr_diversity(
    diversity_weight: float = 0.3,
    max_items_per_cuisine: int = 2,
    top_k: int = 10
):
    logger.info("Testing MMR diversity algorithm")
    logger.info(f"Diversity weight: {diversity_weight}")
    logger.info(f"Max items per cuisine: {max_items_per_cuisine}")
    
    with Session(engine) as session:
        user = session.query(User).first()
        
        if not user:
            logger.error("No users found in database")
            return
        
        if not user.taste_vector:
            logger.error("User has no taste vector")
            return
        
        all_items = session.query(MenuItem).limit(100).all()
        
        if not all_items:
            logger.error("No menu items found")
            return
        
        logger.info(f"Testing with {len(all_items)} candidate items")
        
        mmr_service = MMRService()
        
        logger.info("\n" + "="*60)
        logger.info("Without diversity constraints")
        logger.info("="*60)
        
        selected_no_constraints = mmr_service.rerank_with_mmr(
            candidates=all_items,
            user_taste_vector=user.taste_vector,
            k=top_k,
            diversity_weight=diversity_weight
        )
        
        logger.info(f"Selected {len(selected_no_constraints)} items")
        
        cuisine_counts_no_constraints = {}
        for item in selected_no_constraints:
            logger.info(f"- {item.name} ({', '.join(item.cuisine)}) - ${item.price}")
            for cuisine in item.cuisine:
                cuisine_counts_no_constraints[cuisine] = cuisine_counts_no_constraints.get(cuisine, 0) + 1
        
        logger.info(f"\nCuisine distribution: {cuisine_counts_no_constraints}")
        diversity_score_no_constraints = mmr_service._compute_diversity_score(selected_no_constraints)
        logger.info(f"Diversity score: {diversity_score_no_constraints:.3f}")
        
        logger.info("\n" + "="*60)
        logger.info("With diversity constraints")
        logger.info("="*60)
        
        constraints = DiversityConstraints(
            max_items_per_cuisine=max_items_per_cuisine,
            max_items_per_restaurant=3
        )
        
        selected_with_constraints = mmr_service.rerank_with_mmr(
            candidates=all_items,
            user_taste_vector=user.taste_vector,
            k=top_k,
            diversity_weight=diversity_weight,
            constraints=constraints
        )
        
        logger.info(f"Selected {len(selected_with_constraints)} items")
        
        cuisine_counts_with_constraints = {}
        for item in selected_with_constraints:
            logger.info(f"- {item.name} ({', '.join(item.cuisine)}) - ${item.price}")
            for cuisine in item.cuisine:
                cuisine_counts_with_constraints[cuisine] = cuisine_counts_with_constraints.get(cuisine, 0) + 1
        
        logger.info(f"\nCuisine distribution: {cuisine_counts_with_constraints}")
        diversity_score_with_constraints = mmr_service._compute_diversity_score(selected_with_constraints)
        logger.info(f"Diversity score: {diversity_score_with_constraints:.3f}")
        
        logger.info("\n" + "="*60)
        logger.info("Comparison")
        logger.info("="*60)
        logger.info(f"Diversity improvement: {(diversity_score_with_constraints - diversity_score_no_constraints):.3f}")
        logger.info(f"Max cuisine count without constraints: {max(cuisine_counts_no_constraints.values())}")
        logger.info(f"Max cuisine count with constraints: {max(cuisine_counts_with_constraints.values())}")


def compare_diversity_weights():
    logger.info("\n" + "="*60)
    logger.info("Comparing different diversity weights")
    logger.info("="*60)
    
    with Session(engine) as session:
        user = session.query(User).first()
        
        if not user or not user.taste_vector:
            logger.error("Cannot run comparison: no user or taste vector")
            return
        
        all_items = session.query(MenuItem).limit(50).all()
        
        if not all_items:
            logger.error("No menu items found")
            return
        
        mmr_service = MMRService()
        
        weights_to_test = [0.0, 0.2, 0.3, 0.5, 0.7, 1.0]
        
        for weight in weights_to_test:
            selected = mmr_service.rerank_with_mmr(
                candidates=all_items,
                user_taste_vector=user.taste_vector,
                k=10,
                diversity_weight=weight
            )
            
            diversity_score = mmr_service._compute_diversity_score(selected)
            
            cuisine_counts = {}
            for item in selected:
                for cuisine in item.cuisine:
                    cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
            
            unique_cuisines = len(cuisine_counts)
            
            logger.info(f"\nDiversity weight: {weight:.1f}")
            logger.info(f"  Diversity score: {diversity_score:.3f}")
            logger.info(f"  Unique cuisines: {unique_cuisines}")
            logger.info(f"  Cuisine distribution: {dict(sorted(cuisine_counts.items(), key=lambda x: x[1], reverse=True))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test MMR diversity algorithm")
    parser.add_argument(
        "--diversity-weight",
        type=float,
        default=0.3,
        help="Diversity weight (0.0 = no diversity, 1.0 = max diversity)"
    )
    parser.add_argument(
        "--max-per-cuisine",
        type=int,
        default=2,
        help="Maximum items per cuisine"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of items to select"
    )
    parser.add_argument(
        "--compare-weights",
        action="store_true",
        help="Compare different diversity weights"
    )
    
    args = parser.parse_args()
    
    if args.compare_weights:
        compare_diversity_weights()
    else:
        test_mmr_diversity(
            diversity_weight=args.diversity_weight,
            max_items_per_cuisine=args.max_per_cuisine,
            top_k=args.top_k
        )
    
    logger.info("\nTest completed")
