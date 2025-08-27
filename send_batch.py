import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict

from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from fetch_articles import fetch_rss_articles, deduplicate
from translate import translate_headline
from summarize import summarize
from notify_slack import send_to_slack
from main import _parse_to_utc
from score import score_article


def _load_articles() -> List[Dict[str, str]]:
    with open("rss_sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)
    return deduplicate(fetch_rss_articles(sources))


def _filter_by_jst_date(articles: List[Dict[str, str]], yyyy_mm_dd: str) -> List[Dict[str, str]]:
    jst = ZoneInfo("Asia/Tokyo")
    try:
        target = datetime.strptime(yyyy_mm_dd, "%Y-%m-%d").replace(tzinfo=jst)
    except Exception as e:
        raise ValueError(f"Invalid --date format, expected YYYY-MM-DD: {e}")

    start_utc = target.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(days=1)

    filtered: List[Dict[str, str]] = []
    for a in articles:
        dt = _parse_to_utc(a.get("published", ""))
        if dt and start_utc <= dt < end_utc:
            a_copy = dict(a)
            a_copy["_dt"] = dt
            filtered.append(a_copy)

    filtered.sort(key=lambda x: x["_dt"])  # chronological order
    return filtered


def _safe_translate_and_summarize(title: str, content: str, max_chars: int, min_chars: int, max_sentences: int) -> tuple[str, str]:
    ja_title = title
    summary_ja = content
    try:
        ja_title = translate_headline(title)
    except Exception:
        pass
    try:
        summary_ja = summarize(content, max_chars=max_chars, min_chars=min_chars, max_sentences=max_sentences)
    except Exception:
        summary_ja = summarize(content, max_chars=max_chars, min_chars=min_chars, max_sentences=max_sentences)
    return ja_title, summary_ja


def main() -> int:
    # Load .env if present
    try:
        if os.path.exists(".env"):
            load_dotenv(dotenv_path=".env")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Send filtered AI news items to Slack for a specific JST date.")
    parser.add_argument("--date", required=True, help="Target date in JST, format YYYY-MM-DD (e.g., 2025-08-19)")
    parser.add_argument("--channel", default=os.getenv("SLACK_CHANNEL", "#ai-news"), help="Slack channel name (#ai-news) or ID (CXXXX…). Defaults to env SLACK_CHANNEL or #ai-news")
    parser.add_argument("--sleep", type=float, default=1.2, help="Seconds to sleep between Slack posts to avoid rate limits")
    parser.add_argument("--limit", type=int, default=None, help="Max number of items to send")
    parser.add_argument("--summary-max-chars", type=int, default=300)
    parser.add_argument("--summary-min-chars", type=int, default=220)
    parser.add_argument("--summary-max-sentences", type=int, default=4)
    args = parser.parse_args()

    articles = _load_articles()
    targets = _filter_by_jst_date(articles, args.date)

    if args.limit is not None:
        targets = targets[: args.limit]
    print(f"Preparing to send {len(targets)} messages to {args.channel} for JST {args.date}")
    sent = 0
    for idx, a in enumerate(targets, start=1):
        title = a.get("title", "")
        link = a.get("link", "")
        content = a.get("content", "") or title
        source = a.get("source", "")
        try:
            ja_title, summary_ja = _safe_translate_and_summarize(
                title,
                content,
                max_chars=args.summary_max_chars,
                min_chars=args.summary_min_chars,
                max_sentences=args.summary_max_sentences,
            )
            if source:
                ja_title = f"[{source}] {ja_title}"
            # 箇条書き要点に切り替え
            points = summarize(content)
            s, primary_cat, _ = score_article(title, content, a.get("published", ""))
            send_to_slack(args.channel, ja_title, link, points, primary_cat, s)
            sent += 1
            print(f"[{idx}/{len(targets)}] Sent: {ja_title[:60]} …")
            time.sleep(args.sleep)
        except Exception as e:
            print(f"[{idx}/{len(targets)}] Failed: {e}")

    print(f"Done. Attempted {len(targets)} sends, success {sent}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


