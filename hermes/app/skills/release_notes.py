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
    logger.info("[release-notes] fetched jira issues=%d output_type=%s", len(issues), output_type)
    prompt = _jira_prompt(issues, output_type=output_type, release_notes_text=release_notes_text)
    return _llm_generate(prompt)


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


class JiraClient:
    def __init__(self, email: str = "", api_token: str = "") -> None:
        email = email or config.JIRA_EMAIL
        api_token = api_token or config.JIRA_API_TOKEN
        if not email or not api_token:
            raise ReleaseNotesError("JIRA_EMAIL и JIRA_API_TOKEN не заданы в .env")
        self._auth = HTTPBasicAuth(email, api_token)

    def get_issue(self, base_url: str, key: str) -> dict:
        try:
            response = http_client.get(
                f"{base_url}/rest/api/3/issue/{key}",
                auth=self._auth,
                params={"fields": "summary,issuetype,status,description,labels,components,fixVersions"},
                timeout=config.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            message = _JIRA_HTTP_ERRORS.get(status)
            if message:
                raise ReleaseNotesError(message.format(key=key)) from exc
            raise ReleaseNotesError(f"Jira API ошибка {status}") from exc
        except requests.RequestException as exc:
            raise ReleaseNotesError(f"Не удалось подключиться к Jira: {exc}") from exc

        fields = response.json()["fields"]
        return {
            "key": key,
            "summary": fields.get("summary", ""),
            "type": fields.get("issuetype", {}).get("name", ""),
            "status": fields.get("status", {}).get("name", ""),
            "description": _adf_to_text(fields.get("description")),
            "labels": fields.get("labels") or [],
            "components": [item.get("name", "") for item in fields.get("components") or [] if item.get("name")],
            "fix_versions": [item.get("name", "") for item in fields.get("fixVersions") or [] if item.get("name")],
        }

    def get_issues(self, urls: list[str]) -> list[dict]:
        grouped = _parse_jira_urls(urls)
        return [self.get_issue(base_url, key) for base_url, keys in grouped.items() for key in keys]


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


def _jira_prompt(
    issues: list[dict],
    output_type: OutputType = "release_notes",
    release_notes_text: str = "",
) -> str:
    blocks = []
    for issue in issues:
        meta = [f"тип: {issue.get('type', '')}", f"статус: {issue.get('status', '')}"]
        if issue.get("fix_versions"):
            meta.append(f"fixVersion: {', '.join(issue['fix_versions'])}")
        if issue.get("components"):
            meta.append(f"компоненты: {', '.join(issue['components'])}")
        if issue.get("labels"):
            meta.append(f"labels: {', '.join(issue['labels'])}")
        block = f"- [{issue['key']}] ({'; '.join(meta)}) {issue.get('summary', '')}"
        description = issue.get("description", "").strip()
        if description:
            block += f"\n  Описание:\n  {description.replace(chr(10), chr(10) + '  ')}"
        blocks.append(block)

    lines = "\n".join(blocks)
    if release_notes_text.strip():
        return (
            f"Jira-задачи:\n{lines}\n\nАктуальные Release Notes:\n{release_notes_text.strip()}\n\n"
            f"{load_instructions('release-notes', 'instructions-mapping.md')}"
        )
    return f"Jira-задачи:\n{lines}\n\n{_instructions(output_type)}"
