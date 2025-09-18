import json
import os
import argparse
import email.utils
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional

from dotenv import load_dotenv

from fetch_articles import fetch_rss_articles, deduplicate
from save_notion import save_to_notion, url_exists_in_notion
from notify_slack import send_four_part_blocks
try:
    # Utilities for GPT-4o 4-part summarization and parsing
    from send_four_part import summarize_4o, parse_four_part
except Exception:
    summarize_4o = None  # type: ignore
    parse_four_part = None  # type: ignore
from score import score_article


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
    slack_channel: str = "#ai-news",
    limit: int | None = None,
    no_slack: bool = False,
    today_only: bool = False,
    summary_max_chars: int = 300,
    summary_min_chars: int = 220,
    summary_max_sentences: int = 4,
    four_part: bool = True,
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
        source = article.get("source", "")

        # Skip if URL already exists in Notion
        if url_exists_in_notion(link):
            continue

        if four_part and summarize_4o and parse_four_part:
            try:
                # Use GPT-4o to produce 4-part text, then parse and send as blocks
                fp_text = summarize_4o(title, content, link)
                title_ja, yasashii, points, glossary = parse_four_part(fp_text)
                # Save a compact body to Notion: combine やさしい要約 + ポイント
                notion_body = "\n".join(yasashii + points)
                save_to_notion(title_ja or title, link, notion_body or "(no summary)", published)
                if not no_slack:
                    send_four_part_blocks(slack_channel, title_ja or title, yasashii, points, glossary, link)
                processed.append(
                    {
                        "title_ja": title_ja or title,
                        "url": link,
                        "summary_ja": notion_body,
                        "published": published,
                        "source": source,
                    }
                )
                continue
            except Exception as e:
                print(f"four_part mode failed for one article, falling back to classic summary: {e}")
                # Fall through to classic pipeline below
        # Classic pipeline (headline translation + bullet summarize)
        try:
            from translate import translate_headline
            from summarize import summarize as classic_summarize
            from notify_slack import send_to_slack
        except Exception as ie:
            print(f"Failed to import classic pipeline components: {ie}")
            continue
        ja_title = translate_headline(title)
        if source:
            ja_title = f"[{source}] {ja_title}"
        points = classic_summarize(content)
        s, primary_cat, _ = score_article(title, content, published)
        save_to_notion(ja_title, link, "\n".join(points), published)
        if not no_slack:
            send_to_slack(slack_channel, ja_title, link, points, primary_cat, s)
        processed.append(
            {
                "title_ja": ja_title,
                "url": link,
                "summary_ja": "\n".join(points),
                "published": published,
                "source": source,
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
    parser.add_argument("--slack-channel", type=str, default=os.getenv("SLACK_CHANNEL", "#ai-news"))
    parser.add_argument("--summary-max-chars", type=int, default=300)
    parser.add_argument("--summary-min-chars", type=int, default=220)
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
        four_part=True,
    )
