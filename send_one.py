import argparse
import os
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup  # lightweight HTML text extraction
from readability import Document

from dotenv import load_dotenv

from translate import translate_headline
from summarize import summarize
from notify_slack import send_to_slack
from score import score_article


def _extract_text_from_url(url: str) -> tuple[str, str, str]:
    resp = requests.get(url, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,ja;q=0.8"
    })
    resp.raise_for_status()
    html = resp.text
    # Try readability to extract main content + better title
    try:
        doc = Document(html)
        content_html = doc.summary()
        title_guess = doc.short_title() or None
        soup = BeautifulSoup(content_html, "html.parser")
        title = title_guess or (soup.title.get_text(strip=True) if soup.title else url)
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
        # Title
        title = soup.title.get_text(strip=True) if soup.title else url
    # Try OpenGraph site_name for better source labeling
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        source = og_site.get("content").strip()
    else:
        source = (urlparse(url).hostname or url).replace("www.", "")
    # Main text
    for tag in soup(["script", "style", "noscript", "header", "footer", "svg", "img", "aside", "nav"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return title, text, source


def main() -> int:
    try:
        if os.path.exists(".env"):
            load_dotenv(".env")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Send a single URL to Slack with summarized Japanese text.")
    ap.add_argument("url", help="Article URL")
    ap.add_argument("--channel", default=os.getenv("SLACK_CHANNEL", "#ai-news"))
    ap.add_argument("--summary-max-chars", type=int, default=300)
    ap.add_argument("--summary-min-chars", type=int, default=220)
    ap.add_argument("--summary-max-sentences", type=int, default=4)
    args = ap.parse_args()

    title_en, content_en, source = _extract_text_from_url(args.url)
    ja_title = translate_headline(title_en)
    summary_ja = summarize(content_en, max_chars=args.summary_max_chars, min_chars=args.summary_min_chars, max_sentences=args.summary_max_sentences)
    if source:
        ja_title = f"[{source}] {ja_title}"
    s, primary_cat, _ = score_article(title_en, content_en, None)
    send_to_slack(args.channel, ja_title, args.url, summary_ja, primary_cat, s)
    print("Posted:", ja_title[:80])
    return 0


if __name__ == "__main__":
    sys.exit(main())


