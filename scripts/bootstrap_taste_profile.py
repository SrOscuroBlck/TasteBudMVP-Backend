#!/usr/bin/env python3
"""
Bootstrap user taste profile based on their rating history.

Analyzes liked/disliked items with REAL features (from old restaurant)
and manually sets a personalized taste vector to kickstart recommendations.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlmodel import Session, select
from config.database import engine
from models import User, MenuItem, Rating
from uuid import UUID

USER_ID = UUID("385b70e4-35f6-4d8e-9113-d1ef1672afec")


def bootstrap_taste_profile():
    """Analyze user's rating history and generate personalized taste profile."""
    
    with Session(engine) as session:
        user = session.get(User, USER_ID)
        if not user:
            print(f"❌ User {USER_ID} not found")
            return
        
        print("="*80)
        print("🧠 ANALYZING YOUR TASTE PROFILE")
        print("="*80)
        print()
        
        # Get all ratings
        ratings = session.exec(
            select(Rating, MenuItem)
            .join(MenuItem, Rating.item_id == MenuItem.id)
            .where(Rating.user_id == USER_ID)
            .order_by(Rating.timestamp.desc())
        ).all()
        
        if not ratings:
            print("❌ No ratings found")
            return
        
        liked_items = []
        disliked_items = []
        
        for rating, item in ratings:
            # Only consider items with meaningful features (not all 0.5)
            if item.features and not all(0.4 <= v <= 0.6 for v in item.features.values()):
                if rating.liked or rating.rating >= 4:
                    liked_items.append((item, rating))
                elif not rating.liked or rating.rating <= 2:
                    disliked_items.append((item, rating))
        
        print(f"📊 Analysis:")
        print(f"   Total ratings: {len(ratings)}")
        print(f"   Liked (with real features): {len(liked_items)}")
        print(f"   Disliked (with real features): {len(disliked_items)}")
        print()
        
        if len(liked_items) == 0:
            print("⚠️  No liked items with real features found")
            print("   Cannot bootstrap taste profile automatically")
            return
        
        # Analyze liked items
        print("👍 ITEMS YOU LIKED:")
        print("-" * 80)
        for item, rating in liked_items[:10]:
            dominant_axes = sorted(
                [(k, v) for k, v in item.features.items() if v > 0.6],
                key=lambda x: x[1],
                reverse=True
            )[:3]
            features_str = ", ".join(f"{k}:{v:.2f}" for k, v in dominant_axes)
            print(f"   {item.name[:50]:<50}  {features_str}")
        print()
        
        # Calculate average taste profile from liked items
        taste_accumulator = {}
        for item, _ in liked_items:
            for axis, value in item.features.items():
                if axis not in taste_accumulator:
                    taste_accumulator[axis] = []
                taste_accumulator[axis].append(value)
        
        learned_profile = {}
        for axis, values in taste_accumulator.items():
            avg = sum(values) / len(values)
            # Emphasize preferences - if you like high umami food, boost it
            if avg > 0.7:
                avg = min(1.0, avg + 0.1)
            elif avg < 0.3:
                avg = max(0.0, avg - 0.1)
            learned_profile[axis] = round(avg, 3)
        
        # Analyze disliked items to adjust
        if disliked_items:
            print("👎 ITEMS YOU DISLIKED:")
            print("-" * 80)
            for item, rating in disliked_items[:10]:
                dominant_axes = sorted(
                    [(k, v) for k, v in item.features.items() if v > 0.6],
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
                features_str = ", ".join(f"{k}:{v:.2f}" for k, v in dominant_axes)
                print(f"   {item.name[:50]:<50}  {features_str}")
            print()
            
            # Penalize axes from disliked items
            dislike_accumulator = {}
            for item, _ in disliked_items:
                for axis, value in item.features.items():
                    if value > 0.6:  # Only penalize strong characteristics
                        if axis not in dislike_accumulator:
                            dislike_accumulator[axis] = []
                        dislike_accumulator[axis].append(value)
            
            for axis, values in dislike_accumulator.items():
                if axis in learned_profile:
                    penalty = sum(values) / len(values) * 0.1
                    learned_profile[axis] = max(0.0, learned_profile[axis] - penalty)
        
        # Ensure all 10 axes are present
        all_axes = ["sweet", "sour", "salty", "bitter", "umami", "spicy", "fattiness", "acidity", "crunch", "temp_hot"]
        for axis in all_axes:
            if axis not in learned_profile:
                learned_profile[axis] = 0.5
        
        print("🎯 LEARNED TASTE PROFILE:")
        print("-" * 80)
        sorted_axes = sorted(learned_profile.items(), key=lambda x: x[1], reverse=True)
        for axis, value in sorted_axes:
            bar = "█" * int(value * 20)
            emoji = "🔥" if value > 0.7 else "✓" if value > 0.55 else "○" if value > 0.45 else "✗"
            print(f"   {emoji} {axis:12} : {value:.3f}  {bar}")
        print()
        
        # Compare to current profile
        print("📊 CHANGES FROM CURRENT PROFILE:")
        print("-" * 80)
        for axis in all_axes:
            old_val = user.taste_vector.get(axis, 0.5)
            new_val = learned_profile[axis]
            change = new_val - old_val
            if abs(change) > 0.05:
                emoji = "📈" if change > 0 else "📉"
                print(f"   {emoji} {axis:12} : {old_val:.3f} → {new_val:.3f}  ({change:+.3f})")
        print()
        
        # Update user profile
        print("💾 Updating user profile...")
        user.taste_vector = learned_profile
        user.taste_uncertainty = {axis: max(0.0, 0.5 - len(liked_items) * 0.05) for axis in all_axes}
        session.add(user)
        session.commit()
        
        print()
        print("="*80)
        print("✅ TASTE PROFILE UPDATED!")
        print("="*80)
        print()
        print("Your preferences have been learned from your rating history.")
        print("The recommendation algorithm will now use this personalized profile.")
        print()
        print("🔄 Restart your app or refresh to see personalized recommendations!")


if __name__ == "__main__":
    bootstrap_taste_profile()
