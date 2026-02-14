import argparse
from uuid import UUID
from sqlmodel import select

from config.database import get_db
from models import ABTestExperiment
from services.team_draft_interleaving_service import TeamDraftInterleavingService
from utils.logger import setup_logger

logger = setup_logger(__name__)


def analyze_ab_test(
    experiment_name: str = None,
    experiment_id: str = None,
    min_samples: int = 30
):
    if not experiment_name and not experiment_id:
        raise ValueError("Either experiment_name or experiment_id must be provided")
    
    db_session = next(get_db())
    interleaving_service = TeamDraftInterleavingService()
    
    if experiment_id:
        exp_uuid = UUID(experiment_id)
        experiment_stmt = select(ABTestExperiment).where(
            ABTestExperiment.id == exp_uuid
        )
    else:
        experiment_stmt = select(ABTestExperiment).where(
            ABTestExperiment.experiment_name == experiment_name
        )
    
    experiment = db_session.exec(experiment_stmt).first()
    
    if not experiment:
        logger.error("Experiment not found")
        print(f"Error: Experiment not found")
        return
    
    logger.info(
        "Analyzing A/B test experiment",
        extra={
            "experiment_id": str(experiment.id),
            "experiment_name": experiment.experiment_name
        }
    )
    
    analysis = interleaving_service.analyze_experiment_results(
        session=db_session,
        experiment_id=experiment.id,
        min_samples=min_samples
    )
    
    print(f"\nA/B Test Analysis Results")
    print(f"=========================")
    print(f"Experiment: {experiment.experiment_name}")
    print(f"Description: {experiment.description}")
    print(f"Algorithm A: {experiment.algorithm_a_name}")
    print(f"Algorithm B: {experiment.algorithm_b_name}")
    print(f"Status: {experiment.status}")
    print(f"\nAnalysis:")
    print(f"---------")
    
    if analysis["status"] == "insufficient_samples":
        print(f"Status: Insufficient samples")
        print(f"Samples collected: {analysis['sample_count']}")
        print(f"Required: {analysis['min_required']}")
        print(f"\nNeed {analysis['min_required'] - analysis['sample_count']} more samples for statistical significance")
    else:
        print(f"Sample Count: {analysis['sample_count']}")
        print(f"Winner: {analysis['winner']}")
        print(f"Statistically Significant: {'Yes' if analysis['is_statistically_significant'] else 'No'}")
        print(f"P-Value: {analysis['p_value']:.6f}")
        print(f"Chi-Square Statistic: {analysis['chi_square_statistic']:.4f}")
        
        print(f"\nAlgorithm A ({experiment.algorithm_a_name}):")
        print(f"  Wins: {analysis['algorithm_a']['wins']}")
        print(f"  Win Rate: {analysis['algorithm_a']['win_rate']:.4f}")
        print(f"  Total Clicks: {analysis['algorithm_a']['total_clicks']}")
        print(f"  Total Likes: {analysis['algorithm_a']['total_likes']}")
        print(f"  Total Selections: {analysis['algorithm_a']['total_selections']}")
        
        print(f"\nAlgorithm B ({experiment.algorithm_b_name}):")
        print(f"  Wins: {analysis['algorithm_b']['wins']}")
        print(f"  Win Rate: {analysis['algorithm_b']['win_rate']:.4f}")
        print(f"  Total Clicks: {analysis['algorithm_b']['total_clicks']}")
        print(f"  Total Likes: {analysis['algorithm_b']['total_likes']}")
        print(f"  Total Selections: {analysis['algorithm_b']['total_selections']}")
        
        print(f"\nTies: {analysis['ties']}")
        
        if analysis['is_statistically_significant']:
            print(f"\n✓ Results are statistically significant (p < 0.05)")
            print(f"  Recommendation: Deploy {analysis['winner']}")
        else:
            print(f"\n✗ Results are NOT statistically significant (p >= 0.05)")
            print(f"  Recommendation: Continue experiment or try alternative algorithms")


def list_experiments():
    db_session = next(get_db())
    
    experiments_stmt = select(ABTestExperiment)
    experiments = db_session.exec(experiments_stmt).all()
    
    if not experiments:
        print("No experiments found")
        return
    
    print(f"\nA/B Test Experiments")
    print(f"====================")
    
    for exp in experiments:
        print(f"\nID: {exp.id}")
        print(f"Name: {exp.experiment_name}")
        print(f"Description: {exp.description}")
        print(f"Algorithm A: {exp.algorithm_a_name}")
        print(f"Algorithm B: {exp.algorithm_b_name}")
        print(f"Status: {exp.status}")
        print(f"Started: {exp.start_date}")
        if exp.end_date:
            print(f"Ended: {exp.end_date}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze A/B test experiment results"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    analyze_parser = subparsers.add_parser("analyze", help="Analyze experiment results")
    analyze_parser.add_argument(
        "--experiment-name",
        type=str,
        help="Name of the experiment to analyze"
    )
    analyze_parser.add_argument(
        "--experiment-id",
        type=str,
        help="ID of the experiment to analyze"
    )
    analyze_parser.add_argument(
        "--min-samples",
        type=int,
        default=30,
        help="Minimum samples required for statistical significance (default: 30)"
    )
    
    list_parser = subparsers.add_parser("list", help="List all experiments")
    
    args = parser.parse_args()
    
    if args.command == "analyze":
        analyze_ab_test(
            experiment_name=args.experiment_name,
            experiment_id=args.experiment_id,
            min_samples=args.min_samples
        )
    elif args.command == "list":
        list_experiments()
    else:
        parser.print_help()
