from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import struct

from app.models import IncomingAttachment, IncomingMessage, Route
from app.skills import api_docs, documents, figma, release_notes, spec2doc
from app.skills.runner import run_route


class SkillRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_api_docs_text_route_runs_in_process(self) -> None:
        message = IncomingMessage(
            content="""
openapi: 3.0.0
info:
  title: Demo API
  version: 1.0.0
paths:
  /users:
    get:
      summary: List users
      responses:
        "200":
          description: OK
""",
            attachments=[],
        )

        result = await run_route(Route("api_docs_text"), message)

        self.assertIn("# Demo API", result)
        self.assertIn("## GET /users", result)
        self.assertIn("| 200 | OK |", result)

    async def test_api_docs_file_route_reads_utf8_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "openapi.yaml"
            path.write_text(
                "openapi: 3.0.0\ninfo:\n  title: File API\npaths:\n  /ping:\n    get:\n      responses:\n        '204':\n          description: No Content\n",
                encoding="utf-8",
            )
            message = IncomingMessage(
                content="",
                attachments=[IncomingAttachment(filename=path.name, content_type=None, path=path)],
            )

            result = await run_route(Route("api_docs_file", attachment=message.attachments[0]), message)

        self.assertIn("# File API", result)
        self.assertIn("## GET /ping", result)

    async def test_spec_text_route_uses_spec_skill_without_http(self) -> None:
        with patch("app.skills.spec2doc.generate_draft", return_value="# Draft") as generate:
            result = await run_route(Route("spec_text"), IncomingMessage(content="описание функции", attachments=[]))

        self.assertEqual(result, "# Draft")
        generate.assert_called_once_with("описание функции")

    async def test_merge_request_route_passes_url_and_comment(self) -> None:
        route = Route("spec_merge_request", urls=["https://gitlab.com/acme/app/-/merge_requests/42"])
        message = IncomingMessage(
            content="Нужна инструкция https://gitlab.com/acme/app/-/merge_requests/42 для саппорта",
            attachments=[],
        )

        with patch("app.skills.spec2doc.generate_draft_from_merge_request", return_value="# MR") as generate:
            result = await run_route(route, message)

        self.assertEqual(result, "# MR")
        generate.assert_called_once_with(
            "https://gitlab.com/acme/app/-/merge_requests/42",
            "Нужна инструкция  для саппорта",
        )

    async def test_spec_file_route_reads_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "postanovka.md"
            path.write_text("# Постановка\n\nНужен экспорт в CSV.\n", encoding="utf-8")
            message = IncomingMessage(
                content="",
                attachments=[IncomingAttachment(filename=path.name, content_type=None, path=path)],
            )
            with patch("app.skills.spec2doc.generate_draft", return_value="# Draft") as generate:
                result = await run_route(Route("spec_file", attachment=message.attachments[0]), message)

        self.assertEqual(result, "# Draft")
        self.assertIn("Нужен экспорт в CSV.", generate.call_args.args[0])

    async def test_github_release_builds_payload_from_route(self) -> None:
        route = Route(
            "github_release",
            urls=["https://github.com/acme/app"],
            output_type="changelog",
        )
        message = IncomingMessage(
            content="changelog https://github.com/acme/app с 01.01.2026 по 31.01.2026",
            attachments=[],
        )
        with patch("app.skills.release_notes.generate_github", return_value="changes") as generate:
            result = await run_route(route, message)

        self.assertEqual(result, "changes")
        generate.assert_called_once_with(
            repository="https://github.com/acme/app",
            date_from="01-01-2026",
            date_to="31-01-2026",
            branch="",
            output_type="changelog",
        )

    async def test_release_request_without_source_returns_explicit_error(self) -> None:
        message = IncomingMessage(content="Collect release notes for the new feature", attachments=[])

        with self.assertRaisesRegex(Exception, "release notes"):
            await run_route(Route("release_request"), message)


