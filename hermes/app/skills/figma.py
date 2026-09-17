from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

import httpx

from app import config, http_client
from app.skills.llm import generate_text
from app.skills.loader import load_instructions

logger = logging.getLogger(__name__)


class FigmaError(Exception):
    pass


class FigmaBadUrlError(FigmaError):
    pass


def generate_guide(
    figma_url: str,
    figma_token: str = "",
    language: str = "ru",
    detail_level: str = "brief",
    audience: str = "user",
) -> str:
    token = figma_token or config.FIGMA_TOKEN
    file_id = extract_file_id(figma_url)
    with FigmaClient() as figma:
        data = figma.get_file(file_id, token)
    filtered = filter_figma_json(data)
    prompt = build_prompt(filtered, language=language, detail_level=detail_level, audience=audience)
    output = generate_text([{"role": "user", "content": prompt}], temperature=config.LLM_TEMPERATURE, max_tokens=config.LLM_MAX_TOKENS)
    markdown, _ = parse_llm_output(output)
    return markdown


def extract_file_id(value: str) -> str:
    if not value:
        raise FigmaBadUrlError("URL is empty")
    raw = value.strip()
    if re.fullmatch(r"[A-Za-z0-9]{10,}", raw):
        return raw
    match = re.search(r"https?://(?:www\.)?figma\.com/(?:file|proto|design)/([A-Za-z0-9]+)", raw)
    if match:
        return match.group(1)
    raise FigmaBadUrlError("Cannot extract file id from URL")


class FigmaClient:
    def __init__(self, base_url: str = "", timeout: float | None = None) -> None:
        self._client = httpx.Client(
            base_url=base_url or config.FIGMA_API_BASE,
            timeout=timeout or config.REQUEST_TIMEOUT,
        )

    def __enter__(self) -> "FigmaClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_file(self, file_id: str, token: str) -> dict:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = http_client.httpx_get(self._client, f"/files/{file_id}", headers=headers)
        if response.status_code in (401, 403) and token:
            headers["X-FIGMA-TOKEN"] = token
            response = http_client.httpx_get(self._client, f"/files/{file_id}", headers=headers)
        if response.status_code == 404:
            raise FigmaError("Figma-файл не найден")
        if response.status_code == 429:
            raise FigmaError("Превышен лимит запросов Figma")
        if response.status_code in (401, 403):
            raise FigmaError("Ошибка авторизации Figma")
        if response.status_code >= 400:
            raise FigmaError(f"Ошибка Figma API: {response.status_code}")
        return response.json()

    def close(self) -> None:
        self._client.close()


KEYWORDS = {
    "button": ["button", "btn"],
    "input": ["input", "textfield", "text field", "textbox", "field", "search"],
    "header": ["header", "title", "heading", "h1", "h2", "h3"],
    "link": ["link", "href", "url"],
    "navigation": ["nav", "tab", "menu", "breadcrumb", "back", "next", "continue"],
    "error": ["error", "alert", "warning", "empty", "success"],
}


def filter_figma_json(figma_json: dict[str, Any]) -> dict[str, Any]:
    document = figma_json.get("document") or {}
    file_name = figma_json.get("name")
    pages = [child for child in _iter_children(document) if child.get("type") == "CANVAS"]
    if not pages:
        pages = [document]

    screens: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages, start=1):
        for frame in _iter_screen_frames(page):
            screens.append(_screen_from_frame(frame, page=page.get("name"), page_index=page_index))

    if not screens:
        screens.append(_screen_from_frame(document, page=document.get("name"), page_index=1))

    screens = _sort_screens(screens)
    order = {screen["id"]: index for index, screen in enumerate(screens, start=1) if screen.get("id")}
    for index, screen in enumerate(screens, start=1):
        screen["order"] = index

    flows = _collect_flows(screens, order)
    return {
        "file_name": file_name,
        "mode": "wireflow" if len(screens) > 1 or flows else "single_screen",
        "screens": screens,
        "flows": flows,
    }


def build_prompt(filtered_json: dict, language: str, detail_level: str, audience: str) -> str:
    limited_json = _limit_elements(filtered_json, per_screen_limit=16, screen_limit=12)
    template = load_instructions("figma-guide")
    return (
        template.replace("{{LANGUAGE}}", language)
        .replace("{{DETAIL_LEVEL}}", detail_level)
        .replace("{{AUDIENCE}}", audience)
        .replace("{{DATA}}", json.dumps(limited_json, ensure_ascii=False))
    )


def parse_llm_output(text: str) -> tuple[str, dict]:
    cleaned = text
    while "<think>" in cleaned and "</think>" in cleaned:
        start = cleaned.find("<think>")
        end = cleaned.find("</think>", start)
        if end == -1:
            break
        cleaned = cleaned[:start] + cleaned[end + len("</think>") :]
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    if "JSON:" not in cleaned:
        return cleaned.strip(), {"markdown": cleaned.strip()}
    markdown_part, json_part = cleaned.split("JSON:", 1)
    markdown = markdown_part.replace("MARKDOWN:", "").strip()
    try:
        return markdown, json.loads(json_part.strip())
    except json.JSONDecodeError:
        return markdown, {"markdown": markdown}


