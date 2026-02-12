from typing import List, Optional, Set
from uuid import UUID
from sqlmodel import Session, select
from datetime import datetime, timedelta

from models import MenuItem, User, Rating
from services.faiss_service import FAISSService
from services.features import has_allergen, violates_diet, cosine_similarity
from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RetrievalService:
    def __init__(self, faiss_service: Optional[FAISSService] = None):
        self.faiss_service = faiss_service or FAISSService()
        self._faiss_loaded = False
        
    def _ensure_faiss_loaded(self) -> bool:
        if self._faiss_loaded:
            return True
            
        try:
            if not self.faiss_service.is_loaded:
                dimension = getattr(settings, 'FAISS_DIMENSION', 64)
                self.faiss_service.load(index_name="current", dimension=dimension)
            self._faiss_loaded = True
            logger.info("FAISS index loaded successfully for retrieval")
            return True
        except (FileNotFoundError, ValueError) as e:
            logger.warning(
                "Failed to load FAISS index, will use SQL fallback",
                extra={"error": str(e)}
            )
            return False
    
    def retrieve_candidates(
        self,
        session: Session,
        user: User,
        k: int = 50,
        restaurant_id: Optional[str] = None,
        budget: Optional[float] = None,
        use_faiss: bool = True,
        exclude_recent_days: int = 2
    ) -> List[MenuItem]:
        if not user.taste_vector:
            raise ValueError("user taste_vector is required for retrieval")
        
        # Get recently interacted items to exclude
        recent_item_ids = self._get_recent_item_ids(session, user, days=exclude_recent_days)
        
        if use_faiss and self._ensure_faiss_loaded():
            return self._retrieve_with_faiss(
                session, user, k, restaurant_id, budget, recent_item_ids
            )
        else:
            return self._retrieve_with_sql(
                session, user, k, restaurant_id, budget, recent_item_ids
            )
    
    def _retrieve_with_faiss(
        self,
        session: Session,
        user: User,
        k: int,
        restaurant_id: Optional[str],
        budget: Optional[float],
        recent_item_ids: Set[UUID]
    ) -> List[MenuItem]:
        embedding_field = "reduced_embedding" if settings.FAISS_DIMENSION == 64 else "embedding"
        
        user_embedding = self._get_user_embedding(user, embedding_field)
        if not user_embedding:
            logger.warning(
                "User has no embedding, falling back to SQL",
                extra={"user_id": str(user.id)}
            )
            return self._retrieve_with_sql(session, user, k, restaurant_id, budget, recent_item_ids)
        
        # Inflate k to account for filtering
        k_inflated = k * 4  # Increased from 3 to account for recency filtering
        
        try:
            search_results = self.faiss_service.search(
                query_embedding=user_embedding,
                k=k_inflated
            )
        except Exception as e:
            logger.error(
                "FAISS search failed, falling back to SQL",
                extra={"error": str(e)},
                exc_info=True
            )
            return self._retrieve_with_sql(session, user, k, restaurant_id, budget, recent_item_ids)
        
        item_ids = [item_id for item_id, _ in search_results]
        
        query = select(MenuItem).where(MenuItem.id.in_(item_ids))
        if restaurant_id:
            query = query.where(MenuItem.restaurant_id == UUID(restaurant_id))
        
        items = list(session.exec(query).all())
        
        items_dict = {item.id: item for item in items}
        ordered_items = []
        for item_id, score in search_results:
            if item_id in items_dict:
                ordered_items.append(items_dict[item_id])
        
        # Apply recency filter
        filtered_by_recency = [
            item for item in ordered_items 
            if item.id not in recent_item_ids
        ]
        
        logger.info(
            "Applied recency filter",
            extra={
                "before_count": len(ordered_items),
                "after_count": len(filtered_by_recency),
                "filtered_count": len(ordered_items) - len(filtered_by_recency)
            }
        )
        
        filtered_items = self._apply_safety_filters(
            filtered_by_recency, user, budget
        )
        
        return filtered_items[:k]
    
    def _retrieve_with_sql(
        self,
        session: Session,
        user: User,
        k: int,
        restaurant_id: Optional[str],
        budget: Optional[float],
        recent_item_ids: Set[UUID]
    ) -> List[MenuItem]:
        query = select(MenuItem)
        if restaurant_id:
            query = query.where(MenuItem.restaurant_id == UUID(restaurant_id))
        
        all_items = list(session.exec(query).all())
        
        # Apply recency filter
        non_recent_items = [
            item for item in all_items
            if item.id not in recent_item_ids
        ]
        
        filtered_items = self._apply_safety_filters(
            non_recent_items, user, budget
        )
        
        scored_items = []
        for item in filtered_items:
            if not item.features:
                continue
            score = cosine_similarity(user.taste_vector, item.features)
            scored_items.append((item, score))
        
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        return [item for item, _ in scored_items[:k]]
    
    def _apply_safety_filters(
        self,
        items: List[MenuItem],
        user: User,
        budget: Optional[float]
    ) -> List[MenuItem]:
        user_allergies = set(map(str.lower, user.allergies))
        
        filtered = []
        for item in items:
            if user_allergies.intersection(set(map(str.lower, item.allergens))):
                continue
            
            if has_allergen(user.allergies, item.ingredients, item.allergens):
                continue
            
            if violates_diet(user.dietary_rules, item.dietary_tags):
                continue
            
            if budget is not None and item.price is not None and item.price > budget:
                continue
            
            filtered.append(item)
        
        return filtered
    
    def _get_user_embedding(
        self,
        user: User,
        embedding_field: str
    ) -> Optional[List[float]]:
        taste_axes = [
            "sweet", "sour", "salty", "bitter", "umami",
            "spicy", "fattiness", "acidity", "crunch", "temp_hot"
        ]
        
        embedding = [user.taste_vector.get(axis, 0.5) for axis in taste_axes]
        
        if embedding_field == "reduced_embedding" and len(embedding) < 64:
            embedding = embedding + [0.0] * (64 - len(embedding))
        elif embedding_field == "embedding" and len(embedding) < 1536:
            embedding = embedding + [0.0] * (1536 - len(embedding))
        
        return embedding
    
    def _get_recent_item_ids(
        self,
        session: Session,
        user: User,
        days: int = 2
    ) -> Set[UUID]:
        """Get item IDs that user interacted with in the last N days or permanently excluded."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        recent_ratings = session.exec(
            select(Rating.item_id)
            .where(Rating.user_id == user.id)
            .where(Rating.timestamp >= cutoff_date)
        ).all()
        
        from models.session import RecommendationFeedback, RecommendationSession
        
        disliked_feedback = session.exec(
            select(RecommendationFeedback.item_id)
            .where(RecommendationFeedback.session_id.in_(
                select(RecommendationSession.id)
                .where(RecommendationSession.user_id == user.id)
            ))
            .where(RecommendationFeedback.feedback_type == "dislike")
            .where(RecommendationFeedback.timestamp >= cutoff_date - timedelta(days=28))
        ).all()
        
        excluded = set(recent_ratings)
        excluded.update(disliked_feedback)
        
        for item_id_str in user.permanently_excluded_items:
            try:
                excluded.add(UUID(item_id_str))
            except (ValueError, AttributeError):
                continue
        
        logger.info(
            "Excluded items calculated",
            extra={
                "user_id": str(user.id),
                "from_ratings": len(recent_ratings),
                "from_feedback": len(disliked_feedback),
                "from_permanent": len(user.permanently_excluded_items),
                "total_excluded": len(excluded)
            }
        )
        
        return excluded
