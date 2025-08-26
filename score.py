import re
from datetime import datetime, timezone
from typing import Dict, Tuple, List, Optional


_COMPANIES = [
    "openai", "google", "microsoft", "meta", "apple", "amazon", "nvidia",
]

_MODEL_TERMS = [
    "gpt", "claude", "gemini", "llama", "mixtral", "mistral", "phi", "qwen", "xai",
]

_MARKET_TERMS = [
    "standard", "standardization", "regulation", "policy", "governance", "compliance",
    "industry", "industry-wide", "ecosystem", "framework",
]

_TECH_TERMS = [
    "state-of-the-art", "sota", "benchmark", "accuracy", "aime", "mmlu", "humaneval",
    "record", "breakthrough", "novel", "performance", "latency", "throughput",
]

_LAUNCH_TERMS = [
    "launch", "launched", "introduce", "introduces", "introduced", "release", "released",
    "unveil", "unveils", "available now", "available today", "general availability",
]

_RUMOR_TERMS = [
    "rumor", "speculation", "might", "could", "reportedly", "allegedly",
]


def _contains_any(text: str, terms: List[str]) -> bool:
    return any(t in text for t in terms)


def _money_over_100m(text: str) -> bool:
    # $1B, $500M, 200 million, 1.2 billion
    t = text.replace(",", "").lower()
    # B or billion always >= 100M
    if re.search(r"\$?\s*\d+(?:\.\d+)?\s*(b|bn|billion)", t):
        return True
    m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*(m|mm|million)", t)
    if m:
        try:
            val = float(m.group(1))
            return val >= 100.0
        except Exception:
            return False
    # $100000000 pattern
    m2 = re.search(r"\$\s*(\d{9,})", t)
    if m2:
        try:
            return int(m2.group(1)) >= 100_000_000
        except Exception:
            return False
    return False


def score_article(title: str, content: str, published_iso: Optional[str] = None) -> Tuple[int, str, Dict[str, int]]:
    """Return (score0to10, primary_category, detail_breakdown)."""
    text = f"{title}\n{content}".lower()

    breakdown: Dict[str, int] = {"企業インパクト": 0, "技術革新": 0, "市場影響": 0, "技術的価値": 0}

    # Base points
    if _contains_any(text, _COMPANIES):
        breakdown["企業インパクト"] += 3
    if _contains_any(text, _LAUNCH_TERMS) and _contains_any(text, _MODEL_TERMS):
        breakdown["技術革新"] += 3
    if _contains_any(text, _MARKET_TERMS):
        breakdown["市場影響"] += 2
    if _contains_any(text, _TECH_TERMS):
        breakdown["技術的価値"] += 2

    score = sum(breakdown.values())

    # Bonuses
    if _money_over_100m(text):
        score += 1
    if _contains_any(text, ["today", "available now", "available today", "rolling out", "now available", "ships today"]):
        score += 1
    if ("japan" in text) or ("japanese" in text) or ("日本" in text):
        score += 1

    # Penalties
    if _contains_any(text, _RUMOR_TERMS):
        score -= 2
    if published_iso:
        try:
            dt = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - dt).days
            if days > 7:
                score -= 1
        except Exception:
            pass

    # Normalize 0..10
    score = max(0, min(10, score))

    # Primary category: pick the one with highest base
    primary = max(breakdown.items(), key=lambda kv: kv[1])[0] if any(v > 0 for v in breakdown.values()) else "その他"
    return score, primary, breakdown