def _limit_elements(filtered_json: dict, per_screen_limit: int = 16, screen_limit: int = 12) -> dict:
    if not filtered_json or "screens" not in filtered_json:
        return filtered_json
    kept_screens = filtered_json.get("screens", [])[:screen_limit]
    kept_ids = {screen.get("id") for screen in kept_screens}
    trimmed = {
        "file_name": filtered_json.get("file_name"),
        "mode": filtered_json.get("mode"),
        "screens": [],
        "flows": [
            flow
            for flow in filtered_json.get("flows", [])
            if flow.get("from") in kept_ids and flow.get("to") in kept_ids
        ],
    }
    for screen in kept_screens:
        screen_copy = {
            "id": screen.get("id"),
            "order": screen.get("order"),
            "name": screen.get("name"),
            "page": screen.get("page"),
            "type": screen.get("type"),
            "position": screen.get("position"),
            "elements": screen.get("elements", [])[:per_screen_limit],
        }
        trimmed["screens"].append(screen_copy)
    return trimmed


def _iter_screen_frames(page: dict[str, Any]) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for child in _iter_children(page):
        if child.get("type") in {"FRAME", "COMPONENT", "INSTANCE"}:
            frames.append(child)
        elif child.get("type") in {"SECTION", "GROUP"}:
            frames.extend(_iter_screen_frames(child))
    return frames


def _screen_from_frame(frame: dict[str, Any], page: str | None, page_index: int) -> dict[str, Any]:
    return {
        "id": frame.get("id"),
        "name": frame.get("name"),
        "page": page,
        "page_index": page_index,
        "type": frame.get("type"),
        "position": _position(frame),
        "elements": _collect_elements(frame),
        "connections": _extract_connections(frame),
    }


def _sort_screens(screens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        screens,
        key=lambda screen: (
            screen.get("page_index") or 0,
            _numeric_prefix(screen.get("name")),
            (screen.get("position") or {}).get("y", 0),
            (screen.get("position") or {}).get("x", 0),
            screen.get("name") or "",
        ),
    )


def _numeric_prefix(value: str | None) -> int:
    match = re.match(r"\s*(\d+)", value or "")
    return int(match.group(1)) if match else 9999


def _position(node: dict[str, Any]) -> dict[str, float] | None:
    box = node.get("absoluteBoundingBox")
    if not isinstance(box, dict):
        return None
    return {
        "x": float(box.get("x", 0)),
        "y": float(box.get("y", 0)),
        "width": float(box.get("width", 0)),
        "height": float(box.get("height", 0)),
    }


def _extract_connections(node: dict[str, Any]) -> list[dict[str, str]]:
    connections: list[dict[str, str]] = []
    for reaction in node.get("reactions") or []:
        if not isinstance(reaction, dict):
            continue
        action = reaction.get("action") or {}
        if not isinstance(action, dict):
            continue
        destination_id = action.get("destinationId")
        if destination_id:
            connections.append(
                {
                    "trigger": str((reaction.get("trigger") or {}).get("type") or ""),
                    "action": str(action.get("type") or ""),
                    "to": str(destination_id),
                }
            )
    return connections


def _collect_flows(screens: list[dict[str, Any]], order: dict[str, int]) -> list[dict[str, Any]]:
    flows: list[dict[str, Any]] = []
    for screen in screens:
        for connection in screen.get("connections", []):
            to_id = connection.get("to")
            if to_id not in order:
                continue
            flows.append(
                {
                    "from": screen.get("id"),
                    "from_order": screen.get("order"),
                    "from_name": screen.get("name"),
                    "to": to_id,
                    "to_order": order[to_id],
                    "trigger": connection.get("trigger"),
                    "action": connection.get("action"),
                }
            )
    if flows:
        return flows

    if len(screens) < 2:
        return []
    return [
        {
            "from": screens[index].get("id"),
            "from_order": index + 1,
            "from_name": screens[index].get("name"),
            "to": screens[index + 1].get("id"),
            "to_order": index + 2,
            "trigger": "inferred_order",
            "action": "next_screen",
        }
        for index in range(len(screens) - 1)
    ]


def _normalize_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _detect_kind(node: dict[str, Any]) -> str:
    name = _normalize_name(node.get("name"))
    if node.get("type") == "TEXT":
        return "text"
    for kind, tokens in KEYWORDS.items():
        if any(token in name for token in tokens):
            return kind
    return "component"


def _is_relevant(node: dict[str, Any]) -> bool:
    if node.get("type") == "TEXT":
        return True
    if node.get("reactions"):
        return True
    name = _normalize_name(node.get("name"))
    return any(token in name for tokens in KEYWORDS.values() for token in tokens)


def _iter_children(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    return node.get("children", []) or []


def _collect_elements(node: dict[str, Any]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for child in _iter_children(node):
        if _is_relevant(child):
            item: dict[str, Any] = {"id": child.get("id"), "name": child.get("name"), "type": child.get("type"), "kind": _detect_kind(child)}
            if child.get("type") == "TEXT":
                item["text"] = child.get("characters", "")
            connections = _extract_connections(child)
            if connections:
                item["connections"] = connections
            elements.append(item)
        elements.extend(_collect_elements(child))
    return elements
