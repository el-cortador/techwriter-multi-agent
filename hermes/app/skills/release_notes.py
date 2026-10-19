from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth

from app import config, http_client
from app.skills.llm import generate_text
from app.skills.loader import load_instructions

logger = logging.getLogger(__name__)

OutputType = Literal["release_notes", "changelog"]
_GITHUB_API = "https://api.github.com"


class ReleaseNotesError(Exception):
    pass


def generate_github(
    repository: str,
    date_from: str,
    date_to: str,
    branch: str = "",
    output_type: OutputType = "release_notes",
) -> str:
    owner, repo = _parse_repository(repository)
    since, until, display_from, display_to = _date_range(date_from, date_to)
    commits = _get_commits(owner, repo, since, until, branch)
    if not commits:
        return "За указанный период коммитов не найдено."
    prompt = _github_prompt(owner, repo, display_from, display_to, commits, output_type=output_type)
    return _llm_generate(prompt)


def generate_jira(
    urls: list[str],
    output_type: OutputType = "release_notes",
    release_notes_text: str = "",
) -> str:
    urls = [url for url in urls if url.strip()]
    if not urls:
        raise ReleaseNotesError("Укажите хотя бы один URL задачи")
    jira = JiraClient()
    issues = jira.get_issues(urls)
    if not issues:
        raise ReleaseNotesError("Не удалось распознать Jira URL")
    if not _looks_like_release_notes(release_notes_text):
        release_notes_text = ""
    logger.info(
        "[release-notes] fetched jira issues=%d output_type=%s mapping=%s",
        len(issues),
        output_type,
        bool(release_notes_text),
    )
    prompt = _jira_prompt(issues, output_type=output_type, release_notes_text=release_notes_text)
    return _llm_generate(prompt)


_MENTION_RE = re.compile(r"<[@#][!&]?\d+>")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+\S")
_MAPPING_KEYWORDS = ("сопостав", "mapping")


def _looks_like_release_notes(text: str) -> bool:
    """Tell a pasted Release Notes draft apart from a short request phrase.

    Mapping mode needs actual release notes items to match against Jira
    issues. A bot mention or a request like "make release notes for these
    epics" must not switch the skill into mapping mode.
    """
    cleaned = _MENTION_RE.sub("", text)
    lines = [line.strip() for line in cleaned.splitlines()]
    content_lines = [line for line in lines if re.search(r"\w", line)]
    if not content_lines:
        return False
    if any(keyword in cleaned.lower() for keyword in _MAPPING_KEYWORDS):
        return True
    list_items = [line for line in content_lines if _LIST_ITEM_RE.match(line)]
    return len(list_items) >= 2 or len(content_lines) >= 3