class SkillUnitTest(unittest.TestCase):
    def test_openapi_renderer_does_not_need_llm(self) -> None:
        result = api_docs.generate_api_docs(
            """
openapi: 3.0.0
info:
  title: Local API
paths:
  /items:
    post:
      summary: Create item
      responses:
        "201":
          description: Created
"""
        )

        self.assertIn("# Local API", result)
        self.assertIn("## POST /items", result)

    def test_figma_file_id_extraction(self) -> None:
        self.assertEqual(
            figma.extract_file_id("https://www.figma.com/design/AbC123456789/Test"),
            "AbC123456789",
        )

    def test_figma_filter_extracts_wireflow_from_canvas_frames(self) -> None:
        filtered = figma.filter_figma_json(
            {
                "name": "Checkout wireframes",
                "document": {
                    "id": "doc",
                    "type": "DOCUMENT",
                    "children": [
                        {
                            "id": "page-1",
                            "name": "Happy path",
                            "type": "CANVAS",
                            "children": [
                                {
                                    "id": "screen-2",
                                    "name": "02 Payment",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {"x": 500, "y": 0, "width": 390, "height": 844},
                                    "children": [
                                        {"id": "text-2", "name": "Title", "type": "TEXT", "characters": "Payment"},
                                    ],
                                },
                                {
                                    "id": "screen-1",
                                    "name": "01 Cart",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 390, "height": 844},
                                    "children": [
                                        {"id": "text-1", "name": "Title", "type": "TEXT", "characters": "Cart"},
                                    ],
                                },
                            ],
                        }
                    ],
                },
            }
        )

        self.assertEqual(filtered["mode"], "wireflow")
        self.assertEqual([screen["id"] for screen in filtered["screens"]], ["screen-1", "screen-2"])
        self.assertEqual(filtered["flows"][0]["trigger"], "inferred_order")
        self.assertEqual(filtered["flows"][0]["from"], "screen-1")
        self.assertEqual(filtered["flows"][0]["to"], "screen-2")

    def test_figma_filter_keeps_prototype_connections(self) -> None:
        filtered = figma.filter_figma_json(
            {
                "name": "Prototype",
                "document": {
                    "id": "doc",
                    "type": "DOCUMENT",
                    "children": [
                        {
                            "id": "page-1",
                            "name": "Flow",
                            "type": "CANVAS",
                            "children": [
                                {
                                    "id": "screen-1",
                                    "name": "Start",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 390, "height": 844},
                                    "reactions": [
                                        {
                                            "trigger": {"type": "ON_CLICK"},
                                            "action": {"type": "NODE", "destinationId": "screen-2"},
                                        }
                                    ],
                                    "children": [],
                                },
                                {
                                    "id": "screen-2",
                                    "name": "Finish",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {"x": 500, "y": 0, "width": 390, "height": 844},
                                    "children": [],
                                },
                            ],
                        }
                    ],
                },
            }
        )

        self.assertEqual(filtered["flows"], [
            {
                "from": "screen-1",
                "from_order": 1,
                "from_name": "Start",
                "to": "screen-2",
                "to_order": 2,
                "trigger": "ON_CLICK",
                "action": "NODE",
            }
        ])

    def test_figma_prompt_mentions_wireflow_analysis(self) -> None:
        prompt = figma.build_prompt(
            {
                "file_name": "Flow",
                "mode": "wireflow",
                "screens": [
                    {"id": "screen-1", "order": 1, "name": "Start", "elements": []},
                    {"id": "screen-2", "order": 2, "name": "Finish", "elements": []},
                ],
                "flows": [{"from": "screen-1", "to": "screen-2", "trigger": "inferred_order"}],
            },
            language="ru",
            detail_level="brief",
            audience="user",
        )

        self.assertIn("wireflow", prompt)
        self.assertIn("пользовательский путь", prompt)

    def test_merge_request_url_parser_handles_subgroups_and_legacy_path(self) -> None:
        self.assertEqual(
            spec2doc.parse_merge_request_url("https://gitlab.com/acme/group/app/-/merge_requests/42"),
            ("https://gitlab.com", "acme/group/app", 42),
        )
        self.assertEqual(
            spec2doc.parse_merge_request_url("https://git.example.com/acme/app/merge_requests/7"),
            ("https://git.example.com", "acme/app", 7),
        )

    def test_merge_request_url_parser_rejects_foreign_links(self) -> None:
        with self.assertRaises(spec2doc.GitLabError):
            spec2doc.parse_merge_request_url("https://github.com/acme/app/pull/42")

    def test_merge_request_diffs_are_truncated_deterministically(self) -> None:
        changes = [
            {"new_path": "src/a.py", "diff": "+" * (spec2doc.MAX_FILE_DIFF_CHARS + 100)},
            {"new_path": "src/b.py", "old_path": "src/old.py", "renamed_file": True, "diff": "+b"},
            {"new_path": "src/c.py", "deleted_file": True, "diff": ""},
        ]

        files, truncated = spec2doc._collect_diffs(changes)

        self.assertTrue(truncated)
        self.assertEqual([item["path"] for item in files], ["src/a.py", "src/b.py", "src/c.py"])
        self.assertEqual(
            [item["status"] for item in files],
            ["изменен", "переименован из src/old.py", "удален"],
        )
        self.assertTrue(files[0]["diff"].endswith("(дифф файла усечен)"))
        self.assertLessEqual(sum(len(item["diff"]) for item in files), spec2doc.MAX_TOTAL_DIFF_CHARS)

    def test_merge_request_prompt_contains_metadata_and_diffs(self) -> None:
        prompt = spec2doc.build_merge_request_prompt(
            {
                "project": "acme/app",
                "iid": 42,
                "web_url": "https://gitlab.com/acme/app/-/merge_requests/42",
                "title": "Add export button",
                "description": "Кнопка экспорта в CSV",
                "state": "opened",
                "author": "Ivan",
                "source_branch": "feature/export",
                "target_branch": "main",
                "labels": ["frontend"],
                "commits": [{"short_id": "abc1234", "title": "Add export button"}],
                "files": [{"path": "src/export.ts", "status": "добавлен", "diff": "+export const run = () => {}"}],
                "diff_truncated": False,
            }
        )

        self.assertIn("Merge request: !42 Add export button", prompt)
        self.assertIn("Проект: acme/app", prompt)
        self.assertIn("feature/export -> main", prompt)
        self.assertIn("Кнопка экспорта в CSV", prompt)
        self.assertIn("- [abc1234] Add export button", prompt)
        self.assertIn("--- src/export.ts ---", prompt)
        self.assertNotIn("усечен", prompt)

    def test_jira_url_parser_groups_by_base_url(self) -> None:
        grouped = release_notes._parse_jira_urls(
            [
                "https://example.atlassian.net/browse/ABC-123",
                "https://example.atlassian.net/browse/ABC-456",
            ]
        )

        self.assertEqual(grouped, {"https://example.atlassian.net": ["ABC-123", "ABC-456"]})

    def test_jira_url_parser_keeps_context_path(self) -> None:
        grouped = release_notes._parse_jira_urls(["https://jira.example.com/jira/browse/ABC-123"])

        self.assertEqual(grouped, {"https://jira.example.com/jira": ["ABC-123"]})

    def test_jira_url_parser_keeps_nested_context_path(self) -> None:
        grouped = release_notes._parse_jira_urls(["https://example.com/tools/jira/browse/ABC-1"])

        self.assertEqual(grouped, {"https://example.com/tools/jira": ["ABC-1"]})

    def test_jira_http_errors_are_distinct_per_status(self) -> None:
        messages = {
            status: release_notes._JIRA_HTTP_ERRORS[status].format(key="ABC-123")
            for status in (401, 403, 404)
        }

        self.assertEqual(len(set(messages.values())), 3)
        self.assertIn("JIRA_API_TOKEN", messages[401])
        self.assertNotIn("JIRA_API_TOKEN", messages[404])
        self.assertIn("Browse Projects", messages[403])
        self.assertIn("ABC-123", messages[404])

    def test_release_notes_detector_ignores_mention_and_request_phrase(self) -> None:
        self.assertFalse(release_notes._looks_like_release_notes("<@123456789> сделай release notes по эпикам:"))
        self.assertFalse(release_notes._looks_like_release_notes("Release notes для релиза 1.8\n-\n-"))
        self.assertFalse(release_notes._looks_like_release_notes(""))

    def test_release_notes_detector_accepts_pasted_draft(self) -> None:
        draft = "- Добавлен конструктор парсеров.\n- Добавлен JSON-парсер для Aqua."

        self.assertTrue(release_notes._looks_like_release_notes(draft))
        self.assertTrue(release_notes._looks_like_release_notes("Сопоставь с задачами: Добавлен экспорт."))

    def test_generate_jira_with_request_phrase_uses_release_notes_template(self) -> None:
        issue = {"key": "ABC-1", "summary": "Конструктор парсеров", "type": "Epic", "status": "Done"}
        with (
            patch.object(release_notes, "JiraClient") as client,
            patch.object(release_notes, "_llm_generate", return_value="notes") as generate,
        ):
            client.return_value.get_issues.return_value = [issue]
            release_notes.generate_jira(
                ["https://example.atlassian.net/browse/ABC-1"],
                release_notes_text="<@123456789> сделай release notes по эпикам",
            )

        prompt = generate.call_args.args[0]
        self.assertIn("Что изменилось для пользователя:", prompt)
        self.assertNotIn("Актуальные Release Notes", prompt)

    def test_issue_payload_detects_epic_and_skips_release_date(self) -> None:
        issue = release_notes._issue_from_payload(
            {
                "key": "ABC-1",
                "fields": {
                    "summary": "Конструктор парсеров",
                    "issuetype": {"name": "Эпик", "hierarchyLevel": 1},
                    "fixVersions": [{"name": "1.7", "releaseDate": "2026-08-31"}],
                },
            }
        )

        self.assertTrue(issue["is_epic"])
        self.assertEqual(issue["fix_versions"], ["1.7"])
        self.assertFalse(release_notes._is_epic({"name": "Story", "hierarchyLevel": 0}))

    def test_jira_client_loads_epic_children_with_pagination(self) -> None:
        def response(payload: dict) -> object:
            fake = Mock()
            fake.json.return_value = payload
            return fake

        epic = {"key": "ABC-1", "fields": {"summary": "Парсеры", "issuetype": {"name": "Epic"}}}
        story = {"key": "ABC-2", "fields": {"summary": "Системные парсеры", "issuetype": {"name": "Story"}}}
        linked = {"key": "ABC-3", "fields": {"summary": "Тест парсера", "issuetype": {"name": "Story"}}}
        pages = [
            response(epic),
            response(linked),
            response({"issues": [story], "nextPageToken": "next", "isLast": False}),
            response({"issues": [linked], "isLast": True}),
        ]
        client = release_notes.JiraClient(email="user@example.com", api_token="token")
        with patch.object(release_notes.http_client, "get", side_effect=pages) as get:
            issues = client.get_issues(
                [
                    "https://example.atlassian.net/browse/ABC-1",
                    "https://example.atlassian.net/browse/ABC-3",
                ]
            )

        self.assertEqual([child["key"] for child in issues[0]["children"]], ["ABC-2"])
        self.assertNotIn("children", issues[1])
        search_calls = [call for call in get.call_args_list if call.args[0].endswith("/rest/api/3/search/jql")]
        self.assertEqual(len(search_calls), 2)
        self.assertIn("parent = ABC-1", search_calls[0].kwargs["params"]["jql"])
        self.assertEqual(search_calls[1].kwargs["params"]["nextPageToken"], "next")

    def test_jira_prompt_nests_epic_children(self) -> None:
        epic = {
            "key": "ABC-1",
            "summary": "Парсеры",
            "type": "Epic",
            "status": "Done",
            "children": [
                {"key": "ABC-2", "summary": "Системные парсеры", "type": "Story", "status": "Done", "description": "x" * 2000},
            ],
        }

        prompt = release_notes._jira_prompt([epic])

        self.assertIn("Дочерние задачи эпика:\n    - [ABC-2]", prompt)
        self.assertIn("x" * 1500 + " …", prompt)
        self.assertNotIn("x" * 1501, prompt)


