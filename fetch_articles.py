import hashlib
import re
import html
from datetime import datetime, timezone
from typing import List, Dict
import urllib.request

import feedparser
from urllib.parse import urlparse
def _normalize_source_name(feed_url: str, candidate: str) -> str:
    """Return a stable, human-friendly source name.
    Prefer known mappings. If the feed-provided title is too generic, fall back to domain.
    """
    try:
        p = urlparse(feed_url)
        host = (p.hostname or feed_url).lower().replace("www.", "")
    except Exception:
        host = feed_url

    generic = {"ai", "blog", "news"}
    if not candidate or len(candidate.strip()) < 4 or candidate.strip().lower() in generic:
        candidate = ""

    # Known host mappings
    domain_map = {
        "openai.com": "OpenAI Blog",
        "blog.google": "Google AI Blog",
        "deepmind.google": "Google DeepMind Blog",
        "huggingface.co": "Hugging Face Blog",
        "blogs.microsoft.com": "Microsoft Blog",
        "artificialintelligence-news.com": "AI News",
        "venturebeat.com": "VentureBeat",
        "marktechpost.com": "MarkTechPost",
        "towardsdatascience.com": "Towards Data Science",
        "machinelearningmastery.com": "Machine Learning Mastery",
    }
    # Special-case Google AI path
    try:
        if host == "blog.google" and "/technology/ai" in urlparse(feed_url).path:
            return "Google AI Blog"
    except Exception:
        pass

    if host in domain_map:
        return domain_map[host]
    # Fallback to feed-provided candidate if reasonable; otherwise use hostname
    return candidate or host


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

    # Set a user agent to avoid being blocked
    feedparser.USER_AGENT = "Mozilla/5.0 (compatible; AI-News-Pipeline/1.0; +http://example.com/bot)"

    for url in urls:
        try:
            # Create a request with custom headers
            request = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; AI-News-Pipeline/1.0; +http://example.com/bot)',
                    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                }
            )

            # Try to fetch the feed with timeout
            try:
                response = urllib.request.urlopen(request, timeout=10)
                feed = feedparser.parse(response.read())
            except (urllib.error.HTTPError, urllib.error.URLError) as e:
                print(f"Failed to fetch {url}: {e}")
                continue
            except Exception as e:
                print(f"Unexpected error fetching {url}: {e}")
                continue

            # Check if feed parsing was successful
            if hasattr(feed, 'bozo_exception') and feed.bozo_exception:
                print(f"Warning: Feed parsing error for {url}: {feed.bozo_exception}")
                # Try to continue if there are still entries
                if not feed.entries:
                    continue
            # Determine human-readable source name from feed metadata or fallback to domain
            try:
                source_title = getattr(getattr(feed, "feed", {}), "title", "")
            except Exception:
                source_title = ""
            source_name = _normalize_source_name(url, source_title)
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
                        "source": source_name,
                    }
                )
        except Exception as e:
            print(f"Error processing feed {url}: {e}")
            continue
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