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
    }
]


class OnboardingService:
    def start(self, user: User, session: Session) -> Dict[str, Any]:
        # initialize vectors from priors
        priors = session.exec(select(PopulationStats)).first()
        if not user.taste_vector:
            if priors and priors.axis_prior_mean:
                user.taste_vector = dict(priors.axis_prior_mean)
            else:
                user.taste_vector = {k: 0.5 for k in user.taste_uncertainty.keys() or ["sweet","sour","salty","bitter","umami","spicy","fattiness","acidity","crunch","temp_hot"]}
        if not user.taste_uncertainty:
            if priors and priors.axis_prior_sigma:
                user.taste_uncertainty = dict(priors.axis_prior_sigma)
            else:
                user.taste_uncertainty = {k: 0.5 for k in user.taste_vector.keys()}
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
        # get axis hints from user onboarding_state (stored at question time)
        axis_hints = {}
        if user.onboarding_state and isinstance(user.onboarding_state, dict):
            if str(user.onboarding_state.get("last_question_id")) == str(question_id):
                axis_hints = user.onboarding_state.get("last_axis_hints", {}) or {}
        # coerce axis_hints to numeric deltas in [0,1]
        numeric_axis_hints = {}
        for axis, delta in axis_hints.items():
            try:
                v = float(delta)
            except Exception:
                # fallback small nudge if non-numeric
                v = 0.2
            numeric_axis_hints[axis] = max(0.0, min(1.0, abs(v)))

        sign = 1.0 if chosen_option_id == "B" else -1.0
        for axis, v in numeric_axis_hints.items():
            old = user.taste_vector.get(axis, 0.5)
            user.taste_vector[axis] = clamp01(old + settings.ONBOARDING_K * sign * v)
            user.taste_uncertainty[axis] = max(0.0, user.taste_uncertainty.get(axis, 0.5) - settings.ONBOARDING_SIGMA_STEP)
        # record answer only
        state.answered_pairs.append({"question_id": question_id, "chosen": chosen_option_id, "timestamp": datetime.utcnow().isoformat()})
        # recompute confidence
        avg_sigma = sum(user.taste_uncertainty.values()) / max(1, len(user.taste_uncertainty))
        state.confidence = 1.0 - avg_sigma
        user.last_updated = datetime.utcnow()
        session.add(user)
        session.add(state)
        session.commit()
        # early stop
        if state.confidence >= settings.ONBOARDING_EARLY_STOP_CONFIDENCE or len(state.answered_pairs) >= settings.ONBOARDING_MAX_QUESTIONS:
            state.active = False
            session.add(state)
            session.commit()
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
            qf = FALLBACK_QUESTIONS[0]
            q = {"question_id": str(uuid4()), **qf}
        # persist last axis_hints on user to apply when answer arrives
        user.onboarding_state = user.onboarding_state or {}
        user.onboarding_state.update({
            "last_question_id": q["question_id"],
            "last_axis_hints": q.get("axis_hints", {}),
        })
        session.add(user)
        session.commit()
        return q

    def _top_uncertain_axes(self, user: User) -> List[str]:
        items = sorted(user.taste_uncertainty.items(), key=lambda kv: kv[1], reverse=True)
        return [k for k, _ in items[:3]]
