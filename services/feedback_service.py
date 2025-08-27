from __future__ import annotations
from typing import List, Dict
from datetime import datetime
from sqlmodel import Session, select
from models import User, MenuItem, Rating, Interaction, PopulationStats
from .features import clamp01


LEARNING_RATE = 0.03


class FeedbackService:
    def add_rating(self, session: Session, user: User, item_id: str, rating: int, liked: bool, reasons: List[str], comment: str = "") -> Rating:
        from uuid import UUID
        item = session.get(MenuItem, UUID(item_id))
        r = Rating(user_id=user.id, item_id=item.id, rating=rating, liked=liked, reasons=",".join(reasons), comment=comment)
        session.add(r)
        self._apply_learning(user, item, liked or rating >= 4, rating <= 2, reasons)
        user.last_updated = datetime.utcnow()
        session.add(user)
        session.commit()
        session.refresh(r)
        return r

    def add_interaction(self, session: Session, user: User, item_id: str, type_: str) -> Interaction:
        from uuid import UUID
        it = session.get(MenuItem, UUID(item_id))
        inter = Interaction(user_id=user.id, item_id=it.id, type=type_)  # type: ignore[arg-type]
        session.add(inter)
        session.commit()
        return inter

    def _apply_learning(self, user: User, item: MenuItem, positive: bool, negative: bool, reasons: List[str]):
        # nudge axes based on item features
        for axis, val in item.features.items():
            delta = LEARNING_RATE * (val if positive else -val if negative else 0.0)
            if delta:
                user.taste_vector[axis] = clamp01(user.taste_vector.get(axis, 0.5) + delta)
                user.taste_uncertainty[axis] = max(0.0, user.taste_uncertainty.get(axis, 0.5) - abs(delta))
        # cuisine affinity
        for c in item.cuisine:
            user.cuisine_affinity[c] = clamp01(user.cuisine_affinity.get(c, 0.5) + (LEARNING_RATE if positive else -LEARNING_RATE if negative else 0.0))
