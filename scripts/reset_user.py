#!/usr/bin/env python3
"""
Reset user account to fresh state for testing onboarding.

This script:
1. Deletes all ratings and interactions
2. Resets taste profile to neutral
3. Clears onboarding completion
4. Allows user to go through onboarding again
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlmodel import Session, select, delete
from config.database import engine
from models import User, Rating, Interaction, OnboardingState
from uuid import UUID

USER_ID = UUID("385b70e4-35f6-4d8e-9113-d1ef1672afec")


def reset_user():
    """Reset user to fresh state."""
    
    with Session(engine) as session:
        user = session.get(User, USER_ID)
        if not user:
            print(f"❌ User {USER_ID} not found")
            return
        
        print("="*80)
        print("🔄 RESETTING USER ACCOUNT")
        print("="*80)
        print(f"User: {user.email}")
        print()
        
        # Count existing data
        ratings = session.exec(select(Rating).where(Rating.user_id == USER_ID)).all()
        interactions = session.exec(select(Interaction).where(Interaction.user_id == USER_ID)).all()
        onboarding_states = session.exec(select(OnboardingState).where(OnboardingState.user_id == USER_ID)).all()
        
        print(f"📊 Current State:")
        print(f"   Ratings: {len(ratings)}")
        print(f"   Interactions: {len(interactions)}")
        print(f"   Onboarding states: {len(onboarding_states)}")
        print(f"   Onboarding completed: {user.onboarding_completed}")
        print()
        
        # Delete ratings
        if ratings:
            print(f"🗑️  Deleting {len(ratings)} ratings...")
            for rating in ratings:
                session.delete(rating)
        
        # Delete interactions
        if interactions:
            print(f"🗑️  Deleting {len(interactions)} interactions...")
            for interaction in interactions:
                session.delete(interaction)
        
        # Delete onboarding states
        if onboarding_states:
            print(f"🗑️  Deleting {len(onboarding_states)} onboarding states...")
            for state in onboarding_states:
                session.delete(state)
        
        # Reset user profile
        print(f"♻️  Resetting user profile...")
        
        default_axes = ["sweet", "sour", "salty", "bitter", "umami", "spicy", "fattiness", "acidity", "crunch", "temp_hot"]
        
        user.taste_vector = {axis: 0.5 for axis in default_axes}
        user.taste_uncertainty = {axis: 0.5 for axis in default_axes}
        user.cuisine_affinity = {}
        user.liked_ingredients = []
        user.disliked_ingredients = []
        user.onboarding_completed = False
        user.onboarding_state = {}
        
        session.add(user)
        session.commit()
        
        print()
        print("="*80)
        print("✅ USER RESET COMPLETE!")
        print("="*80)
        print()
        print("Your account is now fresh:")
        print("  ✓ All ratings deleted")
        print("  ✓ All interactions deleted")
        print("  ✓ Taste profile reset to neutral (all 0.5)")
        print("  ✓ Onboarding marked as incomplete")
        print("  ✓ Ready to test onboarding flow")
        print()
        print("📱 Next steps:")
        print("  1. Login to the app")
        print("  2. You'll be prompted to complete onboarding")
        print("  3. Answer 7-10 questions about your food preferences")
        print("  4. Get personalized recommendations with the new system!")
        print()


if __name__ == "__main__":
    reset_user()
