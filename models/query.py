from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from enum import Enum


class QueryModifier(str, Enum):
    SPICIER = "spicier"
    LESS_SPICY = "less_spicy"
    SWEETER = "sweeter"
    LESS_SWEET = "less_sweet"
    SALTIER = "saltier"
    LESS_SALTY = "less_salty"
    RICHER = "richer"
    LIGHTER = "lighter"
    CRUNCHIER = "crunchier"
    CREAMIER = "creamier"
    MORE_SAVORY = "more_savory"
    VEGETARIAN = "vegetarian"
    HEALTHIER = "healthier"


class QueryIntent(str, Enum):
    SIMILAR_TO = "similar_to"
    EXPLORE_CUISINE = "explore_cuisine"
    MOOD_BASED = "mood_based"
    FREE_TEXT = "free_text"


class ParsedQuery(BaseModel):
    raw_query: str = Field(..., description="Original user query")
    intent: QueryIntent = Field(..., description="Detected query intent")
    base_text: str = Field(..., description="Core query without modifiers")
    modifiers: List[QueryModifier] = Field(default_factory=list)
    reference_item_id: Optional[str] = Field(None, description="Item ID for similar_to queries")
    cuisine_filter: Optional[str] = Field(None)
    taste_adjustments: Dict[str, float] = Field(default_factory=dict)
    embedding_text: str = Field(..., description="Processed text for embedding")
    
    class Config:
        use_enum_values = False


class QueryModifierEffect(BaseModel):
    taste_axis: str
    adjustment: float
    
    @staticmethod
    def get_modifier_effects() -> Dict[QueryModifier, List["QueryModifierEffect"]]:
        return {
            QueryModifier.SPICIER: [
                QueryModifierEffect(taste_axis="spicy", adjustment=0.3)
            ],
            QueryModifier.LESS_SPICY: [
                QueryModifierEffect(taste_axis="spicy", adjustment=-0.3)
            ],
            QueryModifier.SWEETER: [
                QueryModifierEffect(taste_axis="sweet", adjustment=0.3)
            ],
            QueryModifier.LESS_SWEET: [
                QueryModifierEffect(taste_axis="sweet", adjustment=-0.3)
            ],
            QueryModifier.SALTIER: [
                QueryModifierEffect(taste_axis="salty", adjustment=0.3)
            ],
            QueryModifier.LESS_SALTY: [
                QueryModifierEffect(taste_axis="salty", adjustment=-0.3)
            ],
            QueryModifier.RICHER: [
                QueryModifierEffect(taste_axis="fatty", adjustment=0.3),
                QueryModifierEffect(taste_axis="umami", adjustment=0.2)
            ],
            QueryModifier.LIGHTER: [
                QueryModifierEffect(taste_axis="fatty", adjustment=-0.3),
                QueryModifierEffect(taste_axis="sweet", adjustment=-0.1)
            ],
            QueryModifier.CRUNCHIER: [
                QueryModifierEffect(taste_axis="texture_crunchy", adjustment=0.4)
            ],
            QueryModifier.CREAMIER: [
                QueryModifierEffect(taste_axis="texture_creamy", adjustment=0.4)
            ],
            QueryModifier.MORE_SAVORY: [
                QueryModifierEffect(taste_axis="umami", adjustment=0.3),
                QueryModifierEffect(taste_axis="salty", adjustment=0.2)
            ],
            QueryModifier.VEGETARIAN: [],
            QueryModifier.HEALTHIER: [
                QueryModifierEffect(taste_axis="fatty", adjustment=-0.3)
            ]
        }
