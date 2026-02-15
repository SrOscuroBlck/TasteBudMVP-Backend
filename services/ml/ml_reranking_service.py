"""ML-based reranking service using LightGBM.

This service extracts comprehensive features from user-item-context triples
and uses a trained gradient boosting model to predict user preference scores.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from uuid import UUID
import numpy as np
from sqlmodel import Session, select, func

from models import MenuItem, User, Rating, PopulationStats
from services.features.features import cosine_similarity
from services.core.reranking_service import RankedItem, RecommendationContext
from utils.logger import setup_logger

logger = setup_logger(__name__)


class MLRerankingService:
    """ML-based reranking using gradient boosting."""
    
    def __init__(self, population_stats: Optional[PopulationStats] = None):
        self.population_stats = population_stats
        self.model = None
        self._try_load_model()
    
    def _try_load_model(self):
        """Try to load trained model, fall back to None if not available."""
        try:
            import lightgbm as lgb
            import os
            
            model_path = "data/models/reranker.txt"
            if os.path.exists(model_path):
                self.model = lgb.Booster(model_file=model_path)
                logger.info("ML reranking model loaded successfully")
            else:
                logger.info("No trained model found, will use rule-based reranking")
        except ImportError:
            logger.info("lightgbm not installed, using rule-based reranking")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}, using rule-based reranking")
    
    def rerank(
        self,
        candidates: List[MenuItem],
        user: User,
        context: RecommendationContext,
        session: Session,
        top_n: int = 10
    ) -> List[RankedItem]:
        """Rerank candidates using ML model if available, otherwise fall back to rules."""
        
        if self.model is None:
            logger.info("Using rule-based reranking (no ML model available)")
            return self._rerank_with_rules(candidates, user, context, top_n)
        
        try:
            return self._rerank_with_ml(candidates, user, context, session, top_n)
        except Exception as e:
            logger.error(f"ML reranking failed: {e}, falling back to rules", exc_info=True)
            return self._rerank_with_rules(candidates, user, context, top_n)
    
    def _rerank_with_ml(
        self,
        candidates: List[MenuItem],
        user: User,
        context: RecommendationContext,
        session: Session,
        top_n: int
    ) -> List[RankedItem]:
        """Rerank using trained ML model."""
        
        # Extract features for all candidates
        features_list = []
        for item in candidates:
            features = self._extract_features(item, user, context, session)
            features_list.append(features)
        
        # Convert to numpy array
        feature_matrix = np.array([list(f.values()) for f in features_list])
        
        # Predict scores
        scores = self.model.predict(feature_matrix)
        
        # Create ranked items
        ranked_items = []
        for item, score, features in zip(candidates, scores, features_list):
            ranked_items.append(RankedItem(
                item=item,
                base_score=features["taste_similarity"],
                contextual_score=float(score),
                confidence=0.9,  # High confidence with ML
                ranking_factors=features
            ))
        
        # Sort by predicted score
        ranked_items.sort(key=lambda x: x.contextual_score, reverse=True)
        
        return ranked_items[:top_n]
    
    def _rerank_with_rules(
        self,
        candidates: List[MenuItem],
        user: User,
        context: RecommendationContext,
        top_n: int
    ) -> List[RankedItem]:
        """Fallback to rule-based reranking."""
        from services.core.reranking_service import RerankingService
        
        rules_service = RerankingService(self.population_stats)
        return rules_service.rerank(candidates, user, context, top_n)
    
    def _extract_features(
        self,
        item: MenuItem,
        user: User,
        context: RecommendationContext,
        session: Session
    ) -> Dict[str, float]:
        """Extract comprehensive features for ML model."""
        
        features = {}
        
        # === Vector Similarity Features ===
        if item.features and user.taste_vector:
            features["taste_similarity"] = cosine_similarity(user.taste_vector, item.features)
        else:
            features["taste_similarity"] = 0.0
        
        # === Temporal Features ===
        features["hour_of_day"] = context.current_hour / 24.0  # Normalize to [0, 1]
        features["day_of_week"] = context.day_of_week / 7.0
        features["is_weekend"] = 1.0 if context.day_of_week >= 5 else 0.0
        
        # === Time-Course Match ===
        features["breakfast_time_match"] = self._breakfast_match(item, context.current_hour)
        features["lunch_time_match"] = self._lunch_match(item, context.current_hour)
        features["dinner_time_match"] = self._dinner_match(item, context.current_hour)
        
        # === Item Popularity ===
        if self.population_stats:
            pop_global = self.population_stats.item_popularity_global or {}
            pop_rest = self.population_stats.item_popularity_by_restaurant or {}
            features["global_popularity"] = pop_global.get(str(item.id), 0.0)
            features["restaurant_popularity"] = pop_rest.get(str(item.restaurant_id), 0.0)
        else:
            features["global_popularity"] = 0.0
            features["restaurant_popularity"] = 0.0
        
        # === User-Item History ===
        user_history = self._get_user_item_history(session, user, item)
        features["days_since_last_ordered"] = user_history["days_since_last"]
        features["times_ordered_before"] = user_history["order_count"]
        features["avg_rating"] = user_history["avg_rating"]
        
        # === Price Features ===
        if item.price:
            user_avg_price = self._get_user_avg_price(session, user)
            features["price"] = item.price / 100.0  # Normalize
            features["price_vs_user_avg"] = (item.price / max(user_avg_price, 1.0))
            features["price_deviation"] = abs(item.price - user_avg_price) / max(user_avg_price, 1.0)
            
            if context.budget:
                features["within_budget"] = 1.0 if item.price <= context.budget else 0.0
                features["price_vs_budget"] = item.price / context.budget
            else:
                features["within_budget"] = 1.0
                features["price_vs_budget"] = features["price_vs_user_avg"]
        else:
            features["price"] = 0.5
            features["price_vs_user_avg"] = 1.0
            features["price_deviation"] = 0.0
            features["within_budget"] = 1.0
            features["price_vs_budget"] = 1.0
        
        # === Course Features ===
        course_encoding = self._encode_course(item.course)
        features.update(course_encoding)
        
        # === Context Features ===
        if context.course_preference:
            features["course_match"] = 1.0 if item.course == context.course_preference else 0.0
        else:
            features["course_match"] = 0.5
        
        # === Cuisine Affinity ===
        if item.cuisine and user.cuisine_affinity:
            cuisine_scores = [user.cuisine_affinity.get(c, 0.0) for c in item.cuisine]
            features["cuisine_affinity"] = max(cuisine_scores) if cuisine_scores else 0.0
        else:
            features["cuisine_affinity"] = 0.0
        
        # === Ingredient Preferences ===
        features["has_liked_ingredients"] = self._has_liked_ingredients(item, user)
        features["has_disliked_ingredients"] = self._has_disliked_ingredients(item, user)
        
        # === Dietary/Allergen Compatibility ===
        features["violates_dietary_rules"] = 0.0  # Already filtered in retrieval
        features["contains_allergens"] = 0.0  # Already filtered in retrieval
        
        # === Provenance/Quality ===
        features["inference_confidence"] = item.inference_confidence or 0.5
        features["is_ingested"] = 1.0 if item.provenance.get("source") == "pdf_upload" else 0.0
        
        return features
    
    def _breakfast_match(self, item: MenuItem, hour: int) -> float:
        """Check if item matches breakfast time (6am-11am)."""
        if not item.course:
            return 0.0
        is_breakfast_item = item.course.lower() in ["breakfast", "brunch"]
        is_breakfast_time = 6 <= hour < 11
        return 1.0 if (is_breakfast_item and is_breakfast_time) else 0.0
    
    def _lunch_match(self, item: MenuItem, hour: int) -> float:
        """Check if item matches lunch time (11am-3pm)."""
        if not item.course:
            return 0.0
        is_lunch_item = item.course.lower() in ["lunch", "appetizer", "main", "starter"]
        is_lunch_time = 11 <= hour < 15
        return 1.0 if (is_lunch_item and is_lunch_time) else 0.0
    
    def _dinner_match(self, item: MenuItem, hour: int) -> float:
        """Check if item matches dinner time (5pm-10pm)."""
        if not item.course:
            return 0.0
        is_dinner_item = item.course.lower() in ["dinner", "main", "entree"]
        is_dinner_time = 17 <= hour < 22
        return 1.0 if (is_dinner_item and is_dinner_time) else 0.0
    
    def _encode_course(self, course: Optional[str]) -> Dict[str, float]:
        """One-hot encode course categories."""
        courses = ["breakfast", "lunch", "dinner", "appetizer", "main", "dessert", "beverage", "side"]
        encoding = {f"course_{c}": 0.0 for c in courses}
        
        if course:
            course_lower = course.lower()
            for c in courses:
                if c in course_lower:
                    encoding[f"course_{c}"] = 1.0
                    break
        
        return encoding
    
    def _get_user_item_history(
        self,
        session: Session,
        user: User,
        item: MenuItem
    ) -> Dict[str, float]:
        """Get user's history with this specific item."""
        
        ratings = session.exec(
            select(Rating)
            .where(Rating.user_id == user.id)
            .where(Rating.item_id == item.id)
            .order_by(Rating.timestamp.desc())
        ).all()
        
        if not ratings:
            return {
                "days_since_last": 999.0,  # Never ordered
                "order_count": 0.0,
                "avg_rating": 0.5
            }
        
        last_rating = ratings[0]
        days_since = (datetime.utcnow() - last_rating.timestamp).days
        
        avg_rating = sum(r.rating for r in ratings) / len(ratings) / 5.0  # Normalize to [0, 1]
        
        return {
            "days_since_last": min(days_since / 365.0, 1.0),  # Normalize to [0, 1]
            "order_count": min(len(ratings) / 10.0, 1.0),  # Cap at 10
            "avg_rating": avg_rating
        }
    
    def _get_user_avg_price(self, session: Session, user: User) -> float:
        """Get user's average order price."""
        
        result = session.exec(
            select(func.avg(MenuItem.price))
            .join(Rating, Rating.item_id == MenuItem.id)
            .where(Rating.user_id == user.id)
            .where(MenuItem.price.isnot(None))
        ).first()
        
        return float(result) if result else 30000.0  # Default to 30k COP
    
    def _has_liked_ingredients(self, item: MenuItem, user: User) -> float:
        """Check if item contains user's liked ingredients."""
        if not user.liked_ingredients or not item.ingredients:
            return 0.0
        
        liked_set = set(ing.lower() for ing in user.liked_ingredients)
        item_set = set(ing.lower() for ing in item.ingredients)
        
        overlap = len(liked_set.intersection(item_set))
        return min(overlap / max(len(liked_set), 1.0), 1.0)
    
    def _has_disliked_ingredients(self, item: MenuItem, user: User) -> float:
        """Check if item contains user's disliked ingredients."""
        if not user.disliked_ingredients or not item.ingredients:
            return 0.0
        
        disliked_set = set(ing.lower() for ing in user.disliked_ingredients)
        item_set = set(ing.lower() for ing in item.ingredients)
        
        overlap = len(disliked_set.intersection(item_set))
        return min(overlap / max(len(disliked_set), 1.0), 1.0)