def _parse_repository(repository: str) -> tuple[str, str]:
    value = repository.strip()
    if not value:
        raise ReleaseNotesError("Укажите GitHub-репозиторий")
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
    else:
        parts = [p for p in value.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ReleaseNotesError("Укажите репозиторий в формате owner/repo или GitHub URL")
    owner = parts[0]
    repo = re.sub(r"\.git$", "", parts[1])
    if not owner or not repo:
        raise ReleaseNotesError("Укажите репозиторий в формате owner/repo или GitHub URL")
    return owner, repo


def _parse_date(value: str, field_name: str) -> datetime:
    raw = value.strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ReleaseNotesError(f"{field_name} должна быть в формате ДД-ММ-ГГГГ или ГГГГ-ММ-ДД")


def _date_range(date_from: str, date_to: str) -> tuple[str, str, str, str]:
    start = _parse_date(date_from, "date_from")
    end = _parse_date(date_to, "date_to")
    if start > end:
        raise ReleaseNotesError("date_from не может быть позже date_to")
    since = start.strftime("%Y-%m-%dT00:00:00Z")
    until = end.strftime("%Y-%m-%dT23:59:59Z")
    return since, until, start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y")


def _llm_generate(prompt: str) -> str:
    return generate_text(
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=config.RELEASE_NOTES_MAX_TOKENS,
    )


def _get_commits(owner: str, repo: str, since: str, until: str, branch: str = "") -> list[dict]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"

    url = f"{_GITHUB_API}/repos/{owner}/{repo}/commits"
    commits = []
    for page in range(1, 11):
        params: dict = {"since": since, "until": until, "per_page": 100, "page": page}
        if branch:
            params["sha"] = branch
        try:
            response = http_client.get(url, headers=headers, params=params, timeout=config.REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise ReleaseNotesError(f"Не удалось подключиться к GitHub: {exc}") from exc
        if response.status_code in (401, 403):
            raise ReleaseNotesError("GitHub вернул 401/403. Проверьте GITHUB_TOKEN.")
        if response.status_code == 404:
            raise ReleaseNotesError(f"Репозиторий {owner}/{repo} не найден.")
        if response.status_code >= 400:
            raise ReleaseNotesError(f"GitHub API ошибка {response.status_code}")

        items = response.json()
        for item in items:
            commit = item.get("commit", {})
            commits.append(
                {
                    "sha": item.get("sha", "")[:7],
                    "message": commit.get("message", "").split("\n")[0],
                    "author": commit.get("author", {}).get("name", ""),
                    "date": commit.get("author", {}).get("date", "")[:10],
                }
            )
        if len(items) < 100:
            break
    return commits


_JIRA_HTTP_ERRORS = {
    401: (
        "Jira вернул 401: учётные данные не опознаны. Убедитесь, что JIRA_EMAIL — "
        "это email аккаунта, под которым выпущен JIRA_API_TOKEN, и что аккаунт "
        "состоит в этом Jira-сайте."
    ),
    403: (
        "Jira вернул 403: аккаунт опознан, но прав на задачу {key} нет. "
        "Нужно разрешение Browse Projects для её проекта."
    ),
    404: (
        "Jira вернул 404: задача {key} не найдена или не видна этому аккаунту. "
        "Проверьте ключ задачи и адрес Jira-сайта."
    ),
}


_JIRA_FIELDS = "summary,issuetype,status,description,labels,components,fixVersions"
_EPIC_TYPE_NAMES = {"epic", "эпик"}
_EPIC_HIERARCHY_LEVEL = 1
_MAX_EPIC_CHILDREN = 100
_CHILD_DESCRIPTION_LIMIT = 1500


class JiraClient:
    def __init__(self, email: str = "", api_token: str = "") -> None:
        email = email or config.JIRA_EMAIL
        api_token = api_token or config.JIRA_API_TOKEN
        if not email or not api_token:
            raise ReleaseNotesError("JIRA_EMAIL и JIRA_API_TOKEN не заданы в .env")
        self._auth = HTTPBasicAuth(email, api_token)

    def get_issue(self, base_url: str, key: str) -> dict:
        data = self._get_json(f"{base_url}/rest/api/3/issue/{key}", {"fields": _JIRA_FIELDS}, key)
        return _issue_from_payload({"key": key, **data})

    def get_epic_children(self, base_url: str, epic_key: str) -> list[dict]:
        """Fetch child issues of an epic via JQL search (Jira Cloud, nextPageToken pagination)."""
        children: list[dict] = []
        params: dict = {"jql": f"parent = {epic_key} ORDER BY created ASC", "fields": _JIRA_FIELDS, "maxResults": 50}
        while True:
            data = self._get_json(f"{base_url}/rest/api/3/search/jql", params, epic_key)
            children.extend(_issue_from_payload(item) for item in data.get("issues") or [])
            next_token = data.get("nextPageToken")
            if data.get("isLast", True) or not next_token:
                break
            if len(children) >= _MAX_EPIC_CHILDREN:
                logger.warning("[release-notes] epic %s children truncated to %d", epic_key, _MAX_EPIC_CHILDREN)
                break
            params = {**params, "nextPageToken": next_token}
        return children[:_MAX_EPIC_CHILDREN]

    def get_issues(self, urls: list[str]) -> list[dict]:
        pairs = [(base_url, key) for base_url, keys in _parse_jira_urls(urls).items() for key in keys]
        issues = [(base_url, self.get_issue(base_url, key)) for base_url, key in pairs]
        requested_keys = {issue["key"].upper() for _, issue in issues}
        for base_url, issue in issues:
            if issue.get("is_epic"):
                children = self.get_epic_children(base_url, issue["key"])
                # Issues the user linked explicitly are rendered on their own, not twice.
                issue["children"] = [child for child in children if child["key"].upper() not in requested_keys]
        return [issue for _, issue in issues]

    def _get_json(self, url: str, params: dict, key: str) -> dict:
        try:
            response = http_client.get(url, auth=self._auth, params=params, timeout=config.REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            message = _JIRA_HTTP_ERRORS.get(status)
            if message:
                raise ReleaseNotesError(message.format(key=key)) from exc
            raise ReleaseNotesError(f"Jira API ошибка {status}") from exc
        except requests.RequestException as exc:
            raise ReleaseNotesError(f"Не удалось подключиться к Jira: {exc}") from exc
        return response.json()


def _issue_from_payload(data: dict) -> dict:
    fields = data.get("fields") or {}
    issue_type = fields.get("issuetype") or {}
    return {
        "key": data.get("key", ""),
        "summary": fields.get("summary", ""),
        "type": issue_type.get("name", ""),
        "is_epic": _is_epic(issue_type),
        "status": (fields.get("status") or {}).get("name", ""),
        "description": _adf_to_text(fields.get("description")),
        "labels": fields.get("labels") or [],
        "components": [item.get("name", "") for item in fields.get("components") or [] if item.get("name")],
        "fix_versions": [item.get("name", "") for item in fields.get("fixVersions") or [] if item.get("name")],
    }


def _is_epic(issue_type: dict) -> bool:
    if issue_type.get("hierarchyLevel") == _EPIC_HIERARCHY_LEVEL:
        return True
    return str(issue_type.get("name", "")).strip().lower() in _EPIC_TYPE_NAMES


def _parse_jira_urls(urls: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for url in urls:
        parsed = urlparse(url.strip())
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        base, key = _split_jira_path(f"{parsed.scheme}://{parsed.netloc}", parts)
        if key:
            result.setdefault(base, []).append(key)
    return result


def _split_jira_path(origin: str, parts: list[str]) -> tuple[str, str]:
    """Split a Jira URL path into the REST base URL and the issue key.

    Jira Server/DC may live under a context path (/jira/browse/ABC-1), so
    everything before the /browse/ segment belongs to the base URL.
    """
    lowered = [p.lower() for p in parts]
    if "browse" in lowered:
        index = lowered.index("browse")
        context = "/".join(parts[:index])
        base = f"{origin}/{context}" if context else origin
        key = parts[index + 1] if index + 1 < len(parts) else ""
        return base, key
    return origin, next((p for p in reversed(parts) if "-" in p), "")


def _adf_to_text(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()

    chunks: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        node_type = node.get("type")
        if node_type == "text":
            chunks.append(str(node.get("text", "")))
        elif node_type == "hardBreak":
            chunks.append("\n")
        content = node.get("content")
        if content:
            walk(content)
        if node_type in {"paragraph", "heading", "bulletList", "orderedList", "listItem"}:
            chunks.append("\n")

    walk(value)
    lines = [line.strip() for line in "".join(chunks).splitlines()]
    return "\n".join(line for line in lines if line)[:4000]


def _instructions(output_type: OutputType) -> str:
    return load_instructions("release-notes", f"instructions-{output_type}.md")


def _github_prompt(
    owner: str,
    repo: str,
    date_from: str,
    date_to: str,
    commits: list[dict],
    output_type: OutputType = "release_notes",
) -> str:
    lines = "\n".join(f"- [{c['sha']}] {c['date']} {c['author']}: {c['message']}" for c in commits)
    return f"Репозиторий: {owner}/{repo}\nПериод: с {date_from} по {date_to}\n\nКоммиты:\n{lines}\n\n{_instructions(output_type)}"


def _jira_issue_block(issue: dict, indent: str = "", description_limit: int = 0) -> str:
    meta = [f"тип: {issue.get('type', '')}", f"статус: {issue.get('status', '')}"]
    if issue.get("fix_versions"):
        meta.append(f"fixVersion: {', '.join(issue['fix_versions'])}")
    if issue.get("components"):
        meta.append(f"компоненты: {', '.join(issue['components'])}")
    if issue.get("labels"):
        meta.append(f"labels: {', '.join(issue['labels'])}")
    block = f"{indent}- [{issue['key']}] ({'; '.join(meta)}) {issue.get('summary', '')}"
    description = issue.get("description", "").strip()
    if description_limit and len(description) > description_limit:
        description = description[:description_limit].rstrip() + " …"
    if description:
        nested = f"\n{indent}  "
        block += f"{nested}Описание:{nested}{description.replace(chr(10), nested)}"
    return block


def _jira_prompt(
    issues: list[dict],
    output_type: OutputType = "release_notes",
    release_notes_text: str = "",
) -> str:
    blocks = []
    for issue in issues:
        block = _jira_issue_block(issue)
        children = issue.get("children") or []
        if children:
            child_blocks = "\n".join(
                _jira_issue_block(child, indent="    ", description_limit=_CHILD_DESCRIPTION_LIMIT)
                for child in children
            )
            block += f"\n  Дочерние задачи эпика:\n{child_blocks}"
        blocks.append(block)

    lines = "\n".join(blocks)
    if release_notes_text.strip():
        return (
            f"Jira-задачи:\n{lines}\n\nАктуальные Release Notes:\n{release_notes_text.strip()}\n\n"
            f"{load_instructions('release-notes', 'instructions-mapping.md')}"
        )
    return f"Jira-задачи:\n{lines}\n\n{_instructions(output_type)}"
