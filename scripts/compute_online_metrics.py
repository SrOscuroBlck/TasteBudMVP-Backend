import argparse
from datetime import datetime, timedelta
from sqlmodel import select

from config.database import get_db
from models import User, OnlineEvaluationMetrics
from services.evaluation_metrics_service import EvaluationMetricsService
from utils.logger import setup_logger

logger = setup_logger(__name__)


def compute_online_metrics(
    time_period_days: int = 30,
    user_limit: int = 100,
    dry_run: bool = False
):
    db_session = next(get_db())
    
    evaluation_service = EvaluationMetricsService()
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=time_period_days)
    
    logger.info(
        "Computing online metrics",
        extra={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "dry_run": dry_run
        }
    )
    
    users_stmt = select(User).limit(user_limit)
    users = db_session.exec(users_stmt).all()
    
    logger.info(f"Computing metrics for {len(users)} users")
    
    results = []
    
    for idx, user in enumerate(users):
        if idx % 10 == 0:
            logger.info(f"Processing user {idx + 1}/{len(users)}")
        
        try:
            if dry_run:
                like_ratio, counts = evaluation_service.calculate_like_ratio(
                    db_session, user.id, start_date, end_date
                )
                
                results.append({
                    "user_id": str(user.id),
                    "like_ratio": like_ratio,
                    "total_feedback": counts["total_feedback"],
                    "likes": counts["likes"],
                    "dislikes": counts["dislikes"]
                })
            else:
                metrics = evaluation_service.compute_online_metrics(
                    session=db_session,
                    user_id=user.id,
                    start_date=start_date,
                    end_date=end_date
                )
                
                results.append({
                    "user_id": str(user.id),
                    "like_ratio": metrics.like_ratio,
                    "selection_ratio": metrics.selection_ratio,
                    "engagement_ratio": metrics.engagement_ratio,
                    "avg_time_to_decision": metrics.avg_time_to_decision_seconds
                })
        
        except Exception as e:
            logger.warning(
                "Failed to compute metrics for user",
                extra={"user_id": str(user.id), "error": str(e)}
            )
            continue
    
    if results:
        avg_like_ratio = sum(r["like_ratio"] for r in results if r["like_ratio"]) / len([r for r in results if r["like_ratio"]])
        
        print(f"\nOnline Metrics Summary:")
        print(f"======================")
        print(f"Time Period: {start_date.date()} to {end_date.date()}")
        print(f"Users Analyzed: {len(results)}")
        print(f"Average Like Ratio: {avg_like_ratio:.4f}")
        
        if not dry_run and results and "selection_ratio" in results[0]:
            avg_selection_ratio = sum(r["selection_ratio"] for r in results if r["selection_ratio"]) / len([r for r in results if r["selection_ratio"]])
            avg_engagement_ratio = sum(r["engagement_ratio"] for r in results if r["engagement_ratio"]) / len([r for r in results if r["engagement_ratio"]])
            
            print(f"Average Selection Ratio: {avg_selection_ratio:.4f}")
            print(f"Average Engagement Ratio: {avg_engagement_ratio:.4f}")
            
            decision_times = [r["avg_time_to_decision"] for r in results if r["avg_time_to_decision"]]
            if decision_times:
                avg_decision_time = sum(decision_times) / len(decision_times)
                print(f"Average Time to Decision: {avg_decision_time:.2f} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute online evaluation metrics for users"
    )
    parser.add_argument(
        "--time-period-days",
        type=int,
        default=30,
        help="Time period in days to analyze (default: 30)"
    )
    parser.add_argument(
        "--user-limit",
        type=int,
        default=100,
        help="Maximum number of users to analyze (default: 100)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without saving results to database"
    )
    
    args = parser.parse_args()
    
    compute_online_metrics(
        time_period_days=args.time_period_days,
        user_limit=args.user_limit,
        dry_run=args.dry_run
    )
