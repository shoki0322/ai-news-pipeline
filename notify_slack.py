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
    # 1) Env override for cases without conversations:read scope
    # Global override
    env_override = os.getenv("SLACK_CHANNEL_ID")
    if env_override and CHANNEL_ID_RE.match(env_override):
        return env_override
    # Per-name override: SLACK_CHANNEL_ID__<NAME> (uppercase, non-alnum -> _)
    safe_key = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
    per_name_key = f"SLACK_CHANNEL_ID__{safe_key}"
    env_per_name = os.getenv(per_name_key)
    if env_per_name and CHANNEL_ID_RE.match(env_per_name):
        return env_per_name
    # Paginate through channels the bot can see (public + private it belongs to)
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
    print(f"Slack channel not found or bot not a member: {channel}. Invite the bot to the channel or provide a channel ID.")
    return None


def send_to_slack(channel: str, title: str, url: str, summary: str) -> None:
    client = _get_slack_client()
    if not client:
        print("Slack env not set; skipping Slack notification.")
        return

    channel_id = _resolve_channel_id(client, channel)
    if not channel_id:
        return

    # Format with blocks for better structure and clear separators
    blocks = [
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📰 *{title}*\n\n{summary}\n\n<{url}|📖 記事を読む>"
            }
        },
        {"type": "divider"},
    ]
    
    try:
        # Send only the formatted message with embedded link
        resp = client.chat_postMessage(
            channel=channel_id,
            blocks=blocks,
            text=f"{title}\n\n{summary}",  # Fallback text without URL
            unfurl_links=False  # Keep clean format
        )
        
        if resp and resp.get("ok"):
            print(f"Slack posted: channel={channel} title={title[:40]}")
    except Exception as e:
        print(f"Failed to send Slack message: {e}") 