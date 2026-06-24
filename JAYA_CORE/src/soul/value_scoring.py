"""
Value Scoring for Jaya AI (Soul module)
Provides a simple scoring function to determine if a user's intent aligns with allowed values
(e.g., privacy, safety, personal preference) to gate external resource usage.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Example: topics that are considered sensitive and should prefer local/private sources
SENSITIVE_TOPICS = {
    "health", "medical", "disease", "symptom", "treatment",
    "finance", "bank", "loan", "debt", "stock",
    "legal", "lawyer", "court", "lawsuit",
    "personal", "private", "password", "ssn", "social security"
}

# Weights: how much each factor influences the score (0.0 to 1.0)
# Higher weight means more influence.
WEIGHT_TOPIC = 0.5
WEIGHT_USER_PREF = 0.3
WEIGHT_CONTEXT = 0.2

def evaluate_intent_value(user_intent: str, context: Dict[str, Any]) -> float:
    """
    Return a value score between 0.0 and 1.0 indicating how aligned the intent is with the user's values.
    A higher score means more aligned (i.e., safe to use external resources).
    A lower score means less aligned (prefer to keep processing local/private).
    This is a simplified implementation; in a real system, this could be a learned model or a rule base.
    """
    score = 1.0  # start with full alignment
    intent_lower = user_intent.lower()

    # 1. Topic sensitivity: if the intent contains sensitive terms, reduce score.
    for term in SENSITIVE_TOPICS:
        if term in intent_lower:
            score -= WEIGHT_TOPIC
            break  # only penalize once for simplicity

    # 2. User preferences from context (if provided)
    user_prefs = context.get("user_preferences", {})
    # Example: user may have set a preference to avoid internet for certain topics
    avoid_internet_topics = user_prefs.get("avoid_internet_topics", [])
    for topic in avoid_internet_topics:
        if topic.lower() in intent_lower:
            score -= WEIGHT_USER_PREF
            break

    # 3. Contextual factors: time of day, location, etc.
    # For example, if the user is in a private setting (like home) we might be more lenient.
    # Here we just check a flag.
    if context.get("is_private_setting", False):
        # being in a private setting might increase trust for external? Actually we might want to be more cautious.
        # Let's say private setting increases comfort with external? We'll adjust slightly upward.
        score += 0.05  # small boost

    # Clamp score between 0 and 1
    score = max(0.0, min(1.0, score))
    logger.debug(f"Value score for intent '{user_intent[:30]}...': {score}")
    return score