import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session
from config.database import engine
from models import User
from services.recommendation_service import RecommendationService
from services.mmr_service import DiversityConstraints
from utils.logger import setup_logger

logger = setup_logger(__name__)


def test_query_based_recommendations():
    logger.info("Starting query-based recommendation tests")
    
    with Session(engine) as session:
        user = session.query(User).first()
        
        if not user:
            logger.error("No users found in database")
            return
        
        logger.info(f"Testing with user: {user.email}")
        
        recommendation_service = RecommendationService(
            use_new_pipeline=True,
            use_ml_reranking=False
        )
        
        test_queries = [
            "something spicy",
            "like pizza but spicier",
            "healthy vegetarian options",
            "italian food",
            "something rich and indulgent",
            "light and refreshing"
        ]
        
        for query in test_queries:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing query: {query}")
            logger.info(f"{'='*60}")
            
            try:
                result = recommendation_service.recommend_from_query(
                    session=session,
                    user=user,
                    query=query,
                    top_n=5,
                    diversity_weight=0.3,
                    use_cross_encoder=False
                )
                
                logger.info(f"Query info: {result.get('query_info', {})}")
                logger.info(f"Found {len(result['items'])} recommendations")
                
                if result.get('diversity_score'):
                    logger.info(f"Diversity score: {result['diversity_score']:.3f}")
                
                logger.info("\nRecommended items:")
                for idx, item in enumerate(result['items'], 1):
                    logger.info(
                        f"{idx}. {item['name']} - {item.get('cuisine', [])} - ${item.get('price', 0)}"
                    )
                
            except Exception as e:
                logger.error(f"Query failed: {str(e)}", exc_info=True)
        
        logger.info("\n" + "="*60)
        logger.info("Testing diversity constraints")
        logger.info("="*60)
        
        constraints = DiversityConstraints(
            max_items_per_cuisine=2,
            max_items_per_restaurant=3,
            max_items_in_price_range={"low": 2, "medium": 5, "high": 3}
        )
        
        try:
            result = recommendation_service.recommend_from_query(
                session=session,
                user=user,
                query="something delicious",
                top_n=10,
                diversity_weight=0.5,
                diversity_constraints=constraints
            )
            
            logger.info(f"Found {len(result['items'])} recommendations with constraints")
            
            cuisine_counts = {}
            for item in result['items']:
                for cuisine in item.get('cuisine', []):
                    cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
            
            logger.info(f"\nCuisine distribution: {cuisine_counts}")
            
            if result.get('diversity_score'):
                logger.info(f"Diversity score: {result['diversity_score']:.3f}")
            
        except Exception as e:
            logger.error(f"Constrained query failed: {str(e)}", exc_info=True)


def test_cross_encoder_benchmark():
    from services.cross_encoder_service import CrossEncoderService
    
    logger.info("\n" + "="*60)
    logger.info("Benchmarking cross-encoder latency")
    logger.info("="*60)
    
    cross_encoder = CrossEncoderService()
    
    if not cross_encoder.is_available:
        logger.warning("Cross-encoder not available, skipping benchmark")
        return
    
    for num_candidates in [10, 20, 30, 50]:
        latency = cross_encoder.benchmark_latency(num_candidates=num_candidates)
        if latency:
            logger.info(
                f"Latency for {num_candidates} candidates: {latency*1000:.2f}ms"
            )


def test_query_parsing():
    from services.query_service import QueryParsingService
    
    logger.info("\n" + "="*60)
    logger.info("Testing query parsing")
    logger.info("="*60)
    
    parser = QueryParsingService()
    
    test_queries = [
        "like tacos but spicier",
        "something italian",
        "vegetarian and healthy",
        "rich and creamy pasta",
        "light salad"
    ]
    
    for query in test_queries:
        parsed = parser.parse_query(query)
        logger.info(f"\nQuery: {query}")
        logger.info(f"Intent: {parsed.intent.value}")
        logger.info(f"Modifiers: {[m.value for m in parsed.modifiers]}")
        logger.info(f"Taste adjustments: {parsed.taste_adjustments}")
        logger.info(f"Cuisine filter: {parsed.cuisine_filter}")
        logger.info(f"Embedding text: {parsed.embedding_text}")


if __name__ == "__main__":
    test_query_parsing()
    test_query_based_recommendations()
    test_cross_encoder_benchmark()
    
    logger.info("\n" + "="*60)
    logger.info("All tests completed")
    logger.info("="*60)
