from typing import Optional, Dict, List
import re
from uuid import UUID

from models.query import ParsedQuery, QueryIntent, QueryModifier, QueryModifierEffect
from utils.logger import setup_logger

logger = setup_logger(__name__)


class QueryParsingService:
    
    def __init__(self):
        self.modifier_patterns = self._build_modifier_patterns()
        self.intent_patterns = self._build_intent_patterns()
    
    def _build_modifier_patterns(self) -> Dict[QueryModifier, List[str]]:
        return {
            QueryModifier.SPICIER: [
                r"spicier",
                r"more spicy",
                r"with more heat",
                r"hotter",
                r"add heat"
            ],
            QueryModifier.LESS_SPICY: [
                r"less spicy",
                r"milder",
                r"not spicy",
                r"no heat"
            ],
            QueryModifier.SWEETER: [
                r"sweeter",
                r"more sweet",
                r"add sweetness"
            ],
            QueryModifier.LESS_SWEET: [
                r"less sweet",
                r"not sweet",
                r"reduce sweetness"
            ],
            QueryModifier.SALTIER: [
                r"saltier",
                r"more salty"
            ],
            QueryModifier.LESS_SALTY: [
                r"less salty",
                r"reduce salt"
            ],
            QueryModifier.RICHER: [
                r"richer",
                r"more rich",
                r"heavier",
                r"more indulgent"
            ],
            QueryModifier.LIGHTER: [
                r"lighter",
                r"less heavy",
                r"refreshing",
                r"not rich"
            ],
            QueryModifier.CRUNCHIER: [
                r"crunchier",
                r"more crunchy",
                r"crispy"
            ],
            QueryModifier.CREAMIER: [
                r"creamier",
                r"more creamy",
                r"smoother"
            ],
            QueryModifier.MORE_SAVORY: [
                r"more savory",
                r"umami",
                r"deeper flavor"
            ],
            QueryModifier.VEGETARIAN: [
                r"vegetarian",
                r"veggie",
                r"no meat",
                r"plant-based"
            ],
            QueryModifier.HEALTHIER: [
                r"healthier",
                r"healthy",
                r"lower calorie",
                r"lighter on calories"
            ]
        }
    
    def _build_intent_patterns(self) -> Dict[QueryIntent, List[str]]:
        return {
            QueryIntent.SIMILAR_TO: [
                r"like (.+?) but",
                r"similar to (.+?) but",
                r"something like (.+?) but",
                r"comparable to (.+?) but"
            ],
            QueryIntent.EXPLORE_CUISINE: [
                r"(italian|mexican|chinese|japanese|thai|indian|french|colombian|korean|vietnamese) food",
                r"(italian|mexican|chinese|japanese|thai|indian|french|colombian|korean|vietnamese) cuisine",
                r"something (italian|mexican|chinese|japanese|thai|indian|french|colombian|korean|vietnamese)"
            ],
            QueryIntent.MOOD_BASED: [
                r"feeling (hungry|adventurous|comfort|tired|energetic|celebratory)",
                r"in the mood for",
                r"craving"
            ]
        }
    
    def parse_query(self, query: str, available_item_names: Optional[List[str]] = None) -> ParsedQuery:
        if not query:
            raise ValueError("query cannot be empty")
        
        logger.info("Parsing query", extra={"query": query})
        
        query_lower = query.lower().strip()
        
        detected_intent = self._detect_intent(query_lower)
        reference_item_id = None
        base_text = query
        
        if detected_intent == QueryIntent.SIMILAR_TO:
            reference_item_id, base_text = self._extract_reference_item(
                query_lower, available_item_names
            )
        
        detected_modifiers = self._detect_modifiers(query_lower)
        
        taste_adjustments = self._compute_taste_adjustments(detected_modifiers)
        
        embedding_text = self._build_embedding_text(base_text, detected_modifiers)
        
        cuisine_filter = self._extract_cuisine_filter(query_lower)
        
        parsed = ParsedQuery(
            raw_query=query,
            intent=detected_intent,
            base_text=base_text,
            modifiers=detected_modifiers,
            reference_item_id=reference_item_id,
            cuisine_filter=cuisine_filter,
            taste_adjustments=taste_adjustments,
            embedding_text=embedding_text
        )
        
        logger.info(
            "Query parsed successfully",
            extra={
                "intent": parsed.intent.value,
                "modifiers_count": len(parsed.modifiers),
                "has_reference": parsed.reference_item_id is not None
            }
        )
        
        return parsed
    
    def _detect_intent(self, query_lower: str) -> QueryIntent:
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return intent
        
        return QueryIntent.FREE_TEXT
    
    def _extract_reference_item(
        self, 
        query_lower: str, 
        available_item_names: Optional[List[str]]
    ) -> tuple[Optional[str], str]:
        for pattern in self.intent_patterns[QueryIntent.SIMILAR_TO]:
            match = re.search(pattern, query_lower)
            if match:
                reference_text = match.group(1).strip()
                
                if available_item_names:
                    reference_text = reference_text
                
                base_text = reference_text
                
                return None, base_text
        
        return None, query_lower
    
    def _detect_modifiers(self, query_lower: str) -> List[QueryModifier]:
        detected = []
        
        for modifier, patterns in self.modifier_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    detected.append(modifier)
                    break
        
        return detected
    
    def _compute_taste_adjustments(
        self, 
        modifiers: List[QueryModifier]
    ) -> Dict[str, float]:
        adjustments: Dict[str, float] = {}
        
        modifier_effects = QueryModifierEffect.get_modifier_effects()
        
        for modifier in modifiers:
            effects = modifier_effects.get(modifier, [])
            for effect in effects:
                current = adjustments.get(effect.taste_axis, 0.0)
                adjustments[effect.taste_axis] = max(-1.0, min(1.0, current + effect.adjustment))
        
        return adjustments
    
    def _build_embedding_text(
        self, 
        base_text: str, 
        modifiers: List[QueryModifier]
    ) -> str:
        parts = [base_text]
        
        for modifier in modifiers:
            if modifier == QueryModifier.SPICIER:
                parts.append("with more spice and heat")
            elif modifier == QueryModifier.LESS_SPICY:
                parts.append("mild, not spicy")
            elif modifier == QueryModifier.SWEETER:
                parts.append("with sweetness")
            elif modifier == QueryModifier.RICHER:
                parts.append("rich and indulgent")
            elif modifier == QueryModifier.LIGHTER:
                parts.append("light and refreshing")
            elif modifier == QueryModifier.VEGETARIAN:
                parts.append("vegetarian, no meat")
            elif modifier == QueryModifier.HEALTHIER:
                parts.append("healthy, lower calorie")
        
        return " ".join(parts)
    
    def _extract_cuisine_filter(self, query_lower: str) -> Optional[str]:
        cuisines = [
            "italian", "mexican", "chinese", "japanese", "thai", 
            "indian", "french", "colombian", "korean", "vietnamese",
            "mediterranean", "american", "spanish", "greek"
        ]
        
        for cuisine in cuisines:
            if cuisine in query_lower:
                return cuisine.capitalize()
        
        return None
