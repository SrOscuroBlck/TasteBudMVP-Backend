from __future__ import annotations
from typing import Dict, Any, List
from uuid import uuid4
from datetime import datetime
from sqlmodel import Session, select
from config.settings import settings
from models import User, OnboardingState, PopulationStats
from .features import clamp01
from .gpt_helper import generate_onboarding_question


FALLBACK_QUESTIONS = [
    {
        "prompt": "Would you rather have a cheesy Margherita pizza or a spicy beef taco?",
        "options": [
            {"id": "A", "label": "Margherita Pizza", "tags": ["cheesy", "baked", "umami"], "ingredient_keys": ["dough", "tomato", "mozzarella"]},
            {"id": "B", "label": "Spicy Beef Taco", "tags": ["spicy", "fried", "umami"], "ingredient_keys": ["beef", "chili"]},
        ],
        "axis_hints": {"umami": 0.2, "fattiness": 0.1, "spicy": 0.3},
    },
    {
        "prompt": "Would you prefer sweet honey-glazed salmon or tangy lemon herb chicken?",
        "options": [
            {"id": "A", "label": "Honey-Glazed Salmon", "tags": ["sweet", "grilled", "tender"], "ingredient_keys": ["salmon", "honey", "ginger"]},
            {"id": "B", "label": "Lemon Herb Chicken", "tags": ["tangy", "citrus", "savory"], "ingredient_keys": ["chicken", "lemon", "herbs"]},
        ],
        "axis_hints": {"sweet": 0.4, "acidity": 0.3, "sour": 0.2},
    },
    {
        "prompt": "Would you choose crispy fried chicken or a fresh garden salad?",
        "options": [
            {"id": "A", "label": "Crispy Fried Chicken", "tags": ["crispy", "fried", "savory"], "ingredient_keys": ["chicken", "breading", "oil"]},
            {"id": "B", "label": "Fresh Garden Salad", "tags": ["fresh", "crunchy", "light"], "ingredient_keys": ["lettuce", "tomato", "cucumber"]},
        ],
        "axis_hints": {"crunch": 0.3, "fattiness": 0.4, "acidity": 0.2},
    },
    {
        "prompt": "Would you rather have salty french fries or sweet potato fries?",
        "options": [
            {"id": "A", "label": "Salty French Fries", "tags": ["salty", "crispy", "savory"], "ingredient_keys": ["potato", "salt", "oil"]},
            {"id": "B", "label": "Sweet Potato Fries", "tags": ["sweet", "crispy", "earthy"], "ingredient_keys": ["sweet_potato", "oil", "cinnamon"]},
        ],
        "axis_hints": {"salty": 0.4, "sweet": 0.3, "crunch": 0.2},
    },
    {
        "prompt": "Would you prefer rich chocolate lava cake or tangy key lime pie?",
        "options": [
            {"id": "A", "label": "Chocolate Lava Cake", "tags": ["sweet", "rich", "warm"], "ingredient_keys": ["chocolate", "butter", "sugar"]},
            {"id": "B", "label": "Key Lime Pie", "tags": ["tangy", "citrus", "tart"], "ingredient_keys": ["lime", "condensed_milk", "graham_cracker"]},
        ],
        "axis_hints": {"sweet": 0.3, "sour": 0.4, "fattiness": 0.2},
    },
    {
        "prompt": "Would you choose spicy hot wings or mild BBQ ribs?",
        "options": [
            {"id": "A", "label": "Spicy Hot Wings", "tags": ["spicy", "tangy", "crispy"], "ingredient_keys": ["chicken", "hot_sauce", "butter"]},
            {"id": "B", "label": "Mild BBQ Ribs", "tags": ["sweet", "smoky", "tender"], "ingredient_keys": ["pork", "bbq_sauce", "brown_sugar"]},
        ],
        "axis_hints": {"spicy": 0.5, "sweet": 0.3, "umami": 0.2},
    },
    {
        "prompt": "Would you rather have creamy mac and cheese or light steamed vegetables?",
        "options": [
            {"id": "A", "label": "Creamy Mac and Cheese", "tags": ["creamy", "cheesy", "rich"], "ingredient_keys": ["pasta", "cheese", "cream"]},
            {"id": "B", "label": "Steamed Vegetables", "tags": ["light", "fresh", "healthy"], "ingredient_keys": ["broccoli", "carrot", "zucchini"]},
        ],
        "axis_hints": {"fattiness": 0.5, "umami": 0.2, "acidity": 0.1},
    },
]


