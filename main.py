import json
import os
import argparse
import email.utils
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional

from dotenv import load_dotenv

from fetch_articles import fetch_rss_articles, deduplicate
from translate import translate_text
from summarize import summarize
from save_notion import save_to_notion, url_exists_in_notion
from notify_slack import send_to_slack


def _parse_to_utc(dt_str: str) -> Optional[datetime]:
    if not dt_str:
        return None
    # Try ISO8601 first
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # Try RFC 2822 (e.g., Mon, 24 Jun 2024 15:00:00 +0000)
    try:
        dt2 = email.utils.parsedate_to_datetime(dt_str)
        if dt2 is None:
            return None
        if dt2.tzinfo is None:
            dt2 = dt2.replace(tzinfo=timezone.utc)
        return dt2.astimezone(timezone.utc)
    except Exception:
        return None


def _load_last_processed() -> Optional[datetime]:
    try:
        with open("last_processed.json", "r") as f:
            data = json.load(f)
            dt_str = data.get("last_processed_datetime")
            if dt_str:
                return datetime.fromisoformat(dt_str)
    except Exception:
        pass
    return None


def _save_last_processed(dt: datetime) -> None:
    try:
        with open("last_processed.json", "w") as f:
            json.dump({"last_processed_datetime": dt.isoformat()}, f)
    except Exception as e:
        print(f"Failed to save last processed datetime: {e}")


def run_pipeline(
    sources_path: str = "rss_sources.json",
    slack_channel: str = "#ai-速報",
    limit: int | None = None,
    no_slack: bool = False,
    today_only: bool = False,
    summary_max_chars: int = 300,
    summary_min_chars: int = 160,
    summary_max_sentences: int = 4,
) -> List[Dict[str, str]]:
    with open(sources_path, "r", encoding="utf-8") as f:
        rss_sources = json.load(f)

    articles = deduplicate(fetch_rss_articles(rss_sources))

    # Load last processed datetime
    last_processed = _load_last_processed()
    cutoff_datetime = last_processed
    
    # If no last_processed, use 24 hours ago as cutoff
    if cutoff_datetime is None:
        cutoff_datetime = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # Track the latest article datetime
    latest_article_dt = None
    
    # Filter articles based on cutoff datetime
    filtered = []
    for a in articles:
        dt = _parse_to_utc(a.get("published", ""))
        if dt and dt > cutoff_datetime:
            a["published"] = dt.isoformat()
            filtered.append(a)
            if latest_article_dt is None or dt > latest_article_dt:
                latest_article_dt = dt
    articles = filtered

    # Additional filter for today only mode
    if today_only:
        jst = ZoneInfo("Asia/Tokyo")
        start_of_today_jst = datetime.now(jst).replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_today_utc = start_of_today_jst.astimezone(timezone.utc)
        filtered = []
        for a in articles:
            dt = _parse_to_utc(a.get("published", ""))
            if dt and dt >= start_of_today_utc:
                filtered.append(a)
        articles = filtered

    if limit is not None:
        articles = articles[:limit]

    processed: List[Dict[str, str]] = []

    for article in articles:
        title = article.get("title", "")
        link = article.get("link", "")
        published = article.get("published", "")
        content = article.get("content", "") or title

        # Skip if URL already exists in Notion
        if url_exists_in_notion(link):
            continue

        ja_title = translate_text(title)
        summary_ja = summarize(
            translate_text(content),
            max_chars=summary_max_chars,
            min_chars=summary_min_chars,
            max_sentences=summary_max_sentences,
        )

        save_to_notion(ja_title, link, summary_ja, published)
        if not no_slack:
            send_to_slack(slack_channel, ja_title, link, summary_ja)

        processed.append(
            {
                "title_ja": ja_title,
                "url": link,
                "summary_ja": summary_ja,
                "published": published,
            }
        )

    # Save the latest processed datetime
    if latest_article_dt:
        _save_last_processed(latest_article_dt)

    return processed


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-slack", action="store_true")
    parser.add_argument("--today-only", action="store_true")
    parser.add_argument("--slack-channel", type=str, default="#ai-速報")
    parser.add_argument("--summary-max-chars", type=int, default=400)
    parser.add_argument("--summary-min-chars", type=int, default=300)
    parser.add_argument("--summary-max-sentences", type=int, default=4)
    args = parser.parse_args()
    run_pipeline(
        limit=args.limit,
        no_slack=args.no_slack,
        today_only=args.today_only,
        slack_channel=args.slack_channel,
        summary_max_chars=args.summary_max_chars,
        summary_min_chars=args.summary_min_chars,
        summary_max_sentences=args.summary_max_sentences,
    ) 