class DocumentExtractionTest(unittest.TestCase):
    def test_markdown_file_is_read_as_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.md"
            path.write_text("# Заголовок\r\n\r\n\r\n\r\nТело постановки\r\n", encoding="utf-8-sig")

            text = documents.read_document(path)

        self.assertEqual(text, "# Заголовок\n\nТело постановки")

    def test_cp1251_text_file_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.txt"
            path.write_bytes("Постановка".encode("cp1251"))

            self.assertEqual(documents.read_document(path), "Постановка")

    def test_empty_markdown_file_fails_without_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.md"
            path.write_text("   \n\n", encoding="utf-8")

            with self.assertRaises(documents.ParserError):
                documents.read_document(path)

    def test_unsupported_extension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.rtfx"
            path.write_text("text", encoding="utf-8")

            with self.assertRaisesRegex(documents.ParserError, "Неподдерживаемый формат"):
                documents.read_document(path)

    def test_doc_piece_table_is_parsed(self) -> None:
        plc = struct.pack("<II", 0, 6) + struct.pack("<HIH", 0, 0x40000000 | (100 * 2), 0)
        clx = b"\x01" + struct.pack("<H", 2) + b"\x00\x00" + b"\x02" + struct.pack("<I", len(plc)) + plc

        pieces = documents._parse_piece_table(clx)

        self.assertEqual(pieces, [(100, 6, True)])

    def test_doc_compressed_piece_decodes_cyrillic(self) -> None:
        document = b"\x00" * 100 + "Привет".encode("cp1251")

        self.assertEqual(documents._read_doc_piece(document, 100, 6, True), "Привет")

    def test_doc_uncompressed_piece_decodes_utf16(self) -> None:
        document = b"\x00" * 10 + "Привет".encode("utf-16-le")

        self.assertEqual(documents._read_doc_piece(document, 10, 6, False), "Привет")

    def test_doc_control_characters_are_normalized(self) -> None:
        self.assertEqual(
            documents._clean_doc_text("Шаг 1\rШаг 2\x07\x13ссылка\x15\r\r\r\rКонец"),
            "Шаг 1\nШаг 2\nссылка\n\nКонец",
        )

    def test_doc_with_zip_signature_falls_back_to_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "renamed.doc"
            path.write_bytes(b"PK\x03\x04" + b"\x00" * 10)

            with patch("app.skills.documents._extract_docx", return_value="текст") as extract:
                self.assertEqual(documents.extract_text(path), "текст")

        extract.assert_called_once()

    def test_doc_without_ole_signature_reports_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.doc"
            path.write_bytes(b"not a word document")

            with self.assertRaisesRegex(documents.ParserError, "DOCX"):
                documents.extract_text(path)


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: object = None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = headers or {}
        self.encoding = "utf-8"

    def json(self) -> object:
        return self._payload