class OnboardingService:
    def start(self, user: User, session: Session) -> Dict[str, Any]:
        # Deactivate all previous onboarding states
        previous_states = session.exec(
            select(OnboardingState).where(
                OnboardingState.user_id == user.id,
                OnboardingState.active == True
            )
        ).all()
        for prev_state in previous_states:
            prev_state.active = False
            session.add(prev_state)
        session.commit()
        
        # initialize vectors from priors
        priors = session.exec(select(PopulationStats)).first()
        
        # Define default axes
        default_axes = ["sweet", "sour", "salty", "bitter", "umami", "spicy", "fattiness", "acidity", "crunch", "temp_hot"]
        
        # Initialize taste_vector
        if not user.taste_vector:
            if priors and priors.axis_prior_mean:
                user.taste_vector = dict(priors.axis_prior_mean)
            else:
                user.taste_vector = {k: 0.5 for k in default_axes}
        
        # Initialize taste_uncertainty
        if not user.taste_uncertainty:
            if priors and priors.axis_prior_sigma:
                user.taste_uncertainty = dict(priors.axis_prior_sigma)
            else:
                user.taste_uncertainty = {k: 0.5 for k in default_axes}
        
        # Initialize cuisine_affinity
        if not user.cuisine_affinity and priors and priors.cuisine_prior:
            user.cuisine_affinity = dict(priors.cuisine_prior)
        
        state = OnboardingState(user_id=user.id, active=True, answered_pairs=[], pending_axis_targets=self._top_uncertain_axes(user), confidence=0.0)
        session.add(state)
        session.commit()
        session.refresh(state)
        user.onboarding_state = {"state_id": state.id, "active": True, "confidence": 0.0}
        session.add(user)
        session.commit()
        return self._next_question(session, user, state)

    def answer(self, user: User, question_id: str, chosen_option_id: str, session: Session) -> Dict[str, Any]:
        state = session.exec(select(OnboardingState).where(OnboardingState.user_id == user.id, OnboardingState.active == True)).first()
        if not state:
            return {"complete": True}
        
        # Get question data from OnboardingState
        last_question_data = state.current_question_data or {}
        
        # Extract axis hints
        axis_hints = last_question_data.get("axis_hints", {})
        
        # Get the chosen option details
        options = last_question_data.get("options", [])
        chosen_option = next((opt for opt in options if opt.get("id") == chosen_option_id), None)
        
        # coerce axis_hints to numeric deltas in [0,1]
        numeric_axis_hints = {}
        for axis, delta in axis_hints.items():
            try:
                v = float(delta)
            except Exception:
                v = 0.2
            numeric_axis_hints[axis] = max(0.0, min(1.0, abs(v)))

        sign = 1.0 if chosen_option_id == "B" else -1.0
        for axis, v in numeric_axis_hints.items():
            old = user.taste_vector.get(axis, 0.5)
            user.taste_vector[axis] = clamp01(old + settings.ONBOARDING_K * sign * v)
            user.taste_uncertainty[axis] = max(0.0, user.taste_uncertainty.get(axis, 0.5) - settings.ONBOARDING_SIGMA_STEP)
        
        # Record answer with chosen option details
        new_answer = {
            "question_id": question_id,
            "chosen": chosen_option_id,
            "timestamp": datetime.utcnow().isoformat(),
            "ingredients": chosen_option.get("ingredient_keys", []) if chosen_option else [],
            "tags": chosen_option.get("tags", []) if chosen_option else [],
            "label": chosen_option.get("label", "") if chosen_option else ""
        }
        state.answered_pairs = state.answered_pairs + [new_answer]
        
        # recompute confidence
        avg_sigma = sum(user.taste_uncertainty.values()) / max(1, len(user.taste_uncertainty))
        state.confidence = 1.0 - avg_sigma
        user.last_updated = datetime.utcnow()
        session.add(user)
        session.add(state)
        session.commit()
        session.refresh(state)
        # early stop
        if state.confidence >= settings.ONBOARDING_EARLY_STOP_CONFIDENCE or len(state.answered_pairs) >= settings.ONBOARDING_MAX_QUESTIONS:
            state.active = False
            session.add(state)
            session.commit()
            
            # Calculate cuisine affinity from chosen ingredients
            self._calculate_cuisine_affinity_from_choices(user, state, session)
            
            return {"complete": True}
        return self._next_question(session, user, state)

    def _next_question(self, session: Session, user: User, state: OnboardingState) -> Dict[str, Any]:
        target_axes = self._top_uncertain_axes(user)
        context = {
            "user_allergies": user.allergies,
            "target_axes": target_axes,
            "schema": "{question_id,prompt,options:[{id,label,tags,ingredient_keys}],axis_hints}"
        }
        q = generate_onboarding_question(context)
        if not q:
            # Use cycling fallback based on number of answered questions
            fallback_index = len(state.answered_pairs) % len(FALLBACK_QUESTIONS)
            qf = FALLBACK_QUESTIONS[fallback_index]
            q = {"question_id": str(uuid4()), **qf}
        
        # Store full question data in OnboardingState for retrieval when answer comes
        state.current_question_data = {
            "question_id": q["question_id"],
            "axis_hints": q.get("axis_hints", {}),
            "options": q.get("options", [])
        }
        session.add(state)
        session.commit()
        return q

    def _top_uncertain_axes(self, user: User) -> List[str]:
        items = sorted(user.taste_uncertainty.items(), key=lambda kv: kv[1], reverse=True)
        return [k for k, _ in items[:3]]
    
    def _calculate_cuisine_affinity_from_choices(self, user: User, state: OnboardingState, session: Session) -> None:
        """Calculate cuisine affinity based on ingredients chosen during onboarding"""
        # Mapping of ingredients to cuisines
        ingredient_cuisine_map = {
            # Italian
            "dough": ["Italian"], "mozzarella": ["Italian"], "pasta": ["Italian"], 
            "parmesan": ["Italian"], "basil": ["Italian"], "olive_oil": ["Italian"],
            
            # Mexican
            "chili": ["Mexican"], "tortilla": ["Mexican"], "jalapeño": ["Mexican"],
            "cilantro": ["Mexican"], "lime": ["Mexican"], "cumin": ["Mexican"],
            "avocado": ["Mexican"],
            
            # Asian (Japanese, Chinese, Thai)
            "soy_sauce": ["Japanese", "Chinese"], "ginger": ["Asian"], 
            "sesame": ["Asian"], "rice": ["Asian"], "noodles": ["Asian"],
            "tofu": ["Asian"], "miso": ["Japanese"], "wasabi": ["Japanese"],
            
            # Indian
            "curry": ["Indian"], "turmeric": ["Indian"], "cardamom": ["Indian"],
            "coriander": ["Indian"], "ghee": ["Indian"],
            
            # American
            "beef": ["American"], "bacon": ["American"], "cheddar": ["American"],
            
            # Mediterranean
            "lamb": ["Mediterranean"], "feta": ["Mediterranean"], 
            "olive": ["Mediterranean"], "lemon": ["Mediterranean"],
            
            # General proteins/vegetables (multiple cuisines)
            "chicken": ["American", "Asian", "Mexican", "Mediterranean"],
            "tomato": ["Italian", "Mexican", "Mediterranean"],
            "garlic": ["Italian", "Asian", "Mexican", "Mediterranean"],
        }
        
        # Count cuisine occurrences from chosen ingredients
        cuisine_counts = {}
        total_choices = 0
        
        for answer in state.answered_pairs:
            ingredients = answer.get("ingredients", [])
            for ingredient in ingredients:
                cuisines = ingredient_cuisine_map.get(ingredient, [])
                for cuisine in cuisines:
                    cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
                    total_choices += 1
        
        # If no cuisines detected from ingredients, use population priors
        if total_choices == 0:
            priors = session.exec(select(PopulationStats)).first()
            if priors and priors.cuisine_prior:
                user.cuisine_affinity = dict(priors.cuisine_prior)
            else:
                user.cuisine_affinity = {}
            session.add(user)
            session.commit()
            return
        
        # Calculate affinity scores (normalized by total choices)
        cuisine_affinity = {}
        for cuisine, count in cuisine_counts.items():
            # Score between 0.3 (min) and 1.0 (max) based on frequency
            score = 0.3 + (0.7 * count / max(total_choices, 1))
            cuisine_affinity[cuisine] = min(1.0, score)
        
        # Add common cuisines not seen with low default scores
        all_cuisines = ["Italian", "Mexican", "Japanese", "Chinese", "Indian", "American", "Mediterranean", "Thai"]
        for cuisine in all_cuisines:
            if cuisine not in cuisine_affinity:
                cuisine_affinity[cuisine] = 0.2  # Low baseline for unseen cuisines
        
        user.cuisine_affinity = cuisine_affinity
        session.add(user)
        session.commit()
