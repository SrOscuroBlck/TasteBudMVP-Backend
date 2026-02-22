from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from uuid import UUID
import math
from collections import defaultdict
from sqlmodel import Session, select
from sqlalchemy import func, desc

from models import (
    MenuItem,
    Rating,
    EvaluationMetric,
    OfflineEvaluation,
    OnlineEvaluationMetrics,
    UserItemInteractionHistory
)
from models.session import RecommendationFeedback, FeedbackType
from utils.logger import setup_logger

logger = setup_logger(__name__)


class EvaluationMetricsService:
    def __init__(self):
        pass
    
    def calculate_ndcg_at_k(
        self,
        recommended_items: List[MenuItem],
        ground_truth_likes: List[UUID],
        k: int
    ) -> float:
        if not recommended_items or not ground_truth_likes:
            return 0.0
        
        if k > len(recommended_items):
            k = len(recommended_items)
        
        dcg = 0.0
        for i, item in enumerate(recommended_items[:k]):
            if item.id in ground_truth_likes:
                relevance = 1.0
                position = i + 1
                dcg += relevance / math.log2(position + 1)
        
        idcg = 0.0
        num_relevant = min(len(ground_truth_likes), k)
        for i in range(num_relevant):
            position = i + 1
            idcg += 1.0 / math.log2(position + 1)
        
        if idcg == 0:
            return 0.0
        
        ndcg = dcg / idcg
        
        return ndcg
    
    def calculate_diversity_score(
        self,
        recommended_items: List[MenuItem]
    ) -> float:
        if len(recommended_items) < 2:
            return 1.0
        
        total_similarity = 0.0
        comparisons = 0
        
        for i in range(len(recommended_items)):
            for j in range(i + 1, len(recommended_items)):
                item_a = recommended_items[i]
                item_b = recommended_items[j]
                
                similarity = self._calculate_item_similarity(item_a, item_b)
                total_similarity += similarity
                comparisons += 1
        
        if comparisons == 0:
            return 1.0
        
        avg_similarity = total_similarity / comparisons
        
        diversity = 1.0 - avg_similarity
        
        return diversity
    
    def _calculate_item_similarity(
        self,
        item_a: MenuItem,
        item_b: MenuItem
    ) -> float:
        if not item_a.features or not item_b.features:
            return 0.0
        
        common_axes = set(item_a.features.keys()).intersection(
            set(item_b.features.keys())
        )
        
        if not common_axes:
            return 0.0
        
        dot_product = 0.0
        magnitude_a = 0.0
        magnitude_b = 0.0
        
        for axis in common_axes:
            val_a = item_a.features[axis]
            val_b = item_b.features[axis]
            
            dot_product += val_a * val_b
            magnitude_a += val_a ** 2
            magnitude_b += val_b ** 2
        
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        
        cosine_similarity = dot_product / (math.sqrt(magnitude_a) * math.sqrt(magnitude_b))
        
        return cosine_similarity
    
    def calculate_coverage_score(
        self,
        all_recommendations: List[List[MenuItem]],
        catalog: List[MenuItem]
    ) -> float:
        if not catalog:
            return 0.0
        
        recommended_item_ids = set()
        for rec_list in all_recommendations:
            for item in rec_list:
                recommended_item_ids.add(item.id)
        
        catalog_size = len(catalog)
        covered_items = len(recommended_item_ids)
        
        coverage = covered_items / catalog_size
        
        return coverage
    
    def calculate_like_ratio(
        self,
        session: Session,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[float, Dict[str, int]]:
        feedback_stmt = (
            select(RecommendationFeedback)
            .where(RecommendationFeedback.timestamp >= start_date)
            .where(RecommendationFeedback.timestamp <= end_date)
        )
        feedbacks = session.exec(feedback_stmt).all()
        
        feedbacks = [f for f in feedbacks if True]
        
        total_feedback = len(feedbacks)
        if total_feedback == 0:
            return 0.0, {
                "total_feedback": 0,
                "likes": 0,
                "dislikes": 0,
                "selections": 0
            }
        
        likes = sum(1 for f in feedbacks if f.feedback_type == FeedbackType.LIKE.value)
        dislikes = sum(1 for f in feedbacks if f.feedback_type == FeedbackType.DISLIKE.value)
        selections = sum(1 for f in feedbacks if f.feedback_type == FeedbackType.SELECTED.value)
        
        like_ratio = likes / total_feedback if total_feedback > 0 else 0.0
        
        counts = {
            "total_feedback": total_feedback,
            "likes": likes,
            "dislikes": dislikes,
            "selections": selections
        }
        
        return like_ratio, counts
    
    def calculate_time_to_decision(
        self,
        session: Session,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> Optional[float]:
        from models.session import RecommendationSession
        
        sessions_stmt = (
            select(RecommendationSession)
            .where(RecommendationSession.user_id == user_id)
            .where(RecommendationSession.created_at >= start_date)
            .where(RecommendationSession.created_at <= end_date)
        )
        sessions_list = session.exec(sessions_stmt).all()
        
        decision_times = []
        
        for rec_session in sessions_list:
            feedback_stmt = (
                select(RecommendationFeedback)
                .where(RecommendationFeedback.session_id == rec_session.id)
                .order_by(RecommendationFeedback.timestamp)
            )
            feedbacks = session.exec(feedback_stmt).all()
            
            if feedbacks:
                first_feedback = feedbacks[0]
                time_diff = (first_feedback.timestamp - rec_session.created_at).total_seconds()
                if time_diff > 0:
                    decision_times.append(time_diff)
        
        if not decision_times:
            return None
        
        avg_time = sum(decision_times) / len(decision_times)
        
        return avg_time
    
    def run_offline_evaluation(
        self,
        session: Session,
        evaluation_name: str,
        algorithm_name: str,
        test_recommendations: List[Tuple[UUID, List[MenuItem]]],
        temporal_split_date: Optional[datetime] = None
    ) -> OfflineEvaluation:
        if not test_recommendations:
            raise ValueError("test_recommendations cannot be empty for evaluation")
        
        ndcg_5_scores = []
        ndcg_10_scores = []
        ndcg_20_scores = []
        diversity_scores = []
        taste_similarities = []
        
        for user_id, recommended_items in test_recommendations:
            ground_truth_stmt = (
                select(Rating)
                .where(Rating.user_id == user_id)
                .where(Rating.liked == True)
            )
            if temporal_split_date:
                ground_truth_stmt = ground_truth_stmt.where(
                    Rating.timestamp >= temporal_split_date
                )
            
            ground_truth_ratings = session.exec(ground_truth_stmt).all()
            ground_truth_likes = [r.item_id for r in ground_truth_ratings]
            
            if ground_truth_likes:
                ndcg_5 = self.calculate_ndcg_at_k(recommended_items, ground_truth_likes, 5)
                ndcg_10 = self.calculate_ndcg_at_k(recommended_items, ground_truth_likes, 10)
                ndcg_20 = self.calculate_ndcg_at_k(recommended_items, ground_truth_likes, 20)
                
                ndcg_5_scores.append(ndcg_5)
                ndcg_10_scores.append(ndcg_10)
                ndcg_20_scores.append(ndcg_20)
            
            diversity = self.calculate_diversity_score(recommended_items[:10])
            diversity_scores.append(diversity)
        
        catalog_stmt = select(MenuItem)
        catalog = session.exec(catalog_stmt).all()
        coverage = self.calculate_coverage_score(
            [items for _, items in test_recommendations],
            catalog
        )
        
        evaluation = OfflineEvaluation(
            evaluation_name=evaluation_name,
            algorithm_name=algorithm_name,
            ndcg_at_5=sum(ndcg_5_scores) / len(ndcg_5_scores) if ndcg_5_scores else None,
            ndcg_at_10=sum(ndcg_10_scores) / len(ndcg_10_scores) if ndcg_10_scores else None,
            ndcg_at_20=sum(ndcg_20_scores) / len(ndcg_20_scores) if ndcg_20_scores else None,
            diversity_score=sum(diversity_scores) / len(diversity_scores) if diversity_scores else None,
            coverage_score=coverage,
            test_set_size=len(test_recommendations),
            train_set_size=0,
            temporal_split_date=temporal_split_date
        )
        
        session.add(evaluation)
        session.commit()
        session.refresh(evaluation)
        
        logger.info(
            "Offline evaluation completed",
            extra={
                "evaluation_name": evaluation_name,
                "algorithm_name": algorithm_name,
                "ndcg_at_10": evaluation.ndcg_at_10,
                "diversity_score": evaluation.diversity_score,
                "coverage_score": evaluation.coverage_score
            }
        )
        
        return evaluation
    
    def compute_online_metrics(
        self,
        session: Session,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> OnlineEvaluationMetrics:
        interaction_stmt = (
            select(UserItemInteractionHistory)
            .where(UserItemInteractionHistory.user_id == user_id)
            .where(UserItemInteractionHistory.last_shown_at >= start_date)
            .where(UserItemInteractionHistory.last_shown_at <= end_date)
        )
        interactions = session.exec(interaction_stmt).all()
        
        total_shown = len(interactions)
        total_likes = sum(1 for i in interactions if i.was_liked)
        total_dislikes = sum(1 for i in interactions if i.was_disliked)
        total_selections = sum(1 for i in interactions if i.was_ordered)
        total_dismissals = sum(1 for i in interactions if i.was_dismissed)
        
        like_ratio = total_likes / total_shown if total_shown > 0 else None
        selection_ratio = total_selections / total_shown if total_shown > 0 else None
        
        engaged = total_likes + total_dislikes + total_selections
        engagement_ratio = engaged / total_shown if total_shown > 0 else None
        
        avg_time_to_decision = self.calculate_time_to_decision(
            session, user_id, start_date, end_date
        )
        
        metrics = OnlineEvaluationMetrics(
            user_id=user_id,
            time_period_start=start_date,
            time_period_end=end_date,
            total_recommendations_shown=total_shown,
            total_likes=total_likes,
            total_dislikes=total_dislikes,
            total_selections=total_selections,
            total_dismissals=total_dismissals,
            like_ratio=like_ratio,
            selection_ratio=selection_ratio,
            engagement_ratio=engagement_ratio,
            avg_time_to_decision_seconds=avg_time_to_decision
        )
        
        session.add(metrics)
        session.commit()
        session.refresh(metrics)
        
        logger.info(
            "Online metrics computed",
            extra={
                "user_id": str(user_id),
                "like_ratio": like_ratio,
                "selection_ratio": selection_ratio,
                "engagement_ratio": engagement_ratio
            }
        )
        
        return metrics