class GitLabMergeRequestTest(unittest.TestCase):
    def _fake_get(self, responses: dict[str, _FakeResponse]):
        def get(url, headers=None, params=None, timeout=None):  # noqa: ANN001
            for suffix, response in responses.items():
                if url.endswith(suffix):
                    return response
            raise AssertionError(f"Unexpected GitLab call: {url}")

        return get

    def test_fetch_uses_changes_endpoint_when_diffs_is_missing(self) -> None:
        responses = {
            "/merge_requests/42": _FakeResponse(
                200,
                {
                    "title": "Add export",
                    "description": "Описание",
                    "state": "opened",
                    "author": {"name": "Ivan"},
                    "source_branch": "feature/export",
                    "target_branch": "main",
                    "labels": ["frontend"],
                    "web_url": "https://gitlab.com/acme/app/-/merge_requests/42",
                },
            ),
            "/merge_requests/42/commits": _FakeResponse(200, [{"short_id": "abc1234", "title": "Add export"}]),
            "/merge_requests/42/diffs": _FakeResponse(404),
            "/merge_requests/42/changes": _FakeResponse(
                200, {"changes": [{"new_path": "src/export.ts", "new_file": True, "diff": "+code"}]}
            ),
        }

        with patch("app.skills.spec2doc.requests.get", side_effect=self._fake_get(responses)):
            merge_request = spec2doc.fetch_merge_request("https://gitlab.com/acme/app/-/merge_requests/42")

        self.assertEqual(merge_request["project"], "acme/app")
        self.assertEqual(merge_request["iid"], 42)
        self.assertEqual(merge_request["files"], [{"path": "src/export.ts", "status": "добавлен", "diff": "+code"}])
        self.assertEqual(merge_request["commits"], [{"short_id": "abc1234", "title": "Add export"}])
        self.assertFalse(merge_request["diff_truncated"])

    def test_fetch_reports_missing_access_without_calling_llm(self) -> None:
        responses = {"/merge_requests/42": _FakeResponse(401)}

        with patch("app.skills.spec2doc.requests.get", side_effect=self._fake_get(responses)):
            with self.assertRaisesRegex(spec2doc.GitLabError, "GITLAB_TOKEN"):
                spec2doc.fetch_merge_request("https://gitlab.com/acme/app/-/merge_requests/42")


if __name__ == "__main__":
    unittest.main()
