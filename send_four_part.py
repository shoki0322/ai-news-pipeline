import argparse
import os
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv
from openai import OpenAI

from notify_slack import send_plain_text, send_four_part_blocks
from score import score_article


FOUR_PART_PROMPT = """
以下の英語記事を日本語でSlack投稿用に要約してください。出力はこの指示に従った本文のみ。

出力形式（必ずこの順・ラベル固定・空行なし）：
【タイトル】
記事の核心を表す短い見出し（20字以内目安）
【やさしい要約】
専門用語を避け、誰でも理解できる平易な日本語で2〜3文。最初に「何が起きたか」、次に「なぜ重要か／何ができるか」を簡潔に述べる。各文は200〜400字目安で改行し、段落間に空行は入れない。
【ポイント】
重要点を3〜5個の箇条書き。「- 」で開始。各項目に必ず具体情報（数値・モデル名・日時・提供形態・対応範囲など）を1つ以上含める。重複や言い換えは避け、観点を分ける（技術/用途/提供/制約/比較など）。疑問文や推測語（〜ですか、かも）は使用しない。各項目は最大120字。
【用語解説】
「ポイント」に登場した専門用語のみを「- 用語名：一言説明」で解説。該当がない場合は記事の主要キーワード1〜2個を選び同形式で補足。

制約：
- 全体500文字以内（文字数配分はポイントに厚く、やさしい要約は簡潔に）
- エンジニア以外も理解できる表現
- 固有名詞・製品名・API名は原表記（半角英数）で維持
- プレーンテキストのみ（Markdown記法・絵文字・顔文字・コードブロック禁止）
- 箇条書きは必ず「- 」で開始
 - 文章は途中で語が切れないように整形し、断片的な英単語や意味不明な断片を出力しない
""".strip()


def extract(url: str) -> tuple[str, str, str | None, str | None, str]:
    """Fetch URL and return (title_en, content_en, source_name, published, domain)."""
    resp = requests.get(
        url,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
        },
    )
    resp.raise_for_status()
    html = resp.text
    try:
        doc = Document(html)
        content_html = doc.summary()
        title_guess = doc.short_title() or None
        soup = BeautifulSoup(content_html, "html.parser")
        title = title_guess or (soup.title.get_text(strip=True) if soup.title else url)
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else url
    for tag in soup(["script", "style", "noscript", "header", "footer", "svg", "img", "aside", "nav"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    # Heuristics: remove common noise tokens from some blogs
    for noise in [
        "Copy Code",
        "Copied",
        "Use a different Browser",
        "Share on",
        "Read more",
    ]:
        text = text.replace(noise, " ")
    text = " ".join(text.split())
    # meta
    og_site = soup.find("meta", property="og:site_name")
    og_pub = soup.find("meta", property="article:published_time") or soup.find("meta", attrs={"name": "pubdate"})
    source = og_site.get("content").strip() if og_site and og_site.get("content") else None
    published = og_pub.get("content").strip() if og_pub and og_pub.get("content") else None
    try:
        domain = urlparse(url).hostname or ""
        domain = domain.replace("www.", "")
    except Exception:
        domain = ""
    return title, text, source, published, domain


def summarize_4o(title_en: str, content_en: str, url: str) -> str:
    """Use GPT-4o to produce the 4-part Slack-ready text."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    client = OpenAI(api_key=api_key)
    user = (
        f"{FOUR_PART_PROMPT}\n\n"
        f"【入力（タイトル）】\n{title_en}\n"
        f"【入力（URL）】\n{url}\n"
        f"【入力（本文）】\n{content_en}"
    )
    print("Using OpenAI model: gpt-4o")
    resp = client.chat_completions.create if hasattr(client, "chat_completions") else client.chat.completions.create
    resp = resp(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a concise Japanese news summarizer for Slack."},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
    )
    # OpenAI Python v1 returns resp.choices[0].message.content
    text = getattr(resp.choices[0], "message", resp.choices[0]).content.strip()
    # For verification: log token usage if available
    try:
        usage = getattr(resp, "usage", None)
        if usage:
            print(f"OpenAI usage: prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}")
    except Exception:
        pass
    # Normalize: ensure no extra blank lines and bullets start with "- "
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln != ""]  # remove blank lines
    # enforce bullet prefix
    fixed: list[str] = []
    in_points = False
    for ln in lines:
        if ln.startswith("【ポイント】"):
            in_points = True
            fixed.append(ln)
            continue
        if ln.startswith("【用語解説】"):
            in_points = False
            fixed.append(ln)
            continue
        if in_points and not ln.startswith("- "):
            fixed.append("- " + ln.lstrip("- ・*"))
        else:
            fixed.append(ln)
    return "\n".join(fixed)


def parse_four_part(text: str) -> tuple[str, list[str], list[str], list[str]]:
    """Parse the 4-part formatted text into components.
    Returns: (title, yasashii_lines, points, glossary)
    """
    lines = [ln.strip() for ln in text.splitlines()]
    title = ""
    yasashii: list[str] = []
    points: list[str] = []
    glossary: list[str] = []
    section = None
    for ln in lines:
        if ln == "【タイトル】":
            section = "title"
            continue
        if ln == "【やさしい要約】":
            section = "yasashii"
            continue
        if ln == "【ポイント】":
            section = "points"
            continue
        if ln == "【用語解説】":
            section = "glossary"
            continue
        if section == "title" and ln:
            title = ln
        elif section == "yasashii" and ln:
            yasashii.append(ln)
        elif section == "points" and ln:
            points.append(ln)
        elif section == "glossary" and ln:
            glossary.append(ln)
    return title, yasashii, points, glossary


def main() -> int:
    try:
        if os.path.exists(".env"):
            load_dotenv(".env")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Summarize an article with GPT-4o into 4-part Slack text and post to Slack.")
    ap.add_argument("url", help="Article URL")
    ap.add_argument("--channel", default=os.getenv("SLACK_CHANNEL", "#ai-news-test"))
    args = ap.parse_args()

    title_en, content_en, source, published, domain = extract(args.url)
    summary_text = summarize_4o(title_en, content_en, args.url)
    # Parse into blocks; if invalid, do not post (policy: no-GPT-no-post)
    try:
        title_ja, yasashii, points, glossary = parse_four_part(summary_text)
        if title_ja and points:
            # scoring to derive newsness label (2-level: 重要 / 通常)
            score, _, _ = score_article(title_en, content_en, published)
            score_label = "重要" if score >= 6 else "通常"
            media_label = domain or (source or "")
            send_four_part_blocks(
                args.channel,
                title_ja,
                yasashii,
                points,
                glossary,
                args.url,
                source=media_label,
                published=published,
                score_label=score_label,
            )
            print("Sent summary to Slack (blocks).")
            return 0
        else:
            print("GPT output invalid (missing title or points); not posting.")
            return 1
    except Exception as e:
        print("Parse/send error; not posting:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
