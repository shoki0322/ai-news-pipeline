import os
import re
from typing import Optional, List

try:
    from slack_sdk import WebClient  # type: ignore
except Exception:
    WebClient = None  # type: ignore


CHANNEL_ID_RE = re.compile(r"^[CG][A-Z0-9]+$")

# Global round-robin pool for multiple bot tokens
_CLIENTS: List["WebClient"] = []
_CLIENT_INDEX: int = 0


def _initialize_clients_from_env() -> None:
    global _CLIENTS
    if WebClient is None:
        return
    if _CLIENTS:
        return

    # Prefer multiple tokens if provided
    raw_multi = os.getenv("SLACK_BOT_TOKENS")
    tokens: List[str] = []
    if raw_multi:
        tokens = [t.strip() for t in raw_multi.split(",") if t.strip()]
    else:
        single = os.getenv("SLACK_BOT_TOKEN")
        if single:
            tokens = [single.strip()]

    for t in tokens:
        try:
            _CLIENTS.append(WebClient(token=t))
        except Exception as e:
            print(f"Failed to initialize Slack client for one token: {e}")


def _get_slack_client() -> Optional["WebClient"]:
    global _CLIENT_INDEX
    _initialize_clients_from_env()
    if not _CLIENTS:
        return None
    # Round-robin selection
    client = _CLIENTS[_CLIENT_INDEX % len(_CLIENTS)]
    _CLIENT_INDEX = (_CLIENT_INDEX + 1) % len(_CLIENTS)
    return client


def _resolve_channel_id(client: "WebClient", channel: str) -> Optional[str]:
    if CHANNEL_ID_RE.match(channel):
        return channel
    name = channel.lstrip("#").strip()
    # 1) Env override
    env_override = os.getenv("SLACK_CHANNEL_ID")
    if env_override and CHANNEL_ID_RE.match(env_override):
        return env_override
    safe_key = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
    per_name_key = f"SLACK_CHANNEL_ID__{safe_key}"
    env_per_name = os.getenv(per_name_key)
    if env_per_name and CHANNEL_ID_RE.match(env_per_name):
        return env_per_name
    # Paginate through channels
    cursor = None
    try:
        while True:
            resp = client.conversations_list(types="public_channel,private_channel", limit=1000, cursor=cursor)
            for ch in resp.get("channels", []):
                if ch.get("name") == name:
                    return ch.get("id")
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        print(f"Failed to list channels: {e}")
    print(f"Slack channel not found: {channel}")
    return None


def send_to_slack(
    channel: str,
    title: str,
    url: str,
    points: List[str],
    category: Optional[str] = None,
    score: Optional[int] = None,
    source: Optional[str] = None,
    published: Optional[str] = None,
) -> None:
    client = _get_slack_client()
    if not client:
        print("Slack env not set; skipping Slack notification.")
        return

    channel_id = _resolve_channel_id(client, channel)
    if not channel_id:
        return

    # メタ情報
    context_elements: List[dict] = []
    parts = []
    if category:
        parts.append(f"カテゴリ: *{category}*")
    if score is not None:
        parts.append(f"スコア: *{score}* /10")
    if source:
        parts.append(f"メディア: *{source}*")
    if parts:
        context_elements.append({"type": "mrkdwn", "text": " ・ ".join(parts)})

    # 要点を1つの文字列にまとめる
    bullets = "\n".join(points) if points else "（要約なし）"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"🗞️ {title}", "emoji": True}},
    ]
    if context_elements:
        blocks.append({"type": "context", "elements": context_elements})
    # 箇条書きは見本通りに1ブロック化（• 記号、最大5点）
    normalized_points: List[str] = []
    for pt in points[:5]:
        t = pt.strip()
        if not t:
            continue
        # 英字のみの断片は除外
        if re.fullmatch(r"[A-Za-z\s,.]+", t):
            continue
        if t.startswith(("・", "-", "*")):
            t = t.lstrip("・*- ")
        # 1行120字を上限に安全トリム
        if len(t) > 120:
            t = t[:120].rstrip()
        normalized_points.append(f"• {t}")
    bullets_text = "\n".join(normalized_points) if normalized_points else "• 要点なし"
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*要点*\n{bullets_text}"}})
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📖 記事を読む"},
                    "url": url,
                    "style": "primary",
                }
            ],
        }
    )
    # 元メディア/公開日時セクション（指定があれば）
    meta_lines: List[str] = []
    if published:
        meta_lines.append(f"公開日時\n{published}")
    if meta_lines:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n\n".join(meta_lines)}})
    blocks.append({"type": "divider"})

    try:
        resp = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text=f"{title}\n" + bullets,  # Fallback
            unfurl_links=False,
            unfurl_media=False,
        )
        if resp and resp.get("ok"):
            print(f"Slack posted: channel={channel} title={title}")
    except Exception as e:
        print(f"Failed to send Slack message: {e}")


