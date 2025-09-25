from datetime import datetime, timezone
from typing import Tuple, Optional, Dict


def score_article(title: str, content: str, published_iso: Optional[str] = None) -> Tuple[int, str, Dict[str, int]]:
    """Return (score0to10, primary_category, detail_breakdown)."""
    text = f"{title}\n{content}".lower()

    # Simple scoring
    score = 0

    # Major companies: +3 points
    if any(company in text for company in ["openai", "google", "microsoft", "meta", "apple", "amazon", "nvidia"]):
        score += 3

    # Major AI models: +2 points
    if any(model in text for model in ["gpt", "claude", "gemini", "llama"]):
        score += 2

    # New launch/release: +2 points
    if any(term in text for term in ["launch", "release", "announce", "available now", "available today"]):
        score += 2

    # Japan relevance: +1 point
    if "japan" in text or "japanese" in text or "日本" in text:
        score += 1

    # Recency check
    if published_iso:
        try:
            dt = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - dt).days
            if days <= 1:
                score += 2  # Very fresh news
            elif days > 7:
                score -= 1  # Old news
        except Exception:
            pass

    # Cap at 10
    score = min(10, max(0, score))

    # Simplified return (keeping compatibility)
    return score, "AI", {}