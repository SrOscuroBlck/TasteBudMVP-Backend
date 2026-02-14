from typing import List, Tuple, Optional, Dict
from datetime import datetime
from uuid import UUID
import random
from scipy import stats
from sqlmodel import Session, select

from models import MenuItem, ABTestExperiment, InterleavingResult
from services.reranking_service import RankedItem
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TeamDraftInterleavingService:
    def __init__(self):
        pass
    
    def team_draft_interleave(
        self,
        algorithm_a_items: List[MenuItem],
        algorithm_b_items: List[MenuItem],
        k: int = 10
    ) -> Tuple[List[MenuItem], Dict[str, List[int]]]:
        if not algorithm_a_items:
            raise ValueError("algorithm_a_items cannot be empty")
        
        if not algorithm_b_items:
            raise ValueError("algorithm_b_items cannot be empty")
        
        interleaved = []
        assignments = {"A": [], "B": []}
        
        idx_a = 0
        idx_b = 0
        
        current_team = "A"
        
        while len(interleaved) < k:
            if current_team == "A":
                if idx_a < len(algorithm_a_items):
                    item = algorithm_a_items[idx_a]
                    
                    if item not in interleaved:
                        interleaved.append(item)
                        assignments["A"].append(len(interleaved) - 1)
                    
                    idx_a += 1
                
                current_team = "B"
            
            else:
                if idx_b < len(algorithm_b_items):
                    item = algorithm_b_items[idx_b]
                    
                    if item not in interleaved:
                        interleaved.append(item)
                        assignments["B"].append(len(interleaved) - 1)
                    
                    idx_b += 1
                
                current_team = "A"
            
            if idx_a >= len(algorithm_a_items) and idx_b >= len(algorithm_b_items):
                break
            
            if len(interleaved) >= k:
                break
        
        return interleaved, assignments
    
    def record_interleaving_result(
        self,
        session: Session,
        experiment_id: UUID,
        user_id: UUID,
        session_id: UUID,
        algorithm_a_items: List[MenuItem],
        algorithm_b_items: List[MenuItem],
        interleaved_items: List[MenuItem],
        clicked_item_ids: List[UUID],
        liked_item_ids: List[UUID],
        selected_item_ids: List[UUID]
    ) -> InterleavingResult:
        if not experiment_id:
            raise ValueError("experiment_id is required for interleaving result")
        
        if not user_id:
            raise ValueError("user_id is required for interleaving result")
        
        interleaved, assignments = self.team_draft_interleave(
            algorithm_a_items,
            algorithm_b_items,
            k=len(interleaved_items)
        )
        
        a_item_ids = {item.id for item in algorithm_a_items}
        b_item_ids = {item.id for item in algorithm_b_items}
        
        clicks_on_a = sum(1 for item_id in clicked_item_ids if item_id in a_item_ids)
        clicks_on_b = sum(1 for item_id in clicked_item_ids if item_id in b_item_ids)
        
        likes_on_a = sum(1 for item_id in liked_item_ids if item_id in a_item_ids)
        likes_on_b = sum(1 for item_id in liked_item_ids if item_id in b_item_ids)
        
        selections_on_a = sum(1 for item_id in selected_item_ids if item_id in a_item_ids)
        selections_on_b = sum(1 for item_id in selected_item_ids if item_id in b_item_ids)
        
        winner = None
        total_a = clicks_on_a + likes_on_a + selections_on_a
        total_b = clicks_on_b + likes_on_b + selections_on_b
        
        if total_a > total_b:
            winner = "A"
        elif total_b > total_a:
            winner = "B"
        else:
            winner = "tie"
        
        result = InterleavingResult(
            experiment_id=experiment_id,
            user_id=user_id,
            session_id=session_id,
            algorithm_a_items=[str(item.id) for item in algorithm_a_items],
            algorithm_b_items=[str(item.id) for item in algorithm_b_items],
            interleaved_items=[str(item.id) for item in interleaved_items],
            clicks_on_a=clicks_on_a,
            clicks_on_b=clicks_on_b,
            likes_on_a=likes_on_a,
            likes_on_b=likes_on_b,
            selections_on_a=selections_on_a,
            selections_on_b=selections_on_b,
            winner=winner
        )
        
        session.add(result)
        session.commit()
        session.refresh(result)
        
        logger.info(
            "Interleaving result recorded",
            extra={
                "experiment_id": str(experiment_id),
                "user_id": str(user_id),
                "winner": winner,
                "total_a": total_a,
                "total_b": total_b
            }
        )
        
        return result
    
    def analyze_experiment_results(
        self,
        session: Session,
        experiment_id: UUID,
        min_samples: int = 30
    ) -> Dict[str, any]:
        if not experiment_id:
            raise ValueError("experiment_id is required for analysis")
        
        results_stmt = (
            select(InterleavingResult)
            .where(InterleavingResult.experiment_id == experiment_id)
        )
        results = session.exec(results_stmt).all()
        
        if len(results) < min_samples:
            logger.warning(
                "Insufficient samples for statistical significance",
                extra={
                    "experiment_id": str(experiment_id),
                    "samples": len(results),
                    "min_required": min_samples
                }
            )
            return {
                "status": "insufficient_samples",
                "sample_count": len(results),
                "min_required": min_samples
            }
        
        wins_a = sum(1 for r in results if r.winner == "A")
        wins_b = sum(1 for r in results if r.winner == "B")
        ties = sum(1 for r in results if r.winner == "tie")
        
        total_clicks_a = sum(r.clicks_on_a for r in results)
        total_clicks_b = sum(r.clicks_on_b for r in results)
        
        total_likes_a = sum(r.likes_on_a for r in results)
        total_likes_b = sum(r.likes_on_b for r in results)
        
        total_selections_a = sum(r.selections_on_a for r in results)
        total_selections_b = sum(r.selections_on_b for r in results)
        
        chi2_stat, p_value = stats.chisquare([wins_a, wins_b])
        
        is_significant = p_value < 0.05
        
        if wins_a > wins_b:
            winner = "Algorithm A"
            win_rate_a = wins_a / len(results)
            win_rate_b = wins_b / len(results)
        elif wins_b > wins_a:
            winner = "Algorithm B"
            win_rate_a = wins_a / len(results)
            win_rate_b = wins_b / len(results)
        else:
            winner = "No clear winner"
            win_rate_a = wins_a / len(results)
            win_rate_b = wins_b / len(results)
        
        analysis = {
            "status": "complete",
            "sample_count": len(results),
            "winner": winner,
            "is_statistically_significant": is_significant,
            "p_value": p_value,
            "chi_square_statistic": chi2_stat,
            "algorithm_a": {
                "wins": wins_a,
                "win_rate": win_rate_a,
                "total_clicks": total_clicks_a,
                "total_likes": total_likes_a,
                "total_selections": total_selections_a
            },
            "algorithm_b": {
                "wins": wins_b,
                "win_rate": win_rate_b,
                "total_clicks": total_clicks_b,
                "total_likes": total_likes_b,
                "total_selections": total_selections_b
            },
            "ties": ties
        }
        
        experiment_stmt = select(ABTestExperiment).where(
            ABTestExperiment.id == experiment_id
        )
        experiment = session.exec(experiment_stmt).first()
        
        if experiment:
            experiment.results_summary = analysis
            session.add(experiment)
            session.commit()
        
        logger.info(
            "Experiment analysis completed",
            extra={
                "experiment_id": str(experiment_id),
                "winner": winner,
                "is_significant": is_significant,
                "p_value": p_value
            }
        )
        
        return analysis
    
    def create_experiment(
        self,
        session: Session,
        experiment_name: str,
        description: str,
        algorithm_a_name: str,
        algorithm_b_name: str
    ) -> ABTestExperiment:
        if not experiment_name:
            raise ValueError("experiment_name is required to create experiment")
        
        if not algorithm_a_name or not algorithm_b_name:
            raise ValueError("algorithm names are required to create experiment")
        
        experiment = ABTestExperiment(
            experiment_name=experiment_name,
            description=description,
            algorithm_a_name=algorithm_a_name,
            algorithm_b_name=algorithm_b_name,
            status="active"
        )
        
        session.add(experiment)
        session.commit()
        session.refresh(experiment)
        
        logger.info(
            "A/B test experiment created",
            extra={
                "experiment_id": str(experiment.id),
                "experiment_name": experiment_name,
                "algorithm_a": algorithm_a_name,
                "algorithm_b": algorithm_b_name
            }
        )
        
        return experiment
    
    def end_experiment(
        self,
        session: Session,
        experiment_id: UUID
    ) -> ABTestExperiment:
        if not experiment_id:
            raise ValueError("experiment_id is required to end experiment")
        
        experiment_stmt = select(ABTestExperiment).where(
            ABTestExperiment.id == experiment_id
        )
        experiment = session.exec(experiment_stmt).first()
        
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        experiment.status = "completed"
        experiment.end_date = datetime.utcnow()
        
        session.add(experiment)
        session.commit()
        session.refresh(experiment)
        
        logger.info(
            "Experiment ended",
            extra={
                "experiment_id": str(experiment_id),
                "experiment_name": experiment.experiment_name
            }
        )
        
        return experiment
