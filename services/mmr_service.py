from typing import List, Dict, Optional, Set
from uuid import UUID
import math

from models import MenuItem
from services.features import cosine_similarity
from services.similarity_matrix_service import SimilarityMatrixService
from utils.logger import setup_logger

logger = setup_logger(__name__)


class DiversityConstraints:
    def __init__(
        self,
        max_items_per_cuisine: Optional[int] = None,
        max_items_per_restaurant: Optional[int] = None,
        max_items_in_price_range: Optional[Dict[str, int]] = None,
        required_cuisines: Optional[List[str]] = None,
        min_diversity_score: float = 0.0
    ):
        self.max_items_per_cuisine = max_items_per_cuisine
        self.max_items_per_restaurant = max_items_per_restaurant
        self.max_items_in_price_range = max_items_in_price_range or {}
        self.required_cuisines = required_cuisines or []
        self.min_diversity_score = min_diversity_score


class MMRService:
    
    def __init__(self, similarity_service: Optional[SimilarityMatrixService] = None):
        self.similarity_service = similarity_service
        self._similarity_available = similarity_service is not None and similarity_service.is_loaded
    
    def rerank_with_mmr(
        self,
        candidates: List[MenuItem],
        user_taste_vector: Dict[str, float],
        k: int = 10,
        diversity_weight: float = 0.3,
        constraints: Optional[DiversityConstraints] = None,
        base_scores: Optional[Dict[str, float]] = None
    ) -> List[MenuItem]:
        if not candidates:
            return []
        
        if k >= len(candidates):
            return candidates[:k]
        
        if not user_taste_vector:
            raise ValueError("user_taste_vector is required for MMR ranking")
        
        logger.info(
            "Starting MMR reranking",
            extra={
                "candidate_count": len(candidates),
                "k": k,
                "diversity_weight": diversity_weight,
                "use_similarity_matrix": self._similarity_available,
                "using_precomputed_scores": base_scores is not None
            }
        )
        
        if base_scores is not None:
            relevance_scores = [base_scores.get(str(item.id), 0.0) for item in candidates]
            logger.info(
                "Using pre-computed relevance scores",
                extra={
                    "min_score": min(relevance_scores) if relevance_scores else 0.0,
                    "max_score": max(relevance_scores) if relevance_scores else 0.0,
                    "avg_score": sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
                }
            )
        else:
            relevance_scores = self._compute_relevance_scores(candidates, user_taste_vector)
        
        selected: List[MenuItem] = []
        remaining = list(range(len(candidates)))
        
        cuisine_counts: Dict[str, int] = {}
        restaurant_counts: Dict[UUID, int] = {}
        price_range_counts: Dict[str, int] = {"low": 0, "medium": 0, "high": 0}
        
        while len(selected) < k and remaining:
            if not selected:
                best_idx = max(remaining, key=lambda i: relevance_scores[i])
                selected.append(candidates[best_idx])
                remaining.remove(best_idx)
                self._update_constraint_counters(
                    candidates[best_idx], cuisine_counts, restaurant_counts, price_range_counts
                )
                continue
            
            best_idx = None
            best_mmr_score = float('-inf')
            
            for idx in remaining:
                candidate = candidates[idx]
                
                if not self._satisfies_constraints(
                    candidate, constraints, cuisine_counts, restaurant_counts, price_range_counts
                ):
                    continue
                
                relevance = relevance_scores[idx]
                
                max_similarity = self._compute_max_similarity_to_selected(
                    idx, selected, candidates
                )
                
                mmr_score = (1 - diversity_weight) * relevance - diversity_weight * max_similarity
                
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx
            
            if best_idx is None:
                logger.warning(
                    "MMR could not find more candidates satisfying constraints",
                    extra={
                        "selected_count": len(selected),
                        "remaining_count": len(remaining)
                    }
                )
                break
            
            selected.append(candidates[best_idx])
            remaining.remove(best_idx)
            self._update_constraint_counters(
                candidates[best_idx], cuisine_counts, restaurant_counts, price_range_counts
            )
        
        logger.info(
            "MMR reranking completed",
            extra={
                "selected_count": len(selected),
                "diversity_weight": diversity_weight,
                "final_diversity_score": self._compute_diversity_score(selected)
            }
        )
        
        return selected
    
    def _compute_relevance_scores(
        self,
        candidates: List[MenuItem],
        user_taste_vector: Dict[str, float]
    ) -> List[float]:
        scores = []
        for item in candidates:
            if not item.features:
                scores.append(0.0)
                continue
            
            score = cosine_similarity(user_taste_vector, item.features)
            scores.append(score)
        
        return scores
    
    def _compute_max_similarity_to_selected(
        self,
        candidate_idx: int,
        selected: List[MenuItem],
        all_candidates: List[MenuItem]
    ) -> float:
        if not selected:
            return 0.0
        
        candidate = all_candidates[candidate_idx]
        
        max_sim = 0.0
        for selected_item in selected:
            if self._similarity_available:
                sim = self._get_similarity_from_matrix(candidate, selected_item)
            else:
                sim = self._compute_item_similarity(candidate, selected_item)
            
            max_sim = max(max_sim, sim)
        
        return max_sim
    
    def _get_similarity_from_matrix(
        self,
        item1: MenuItem,
        item2: MenuItem
    ) -> float:
        try:
            return self.similarity_service.get_similarity(item1.id, item2.id)
        except (KeyError, AttributeError):
            return self._compute_item_similarity(item1, item2)
    
    def _compute_item_similarity(self, item1: MenuItem, item2: MenuItem) -> float:
        if not item1.features or not item2.features:
            return 0.0
        
        return cosine_similarity(item1.features, item2.features)
    
    def _satisfies_constraints(
        self,
        candidate: MenuItem,
        constraints: Optional[DiversityConstraints],
        cuisine_counts: Dict[str, int],
        restaurant_counts: Dict[UUID, int],
        price_range_counts: Dict[str, int]
    ) -> bool:
        if not constraints:
            return True
        
        if constraints.max_items_per_cuisine is not None:
            for cuisine in candidate.cuisine:
                if cuisine_counts.get(cuisine, 0) >= constraints.max_items_per_cuisine:
                    return False
        
        if constraints.max_items_per_restaurant is not None:
            if restaurant_counts.get(candidate.restaurant_id, 0) >= constraints.max_items_per_restaurant:
                return False
        
        if constraints.max_items_in_price_range:
            price_range = self._get_price_range(candidate.price)
            max_allowed = constraints.max_items_in_price_range.get(price_range)
            if max_allowed is not None and price_range_counts[price_range] >= max_allowed:
                return False
        
        return True
    
    def _update_constraint_counters(
        self,
        item: MenuItem,
        cuisine_counts: Dict[str, int],
        restaurant_counts: Dict[UUID, int],
        price_range_counts: Dict[str, int]
    ) -> None:
        for cuisine in item.cuisine:
            cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
        
        restaurant_counts[item.restaurant_id] = restaurant_counts.get(item.restaurant_id, 0) + 1
        
        price_range = self._get_price_range(item.price)
        price_range_counts[price_range] = price_range_counts.get(price_range, 0) + 1
    
    def _get_price_range(self, price: Optional[float]) -> str:
        if price is None:
            return "medium"
        
        if price < 15.0:
            return "low"
        elif price < 30.0:
            return "medium"
        else:
            return "high"
    
    def _compute_diversity_score(self, items: List[MenuItem]) -> float:
        if len(items) <= 1:
            return 1.0
        
        total_similarity = 0.0
        pair_count = 0
        
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                sim = self._compute_item_similarity(items[i], items[j])
                total_similarity += sim
                pair_count += 1
        
        if pair_count == 0:
            return 1.0
        
        avg_similarity = total_similarity / pair_count
        
        diversity_score = 1.0 - avg_similarity
        
        return max(0.0, min(1.0, diversity_score))
