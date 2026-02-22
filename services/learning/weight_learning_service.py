from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime
from uuid import UUID
from sqlmodel import Session, select

from models.user_scoring_weights import UserScoringWeights
from models import User
from utils.logger import setup_logger

logger = setup_logger(__name__)


class WeightLearningService:
    
    def __init__(self):
        self.calibration_threshold = 50
    
    def get_or_create_weights(
        self,
        db_session: Session,
        user: User
    ) -> UserScoringWeights:
        if not user:
            raise ValueError("user is required to get or create weights")
        
        statement = select(UserScoringWeights).where(
            UserScoringWeights.user_id == user.id
        )
        weights = db_session.exec(statement).first()
        
        if weights:
            return weights
        
        weights = UserScoringWeights(user_id=user.id)
        weights.normalize_weights()
        
        db_session.add(weights)
        db_session.commit()
        db_session.refresh(weights)
        
        logger.info(
            "Created default scoring weights",
            extra={"user_id": str(user.id), "weights": weights.get_weights_dict()}
        )
        
        return weights
    
    def update_weights_online(
        self,
        db_session: Session,
        weights: UserScoringWeights,
        score_components: Dict[str, float],
        was_liked: bool
    ) -> None:
        if not weights:
            raise ValueError("weights required for online update")
        
        if not score_components:
            raise ValueError("score_components required for update")
        
        target = 1.0 if was_liked else 0.0
        
        predicted = sum(score_components.values())
        
        error = target - predicted
        
        component_mapping = {
            "taste_similarity": "taste_weight",
            "cuisine_affinity": "cuisine_weight",
            "popularity": "popularity_weight",
            "exploration_bonus": "exploration_weight"
        }
        
        for component_name, component_value in score_components.items():
            weight_attr = component_mapping.get(component_name)
            
            if not weight_attr:
                continue
            
            current_weight = getattr(weights, weight_attr)
            
            gradient = error * component_value
            
            momentum_key = weight_attr
            if momentum_key not in weights.momentum:
                weights.momentum[momentum_key] = 0.0
            
            weights.momentum[momentum_key] = (
                0.9 * weights.momentum[momentum_key] +
                0.1 * gradient
            )
            
            new_weight = current_weight + weights.learning_rate * weights.momentum[momentum_key]
            new_weight = max(0.01, min(1.0, new_weight))
            
            setattr(weights, weight_attr, new_weight)
        
        weights.normalize_weights()
        
        weights.feedback_count += 1
        weights.last_updated = datetime.utcnow()
        
        db_session.add(weights)
        
        logger.info(
            "Weights updated online",
            extra={
                "user_id": str(weights.user_id),
                "error": round(error, 3),
                "new_weights": weights.get_weights_dict(),
                "feedback_count": weights.feedback_count
            }
        )
    
    def should_calibrate(self, weights: UserScoringWeights) -> bool:
        if weights.feedback_count < self.calibration_threshold:
            return False
        
        if weights.last_calibration_at is None:
            return True
        
        feedbacks_since_calibration = weights.feedback_count
        
        if feedbacks_since_calibration >= self.calibration_threshold:
            return True
        
        return False
    
    def calibrate_weights_optuna(
        self,
        db_session: Session,
        weights: UserScoringWeights,
        feedback_history: List[Dict],
        n_trials: int = 100
    ) -> None:
        if not weights:
            raise ValueError("weights required for calibration")
        
        if not feedback_history or len(feedback_history) < 10:
            logger.warning(
                "Insufficient feedback history for calibration",
                extra={
                    "user_id": str(weights.user_id),
                    "history_length": len(feedback_history) if feedback_history else 0
                }
            )
            return
        
        try:
            import optuna
            
            def objective(trial):
                taste_w = trial.suggest_float("taste_weight", 0.1, 0.8)
                cuisine_w = trial.suggest_float("cuisine_weight", 0.05, 0.4)
                popularity_w = trial.suggest_float("popularity_weight", 0.05, 0.3)
                exploration_w = trial.suggest_float("exploration_weight", 0.05, 0.3)
                
                total = taste_w + cuisine_w + popularity_w + exploration_w
                trial_weights = {
                    "taste": taste_w / total,
                    "cuisine": cuisine_w / total,
                    "popularity": popularity_w / total,
                    "exploration": exploration_w / total
                }
                
                correct_predictions = 0
                for event in feedback_history:
                    predicted_score = (
                        trial_weights["taste"] * event.get("taste_similarity", 0.0) +
                        trial_weights["cuisine"] * event.get("cuisine_affinity", 0.0) +
                        trial_weights["popularity"] * event.get("popularity", 0.0) +
                        trial_weights["exploration"] * event.get("exploration_bonus", 0.0)
                    )
                    
                    was_liked = event.get("was_liked", False)
                    prediction = predicted_score > 0.5
                    
                    if prediction == was_liked:
                        correct_predictions += 1
                
                accuracy = correct_predictions / len(feedback_history)
                return accuracy
            
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            
            study = optuna.create_study(direction="maximize")
            study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
            
            best_params = study.best_params
            
            total = sum(best_params.values())
            weights.taste_weight = best_params["taste_weight"] / total
            weights.cuisine_weight = best_params["cuisine_weight"] / total
            weights.popularity_weight = best_params["popularity_weight"] / total
            weights.exploration_weight = best_params["exploration_weight"] / total
            
            weights.last_calibration_at = datetime.utcnow()
            weights.last_updated = datetime.utcnow()
            
            db_session.add(weights)
            db_session.commit()
            
            logger.info(
                "Weights calibrated via Optuna",
                extra={
                    "user_id": str(weights.user_id),
                    "best_accuracy": round(study.best_value, 3),
                    "new_weights": weights.get_weights_dict(),
                    "n_trials": n_trials,
                    "history_size": len(feedback_history)
                }
            )
            
        except ImportError:
            logger.error(
                "Optuna not installed - cannot perform calibration",
                extra={"user_id": str(weights.user_id)}
            )
        except Exception as e:
            logger.error(
                "Failed to calibrate weights",
                extra={"user_id": str(weights.user_id), "error": str(e)},
                exc_info=True
            )