def send_plain_text(channel: str, text: str) -> None:
    """Send a plain text message to Slack without blocks.

    This is used for cases where the caller prepares a fully formatted
    Slack-friendly text (e.g., 4-part summary with fixed labels).
    """
    client = _get_slack_client()
    if not client:
        print("Slack env not set; skipping Slack notification.")
        return
    channel_id = _resolve_channel_id(client, channel)
    if not channel_id:
        return
    try:
        resp = client.chat_postMessage(
            channel=channel_id,
            text=text,
            unfurl_links=False,
            unfurl_media=False,
        )
        if resp and resp.get("ok"):
            print(f"Slack posted (plain): channel={channel}")
    except Exception as e:
        print(f"Failed to send plain Slack message: {e}")


def send_four_part_blocks(
    channel: str,
    title: str,
    yasashii_lines: List[str],
    points: List[str],
    glossary: List[str],
    url: str,
    *,
    source: str | None = None,
    published: str | None = None,
    show_meta: bool = True,
    score_label: str | None = None,
) -> None:
    """Post a 4-part Japanese summary to Slack using block kit.

    - Header with title
    - Section for やさしい要約 (lines joined with \n)
    - Section for ポイント (each line should start with "- ")
    - Section for 用語解説 (each line should start with "- ")
    - Action button linking to the article
    """
    client = _get_slack_client()
    if not client:
        print("Slack env not set; skipping Slack notification.")
        return

    channel_id = _resolve_channel_id(client, channel)
    if not channel_id:
        return

    def _ensure_bullets(lines: List[str]) -> List[str]:
        out: List[str] = []
        for ln in lines:
            t = (ln or "").strip()
            if not t:
                continue
            if not t.startswith("- "):
                t = "- " + t.lstrip("・*- ")
            out.append(t)
        return out

    points_fmt = _ensure_bullets(points)[:5]
    glossary_fmt = _ensure_bullets(glossary)[:6]
    yasashii_text = "\n".join([ln.strip() for ln in yasashii_lines if ln.strip()])
    points_text = "\n".join(points_fmt) if points_fmt else "- 要点なし"
    glossary_text = "\n".join(glossary_fmt) if glossary_fmt else "- 用語なし"

    blocks: List[dict] = []
    if show_meta and (source or published or score_label):
        meta_parts: list[str] = []
        if source:
            meta_parts.append(f"元メディア: *{source}*")
        if published:
            meta_parts.append(f"公開: *{published}*")
        if score_label:
            meta_parts.append(f"ニュース性: *{score_label}*")
        if meta_parts:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " ・ ".join(meta_parts)}]})

    blocks.extend([
        {"type": "section", "text": {"type": "mrkdwn", "text": f"【タイトル】\n*{title[:150]}*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"【やさしい要約】\n{yasashii_text}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"【ポイント】\n{points_text}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"【用語解説】\n{glossary_text}"}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📖 記事を読む"},
                    "url": url,
                    "style": "primary",
                }
            ],
        },
        {"type": "divider"},
    ])

    try:
        resp = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text=title,
            unfurl_links=False,
            unfurl_media=False,
        )
        if resp and resp.get("ok"):
            print(f"Slack posted (blocks): channel={channel} title={title[:40]}")
    except Exception as e:
        print(f"Failed to send four-part blocks: {e}")
