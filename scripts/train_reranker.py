"""Train the ML reranking model using historical rating data.

This script:
1. Loads all historical ratings from the database
2. Extracts features for each user-item-context triple
3. Creates labeled dataset (liked=1, disliked=0)
4. Trains LightGBM gradient boosting model
5. Saves model to data/models/reranker.txt
"""

import os
import sys
from typing import List, Dict, Any
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from config.database import get_session
from models import Rating, MenuItem, User, PopulationStats
from services.ml_reranking_service import MLRerankingService
from services.reranking_service import RecommendationContext
from utils.logger import setup_logger

logger = setup_logger(__name__)


def load_training_data(session: Session) -> tuple[List[Dict[str, float]], List[int]]:
    """Load ratings and extract features for training."""
    
    logger.info("Loading ratings from database...")
    ratings = session.exec(select(Rating)).all()
    logger.info(f"Found {len(ratings)} ratings")
    
    if len(ratings) < 10:
        logger.error("Not enough ratings to train model (need at least 10)")
        return [], []
    
    # Load population stats
    pop_stats = session.exec(select(PopulationStats)).first()
    
    # Initialize ML service for feature extraction
    ml_service = MLRerankingService(population_stats=pop_stats)
    
    features_list = []
    labels = []
    
    for idx, rating in enumerate(ratings):
        try:
            # Load user and item
            user = session.get(User, rating.user_id)
            item = session.get(MenuItem, rating.item_id)
            
            if not user or not item:
                logger.warning(f"Skipping rating {rating.id}: user or item not found")
                continue
            
            # Create context from rating timestamp
            hour = rating.timestamp.hour
            day_of_week = rating.timestamp.weekday()
            
            context = RecommendationContext(
                current_hour=hour,
                day_of_week=day_of_week,
                course_preference=item.course,
                budget=None,
                location=None
            )
            
            # Extract features
            features = ml_service._extract_features(item, user, context, session)
            features_list.append(features)
            
            # Create label: rating >= 4 is positive, else negative
            label = 1 if rating.rating >= 4 else 0
            labels.append(label)
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Processed {idx + 1}/{len(ratings)} ratings")
        
        except Exception as e:
            logger.error(f"Error processing rating {rating.id}: {e}", exc_info=True)
            continue
    
    logger.info(f"Extracted features from {len(features_list)} ratings")
    logger.info(f"Positive samples: {sum(labels)}, Negative samples: {len(labels) - sum(labels)}")
    
    return features_list, labels


def train_model(features_list: List[Dict[str, float]], labels: List[int]) -> Any:
    """Train LightGBM model."""
    
    try:
        import lightgbm as lgb
    except ImportError:
        logger.error("lightgbm not installed. Install with: pip install lightgbm")
        sys.exit(1)
    
    # Convert to numpy arrays
    feature_names = sorted(features_list[0].keys())
    logger.info(f"Training with {len(feature_names)} features: {feature_names}")
    
    X = np.array([[f[name] for name in feature_names] for f in features_list])
    y = np.array(labels)
    
    logger.info(f"Training set shape: {X.shape}")
    
    # Create LightGBM dataset
    train_data = lgb.Dataset(X, label=y, feature_name=feature_names)
    
    # Train model
    params = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'boosting_type': 'gbdt',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'feature_fraction': 0.9,
        'bagging_fraction': 0.8,
        'bagging_freq': 5,
        'verbose': 0
    }
    
    logger.info("Training LightGBM model...")
    model = lgb.train(
        params,
        train_data,
        num_boost_round=100,
        valid_sets=[train_data],
        valid_names=['train']
    )
    
    logger.info("Training complete!")
    
    # Feature importance
    importance = model.feature_importance(importance_type='gain')
    feature_importance = sorted(
        zip(feature_names, importance),
        key=lambda x: x[1],
        reverse=True
    )
    
    logger.info("Top 10 most important features:")
    for name, score in feature_importance[:10]:
        logger.info(f"  {name}: {score:.2f}")
    
    return model


def save_model(model: Any, output_path: str):
    """Save trained model to disk."""
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    model.save_model(output_path)
    logger.info(f"Model saved to {output_path}")


def main():
    """Main training pipeline."""
    
    logger.info("=== ML Reranker Training ===")
    
    # Load data
    with next(get_session()) as session:
        features_list, labels = load_training_data(session)
    
    if len(features_list) < 10:
        logger.error("Not enough training data. Need at least 10 ratings.")
        sys.exit(1)
    
    # Train model
    model = train_model(features_list, labels)
    
    # Save model
    output_path = "data/models/reranker.txt"
    save_model(model, output_path)
    
    logger.info("=== Training Complete ===")


if __name__ == "__main__":
    main()
