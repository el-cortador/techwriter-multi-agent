# Smoke Test Plan

Ручная проверка после установки или обновления. Выполнять по порядку; критерий прохождения —
все пункты отмечены.

## 1. Юнит-тесты

```powershell
.venv/Scripts/python -m pytest hermes/tests -q
```

- [ ] Все тесты проходят (включая контрактные тесты skill-пакетов `test_skill_packages.py`).

## 2. Сборка и запуск

```powershell
docker compose up -d --build
docker compose ps
```

- [ ] Все 4 сервиса в статусе `running`: `hermes-discord`, `postgres`, `dashboard-api`, `dashboard-ui`.
- [ ] В логах `hermes-discord` есть строка `Hermes Discord gateway logged in as ...`:
      `docker compose logs hermes-discord`
- [ ] Схема БД создаётся через Alembic-миграции (не `CREATE TABLE IF NOT EXISTS` на каждый
      старт): в логах `hermes-discord` и `dashboard-api` есть
      `Running upgrade  -> d4b6fd9bff93, baseline schema` при первом запуске на чистой БД;
      при повторном запуске — без строки `Running upgrade`, только `Context impl PostgresqlImpl`.
- [ ] `SELECT version_num FROM alembic_version;` в `postgres` возвращает текущую head-ревизию:
      `docker compose exec postgres psql -U postgres -d agent_dashboard -c "SELECT * FROM alembic_version;"`

## 3. Discord end-to-end

В разрешенном канале (см. `DISCORD_ALLOWED_*`):

- [ ] `привет` → ответ «Я на связи. Пришлите задачу или материал.»
- [ ] Текст постановки (2–3 абзаца) → Markdown-черновик инструкции (spec2doc).
- [ ] `https://gitlab.com/<group>/<project>/-/merge_requests/<N>` → черновик с разделами «Что изменилось», «Влияние на пользователя» (spec2doc).
- [ ] Ссылка на merge request приватного проекта без `GITLAB_TOKEN` → «Ошибка сервиса: GitLab вернул 401/403…» без ответа LLM.
- [ ] Файл `openapi.yaml` → документация по API без ошибок (api-docs, локальный рендеринг).
- [ ] Файл `.md` (или `.doc` / `.docx` / `.pdf`) → Markdown-черновик инструкции (spec2doc), без ошибки «Текст постановки не может быть пустым».
- [ ] `changelog https://github.com/<owner>/<repo> 01.01.2026 31.01.2026` → changelog или «коммитов не найдено» (release-notes).
- [ ] Ссылка на публичный Figma-файл → руководство по интерфейсу (figma-guide).
- [ ] Скриншот интерфейса → user guide по видимым элементам (vision).
- [ ] Файл `.mp3` → сообщение об отключенной транскрибации.

## 4. Дашборд

- [ ] `http://127.0.0.1:4173` открывается, показывает форму ввода `X-API-Key` вместо графиков,
      пока ключ не введён.
- [ ] После ввода `DASHBOARD_API_KEY` из `.env` дашборд показывает данные без ошибок.
- [ ] `curl http://127.0.0.1:<dashboard-api-порт>/api/overview` без заголовка `X-API-Key` → `401`.
- [ ] После шагов из раздела 3 в Overview появляются runs/sessions; в Recent errors — пусто (если не было ошибок).

## 5. Отказоустойчивость

- [ ] Сообщение без `OPENROUTER_API_KEY` (временно убрать, перезапустить) → понятная ошибка пользователю, запись в Recent errors, бот не падает.
- [ ] `docker compose restart hermes-discord` → бот переподключается и отвечает.

## Критерии отката

Откатывать релиз, если: тесты падают, бот не подключается к Discord, любой сценарий из
раздела 3 возвращает «Не удалось обработать запрос».
