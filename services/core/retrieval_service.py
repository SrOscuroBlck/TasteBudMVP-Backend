from typing import List, Optional, Set, Dict
from uuid import UUID
from sqlmodel import Session, select
from datetime import datetime, timedelta

from models import MenuItem, User, Rating
from models.query import ParsedQuery
from services.features.faiss_service import FAISSService
from services.features.embedding_service import EmbeddingService
from services.features.features import has_allergen, violates_diet, cosine_similarity
from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RetrievalService:
    def __init__(self, faiss_service: Optional[FAISSService] = None):
        self.faiss_service = faiss_service or FAISSService()
        self.embedding_service = EmbeddingService()
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
        exclude_recent_days: int = 2,
        course_filter: Optional[str] = None,
        time_of_day: Optional[str] = None
    ) -> List[MenuItem]:
        if not user.taste_vector:
            raise ValueError("user taste_vector is required for retrieval")
        
        recent_item_ids = self._get_recent_item_ids(session, user, days=exclude_recent_days)
        
        if use_faiss and self._ensure_faiss_loaded():
            return self._retrieve_with_faiss(
                session, user, k, restaurant_id, budget, recent_item_ids,
                course_filter, time_of_day
            )
        else:
            return self._retrieve_with_sql(
                session, user, k, restaurant_id, budget, recent_item_ids,
                course_filter, time_of_day
            )
    
    def _retrieve_with_faiss(
        self,
        session: Session,
        user: User,
        k: int,
        restaurant_id: Optional[str],
        budget: Optional[float],
        recent_item_ids: Set[UUID],
        course_filter: Optional[str] = None,
        time_of_day: Optional[str] = None
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
        
        course_filtered = self._apply_course_filter(
            filtered_items, course_filter, time_of_day
        )
        
        return course_filtered[:k]
    
    def _retrieve_with_sql(
        self,
        session: Session,
        user: User,
        k: int,
        restaurant_id: Optional[str],
        budget: Optional[float],
        recent_item_ids: Set[UUID],
        course_filter: Optional[str] = None,
        time_of_day: Optional[str] = None
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
        
        course_filtered = self._apply_course_filter(
            filtered_items, course_filter, time_of_day
        )
        
        scored_items = []
        for item in course_filtered:
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
    
    def _apply_course_filter(
        self,
        items: List[MenuItem],
        course_filter: Optional[str],
        time_of_day: Optional[str]
    ) -> List[MenuItem]:
        if not course_filter:
            return items
        
        course_filter_lower = course_filter.lower()
        
        course_type_mapping = {
            "appetizer": ["appetizer", "starter", "soup", "salad"],
            "main": ["main", "entree", "dinner", "lunch"],
            "main_course": ["main", "entree", "dinner", "lunch"],
            "dessert": ["dessert", "sweet"],
            "beverage": ["beverage", "drink"],
            "snack": ["snack", "appetizer", "starter", "small plate"],
            "full_meal": []
        }
        
        if course_filter_lower == "full_meal":
            return items
        
        allowed_courses = course_type_mapping.get(course_filter_lower, [])
        
        if not allowed_courses:
            return items
        
        filtered = []
        for item in items:
            if not item.course:
                if course_filter_lower in ["snack", "appetizer"]:
                    filtered.append(item)
                continue
            
            item_course_lower = item.course.lower()
            
            for allowed_course in allowed_courses:
                if allowed_course in item_course_lower:
                    filtered.append(item)
                    break
        
        if time_of_day:
            filtered = self._apply_time_based_filter(filtered, time_of_day)
        
        if not filtered:
            logger.warning(
                "Course filter resulted in zero items, returning unfiltered",
                extra={
                    "course_filter": course_filter,
                    "original_count": len(items),
                    "filtered_count": 0
                }
            )
            return items
        
        return filtered
    
    def _apply_time_based_filter(
        self,
        items: List[MenuItem],
        time_of_day: str
    ) -> List[MenuItem]:
        hour = datetime.now().hour
        
        if 5 <= hour < 11:
            breakfast_keywords = ["breakfast", "brunch", "morning"]
            return [
                item for item in items
                if not item.course or any(kw in item.course.lower() for kw in breakfast_keywords)
                or item.course.lower() in ["appetizer", "beverage", "snack"]
            ]
        
        elif 11 <= hour < 18:
            lunch_keywords = ["lunch", "dinner", "main", "entree"]
            return [
                item for item in items
                if not item.course or any(kw in item.course.lower() for kw in lunch_keywords)
                or item.course.lower() in ["appetizer", "dessert", "beverage", "snack", "salad"]
            ]
        
        else:
            return items
    
    def _get_user_embedding(
        self,
        user: User,
        embedding_field: str
    ) -> Optional[List[float]]:
        from models.user import TASTE_AXES
        
        embedding = [user.taste_vector.get(axis, 0.5) for axis in TASTE_AXES]
        
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
    
    def retrieve_candidates_from_query(
        self,
        session: Session,
        user: User,
        parsed_query: ParsedQuery,
        k: int = 50,
        budget: Optional[float] = None,
        exclude_recent_days: int = 2
    ) -> List[MenuItem]:
        if not parsed_query.embedding_text:
            raise ValueError("parsed_query must have embedding_text for retrieval")
        
        logger.info(
            "Retrieving candidates from query",
            extra={
                "user_id": str(user.id),
                "query": parsed_query.raw_query,
                "intent": parsed_query.intent.value,
                "k": k
            }
        )
        
        recent_item_ids = self._get_recent_item_ids(session, user, days=exclude_recent_days)
        
        query_embedding = self._generate_query_embedding(parsed_query)
        if not query_embedding:
            raise ValueError("failed to generate query embedding")
        
        if self._ensure_faiss_loaded():
            return self._retrieve_query_with_faiss(
                session, user, query_embedding, parsed_query, k, budget, recent_item_ids
            )
        else:
            return self._retrieve_query_with_sql(
                session, user, parsed_query, k, budget, recent_item_ids
            )
    
    def _generate_query_embedding(self, parsed_query: ParsedQuery) -> Optional[List[float]]:
        embedding_result = self.embedding_service.generate_embedding_openai(
            parsed_query.embedding_text
        )
        
        if not embedding_result:
            logger.warning(
                "Failed to generate query embedding with OpenAI, using local",
                extra={"query": parsed_query.raw_query}
            )
            embedding_result = self.embedding_service.generate_embedding_local(
                parsed_query.embedding_text
            )
        
        return embedding_result
    
    def _retrieve_query_with_faiss(
        self,
        session: Session,
        user: User,
        query_embedding: List[float],
        parsed_query: ParsedQuery,
        k: int,
        budget: Optional[float],
        recent_item_ids: Set[UUID]
    ) -> List[MenuItem]:
        k_inflated = k * 4
        
        try:
            search_results = self.faiss_service.search(
                query_embedding=query_embedding,
                k=k_inflated
            )
        except Exception as e:
            logger.error(
                "FAISS query search failed, falling back to SQL",
                extra={"error": str(e)},
                exc_info=True
            )
            return self._retrieve_query_with_sql(
                session, user, parsed_query, k, budget, recent_item_ids
            )
        
        item_ids = [item_id for item_id, _ in search_results]
        
        query = select(MenuItem).where(MenuItem.id.in_(item_ids))
        if parsed_query.cuisine_filter:
            query = query.where(MenuItem.cuisine.contains(parsed_query.cuisine_filter))
        
        items = list(session.exec(query).all())
        
        items_dict = {item.id: item for item in items}
        ordered_items = []
        for item_id, score in search_results:
            if item_id in items_dict:
                ordered_items.append(items_dict[item_id])
        
        filtered_by_recency = [
            item for item in ordered_items 
            if item.id not in recent_item_ids
        ]
        
        filtered_items = self._apply_safety_filters(
            filtered_by_recency, user, budget
        )
        
        adjusted_items = self._apply_taste_adjustments(
            filtered_items, parsed_query.taste_adjustments
        )
        
        logger.info(
            "FAISS query retrieval completed",
            extra={
                "retrieved": len(ordered_items),
                "after_filters": len(adjusted_items)
            }
        )
        
        return adjusted_items[:k]
    
    def _retrieve_query_with_sql(
        self,
        session: Session,
        user: User,
        parsed_query: ParsedQuery,
        k: int,
        budget: Optional[float],
        recent_item_ids: Set[UUID]
    ) -> List[MenuItem]:
        query = select(MenuItem)
        if parsed_query.cuisine_filter:
            query = query.where(MenuItem.cuisine.contains(parsed_query.cuisine_filter))
        
        all_items = list(session.exec(query).all())
        
        non_recent_items = [
            item for item in all_items
            if item.id not in recent_item_ids
        ]
        
        filtered_items = self._apply_safety_filters(
            non_recent_items, user, budget
        )
        
        if not user.taste_vector:
            return filtered_items[:k]
        
        scored_items = []
        for item in filtered_items:
            if not item.features:
                continue
            
            adjusted_features = self._apply_taste_adjustments_to_features(
                item.features, parsed_query.taste_adjustments
            )
            
            score = cosine_similarity(user.taste_vector, adjusted_features)
            scored_items.append((item, score))
        
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        return [item for item, _ in scored_items[:k]]
    
    def _apply_taste_adjustments(
        self,
        items: List[MenuItem],
        taste_adjustments: Dict[str, float]
    ) -> List[MenuItem]:
        if not taste_adjustments:
            return items
        
        adjusted = []
        for item in items:
            if item.features:
                adjusted_features = self._apply_taste_adjustments_to_features(
                    item.features, taste_adjustments
                )
                item_copy = item.model_copy()
                item_copy.features = adjusted_features
                adjusted.append(item_copy)
            else:
                adjusted.append(item)
        
        return adjusted
    
    def _apply_taste_adjustments_to_features(
        self,
        features: Dict[str, float],
        taste_adjustments: Dict[str, float]
    ) -> Dict[str, float]:
        if not taste_adjustments:
            return features
        
        adjusted = features.copy()
        
        for axis, adjustment in taste_adjustments.items():
            if axis.startswith("texture_"):
                continue
            
            if axis in adjusted:
                current_value = adjusted[axis]
                adjusted_value = max(0.0, min(1.0, current_value + adjustment))
                adjusted[axis] = adjusted_value
        
        return adjusted
