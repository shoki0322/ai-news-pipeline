import hashlib
import re
import html
from datetime import datetime, timezone
from typing import List, Dict

import feedparser


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", raw)
    # Unescape entities
    text = html.unescape(text)
    # Normalize spaces
    return re.sub(r"\s+", " ", text).strip()


def _extract_entry_content(entry) -> str:
    # Prefer content.value
    try:
        contents = entry.get("content")
        if contents and isinstance(contents, list) and contents[0].get("value"):
            return _strip_html(contents[0]["value"])[:2000]
    except Exception:
        pass
    # Fallback to summary
    if entry.get("summary"):
        return _strip_html(entry.get("summary"))[:2000]
    # Fallback to description
    if entry.get("description"):
        return _strip_html(entry.get("description"))[:2000]
    # Last resort: title
    return _strip_html(getattr(entry, "title", ""))[:500]


def fetch_rss_articles(urls: List[str]) -> List[Dict[str, str]]:
    articles: List[Dict[str, str]] = []
    for url in urls:
        feed = feedparser.parse(url)
        for entry in getattr(feed, "entries", []):
            published_raw = entry.get("published") or entry.get("updated")
            if published_raw:
                try:
                    # feedparser may parse .published_parsed as a time.struct_time
                    if getattr(entry, "published_parsed", None):
                        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                        published_iso = dt.isoformat()
                    else:
                        published_iso = published_raw
                except Exception:
                    published_iso = datetime.now(timezone.utc).isoformat()
            else:
                published_iso = datetime.now(timezone.utc).isoformat()

            articles.append(
                {
                    "title": getattr(entry, "title", ""),
                    "link": getattr(entry, "link", ""),
                    "published": published_iso,
                    "content": _extract_entry_content(entry),
                }
            )
    return articles


def deduplicate(articles: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen_hashes = set()
    unique_articles: List[Dict[str, str]] = []

    for article in articles:
        link = article.get("link", "")
        link_hash = hashlib.md5(link.encode("utf-8")).hexdigest()
        if link_hash in seen_hashes:
            continue
        seen_hashes.add(link_hash)
        unique_articles.append(article)

    return unique_articles 