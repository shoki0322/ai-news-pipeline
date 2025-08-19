import os
import re
from urllib.parse import urlparse
from typing import Optional, Dict, Any, Tuple

try:
    from notion_client import Client  # type: ignore
except Exception:
    Client = None  # type: ignore


UUID_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _normalize_database_id(raw: str) -> str:
    if raw.startswith("http://") or raw.startswith("https://"):
        p = urlparse(raw)
        seg = p.path.rstrip("/").split("/")[-1]
    else:
        seg = raw
    seg = seg.split("?")[0].split("#")[0]
    if UUID_RE.match(seg):
        return f"{seg[0:8]}-{seg[8:12]}-{seg[12:16]}-{seg[16:20]}-{seg[20:32]}"
    return seg


def _get_notion_client() -> Optional["Client"]:
    token = os.getenv("NOTION_TOKEN")
    if not token or Client is None:
        return None
    try:
        return Client(auth=token)
    except Exception as e:
        print(f"Failed to initialize Notion client: {e}")
        return None


def _detect_properties(notion: "Client", database_id: str) -> Dict[str, Any]:
    return notion.databases.retrieve(database_id).get("properties", {})


def _find_title_prop_name(properties: Dict[str, Any]) -> Optional[str]:
    for name, schema in properties.items():
        if schema.get("type") == "title":
            return name
    return None


def _find_rich_text_prop_name(properties: Dict[str, Any]) -> Optional[str]:
    for name, schema in properties.items():
        if schema.get("type") == "rich_text":
            return name
    return None


def _find_url_prop_name(properties: Dict[str, Any]) -> Optional[str]:
    if "URL" in properties and properties["URL"].get("type") in {"url", "rich_text"}:
        return "URL"
    for name, schema in properties.items():
        if schema.get("type") == "url":
            return name
    # allow rich_text fallback when no url type exists
    for name, schema in properties.items():
        if schema.get("type") == "rich_text":
            return name
    return None


def _build_properties_payload(notion: "Client", database_id: str, title: str, url: str, summary: str, date_iso: str) -> Dict[str, Any]:
    properties = _detect_properties(notion, database_id)

    title_prop_name = _find_title_prop_name(properties)
    if not title_prop_name:
        raise ValueError("No title property found in Notion database")

    payload: Dict[str, Any] = {
        title_prop_name: {"title": [{"text": {"content": title}}]}
    }

    summary_prop_name = None
    if "Summary" in properties and properties["Summary"].get("type") == "rich_text":
        summary_prop_name = "Summary"
    else:
        summary_prop_name = _find_rich_text_prop_name(properties)
    if summary_prop_name:
        payload[summary_prop_name] = {"rich_text": [{"text": {"content": summary}}]}

    url_prop_name = _find_url_prop_name(properties)
    if url_prop_name:
        if properties[url_prop_name].get("type") == "url":
            payload[url_prop_name] = {"url": url}
        else:
            payload[url_prop_name] = {"rich_text": [{"text": {"content": url}}]}

    if "Date" in properties and properties["Date"].get("type") == "date":
        payload["Date"] = {"date": {"start": date_iso}}
    else:
        for name, schema in properties.items():
            if schema.get("type") == "date":
                payload[name] = {"date": {"start": date_iso}}
                break

    return payload


def url_exists_in_notion(url: str) -> bool:
    database_id_raw = os.getenv("NOTION_DATABASE_ID")
    notion = _get_notion_client()
    if not notion or not database_id_raw:
        return False
    database_id = _normalize_database_id(database_id_raw)

    try:
        properties = _detect_properties(notion, database_id)
        url_prop = _find_url_prop_name(properties)
        if not url_prop:
            return False
        schema_type = properties[url_prop].get("type")
        if schema_type == "url":
            flt = {"property": url_prop, "url": {"equals": url}}
        else:
            flt = {"property": url_prop, "rich_text": {"contains": url}}
        resp = notion.databases.query(database_id=database_id, filter=flt, page_size=1)
        return len(resp.get("results", [])) > 0
    except Exception as e:
        print(f"Failed to query Notion for duplicates: {e}")
        return False


def save_to_notion(title: str, url: str, summary: str, date_iso: str) -> None:
    database_id_raw = os.getenv("NOTION_DATABASE_ID")
    notion = _get_notion_client()

    if not notion or not database_id_raw:
        print("Notion env not set; skipping Notion save.")
        return

    database_id = _normalize_database_id(database_id_raw)

    try:
        properties_payload = _build_properties_payload(notion, database_id, title, url, summary, date_iso)
        notion.pages.create(
            parent={"database_id": database_id},
            properties=properties_payload,
        )
    except Exception as e:
        print(f"Failed to save to Notion: {e}") 