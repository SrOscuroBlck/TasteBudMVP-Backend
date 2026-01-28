from typing import List, Optional
from uuid import UUID
from sqlmodel import Session, select

from models import MenuItem, User
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
        use_faiss: bool = True
    ) -> List[MenuItem]:
        if not user.taste_vector:
            raise ValueError("user taste_vector is required for retrieval")
        
        if use_faiss and self._ensure_faiss_loaded():
            return self._retrieve_with_faiss(
                session, user, k, restaurant_id, budget
            )
        else:
            return self._retrieve_with_sql(
                session, user, k, restaurant_id, budget
            )
    
    def _retrieve_with_faiss(
        self,
        session: Session,
        user: User,
        k: int,
        restaurant_id: Optional[str],
        budget: Optional[float]
    ) -> List[MenuItem]:
        embedding_field = "reduced_embedding" if settings.FAISS_DIMENSION == 64 else "embedding"
        
        user_embedding = self._get_user_embedding(user, embedding_field)
        if not user_embedding:
            logger.warning(
                "User has no embedding, falling back to SQL",
                extra={"user_id": str(user.id)}
            )
            return self._retrieve_with_sql(session, user, k, restaurant_id, budget)
        
        k_inflated = k * 3
        
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
            return self._retrieve_with_sql(session, user, k, restaurant_id, budget)
        
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
        
        filtered_items = self._apply_safety_filters(
            ordered_items, user, budget
        )
        
        return filtered_items[:k]
    
    def _retrieve_with_sql(
        self,
        session: Session,
        user: User,
        k: int,
        restaurant_id: Optional[str],
        budget: Optional[float]
    ) -> List[MenuItem]:
        query = select(MenuItem)
        if restaurant_id:
            query = query.where(MenuItem.restaurant_id == UUID(restaurant_id))
        
        all_items = list(session.exec(query).all())
        
        filtered_items = self._apply_safety_filters(
            all_items, user, budget
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
