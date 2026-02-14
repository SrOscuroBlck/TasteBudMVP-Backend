import argparse
from datetime import datetime, timedelta
from typing import List, Tuple
from uuid import UUID
from sqlmodel import Session, select

from config.database import get_db
from models import User, MenuItem, OfflineEvaluation
from services.evaluation_metrics_service import EvaluationMetricsService
from services.recommendation_service import RecommendationService
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_offline_evaluation(
    evaluation_name: str,
    algorithm_name: str,
    temporal_split_days: int = 30,
    test_users_limit: int = 100,
    k: int = 10,
    dry_run: bool = False
):
    db_session = next(get_db())
    
    evaluation_service = EvaluationMetricsService()
    recommendation_service = RecommendationService()
    
    temporal_split_date = datetime.utcnow() - timedelta(days=temporal_split_days)
    
    logger.info(
        "Starting offline evaluation",
        extra={
            "evaluation_name": evaluation_name,
            "algorithm_name": algorithm_name,
            "temporal_split_date": temporal_split_date.isoformat(),
            "dry_run": dry_run
        }
    )
    
    users_stmt = select(User).limit(test_users_limit)
    users = db_session.exec(users_stmt).all()
    
    logger.info(f"Evaluating on {len(users)} users")
    
    test_recommendations: List[Tuple[UUID, List[MenuItem]]] = []
    
    for idx, user in enumerate(users):
        if idx % 10 == 0:
            logger.info(f"Processing user {idx + 1}/{len(users)}")
        
        try:
            result = recommendation_service.recommend(
                session=db_session,
                user=user,
                k=k,
                context=None
            )
            
            recommended_items = result["items"]
            test_recommendations.append((user.id, recommended_items))
            
        except Exception as e:
            logger.warning(
                "Failed to generate recommendations for user",
                extra={"user_id": str(user.id), "error": str(e)}
            )
            continue
    
    if dry_run:
        logger.info(
            "Dry run complete - would evaluate recommendations",
            extra={"recommendation_count": len(test_recommendations)}
        )
        return
    
    evaluation = evaluation_service.run_offline_evaluation(
        session=db_session,
        evaluation_name=evaluation_name,
        algorithm_name=algorithm_name,
        test_recommendations=test_recommendations,
        temporal_split_date=temporal_split_date
    )
    
    logger.info(
        "Offline evaluation complete",
        extra={
            "evaluation_id": str(evaluation.id),
            "ndcg_at_5": evaluation.ndcg_at_5,
            "ndcg_at_10": evaluation.ndcg_at_10,
            "ndcg_at_20": evaluation.ndcg_at_20,
            "diversity_score": evaluation.diversity_score,
            "coverage_score": evaluation.coverage_score
        }
    )
    
    print(f"\nEvaluation Results:")
    print(f"==================")
    print(f"Evaluation Name: {evaluation.evaluation_name}")
    print(f"Algorithm: {evaluation.algorithm_name}")
    print(f"Test Set Size: {evaluation.test_set_size}")
    print(f"\nMetrics:")
    print(f"  nDCG@5:  {evaluation.ndcg_at_5:.4f}" if evaluation.ndcg_at_5 else "  nDCG@5:  N/A")
    print(f"  nDCG@10: {evaluation.ndcg_at_10:.4f}" if evaluation.ndcg_at_10 else "  nDCG@10: N/A")
    print(f"  nDCG@20: {evaluation.ndcg_at_20:.4f}" if evaluation.ndcg_at_20 else "  nDCG@20: N/A")
    print(f"  Diversity: {evaluation.diversity_score:.4f}" if evaluation.diversity_score else "  Diversity: N/A")
    print(f"  Coverage:  {evaluation.coverage_score:.4f}" if evaluation.coverage_score else "  Coverage:  N/A")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run offline evaluation of recommendation algorithm"
    )
    parser.add_argument(
        "--evaluation-name",
        type=str,
        required=True,
        help="Name for this evaluation run"
    )
    parser.add_argument(
        "--algorithm-name",
        type=str,
        required=True,
        help="Name of the algorithm being evaluated"
    )
    parser.add_argument(
        "--temporal-split-days",
        type=int,
        default=30,
        help="Number of days for temporal split (default: 30)"
    )
    parser.add_argument(
        "--test-users",
        type=int,
        default=100,
        help="Maximum number of test users (default: 100)"
    )
    parser.add_argument(
        "--k",
        type=int,
        default=10,
        help="Number of recommendations per user (default: 10)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without saving results to database"
    )
    
    args = parser.parse_args()
    
    run_offline_evaluation(
        evaluation_name=args.evaluation_name,
        algorithm_name=args.algorithm_name,
        temporal_split_days=args.temporal_split_days,
        test_users_limit=args.test_users,
        k=args.k,
        dry_run=args.dry_run
    )
