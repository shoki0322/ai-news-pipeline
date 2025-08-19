import os
import re
from typing import Optional

try:
    from slack_sdk import WebClient  # type: ignore
except Exception:
    WebClient = None  # type: ignore


CHANNEL_ID_RE = re.compile(r"^[CG][A-Z0-9]+$")


def _get_slack_client() -> Optional["WebClient"]:
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token or WebClient is None:
        return None
    try:
        return WebClient(token=token)
    except Exception as e:
        print(f"Failed to initialize Slack client: {e}")
        return None


def _resolve_channel_id(client: "WebClient", channel: str) -> Optional[str]:
    if CHANNEL_ID_RE.match(channel):
        return channel
    name = channel.lstrip("#").strip()
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

    # Format with blocks for better structure
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📰 *{title}*\n\n{summary}\n\n<{url}|📖 記事を読む>"
            }
        }
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