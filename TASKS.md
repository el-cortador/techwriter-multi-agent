# TASKS: techwriter-multi-agent — путь от alpha к релиз-готовности

> Упорядоченный список задач для ИИ-кодера. Выполнять по порядку внутри этапа, этапы —
> последовательно (0 → 7). Перед началом работы прочитать `SPEC.md` (этот документ идёт в
> паре с ним), а также `AGENTS.md` и `core/instructions.md` в самом репозитории.
> Отмечать выполненное чекбоксами.

---

## Этап 0. Security hardening

### - [x] 0.1. API-key middleware для dashboard-api

**Описание:** все `/api/*` эндпоинты `dashboard-api` требуют валидный `X-API-Key`, кроме
`/health`.

**Действия:**
- Добавить `DASHBOARD_API_KEY` в `.env.example`, `docker-compose.yml` (сервис
  `dashboard-api`), README (раздел Required Environment).
- В `dashboard-api/app/` создать `auth.py` с FastAPI-зависимостью на базе
  `fastapi.security.APIKeyHeader` (заголовок `X-API-Key`), сверяющей значение с
  `os.getenv("DASHBOARD_API_KEY")`.
- Подключить зависимость через `Depends(...)` ко всем роутам `/api/*` в
  `dashboard-api/app/main.py`, `/health` оставить без неё.
- При пустом `DASHBOARD_API_KEY` сервис должен падать при старте с понятной ошибкой
  (fail closed) — по аналогии с проверкой `DISCORD_BOT_TOKEN` в `hermes/app/main.py`.

**Готово, когда:**
- `curl http://localhost:PORT/api/overview` без заголовка → `401`.
- Тот же запрос с верным `X-API-Key` → `200`; с неверным → `401`/`403`.
- `curl .../health` без заголовка → `200`.
- Новый тест `dashboard-api/tests/test_auth.py` покрывает оба случая.

---

### - [x] 0.2. Ограничение CORS

**Описание:** заменить `allow_origins=["*"]` на список из переменной окружения.

**Действия:**
- Добавить `DASHBOARD_ALLOWED_ORIGINS` (CSV) в `.env.example` и `docker-compose.yml`,
  дефолт — `http://127.0.0.1:4173`.
- В `dashboard-api/app/main.py` добавить парсер CSV-строки (по аналогии с `_csv_ints` из
  `hermes/app/config.py`, но для строк) и подставить результат в `CORSMiddleware`.

**Готово, когда:**
- Юнит-тест на парсер origin-списка проходит (пустая строка, один origin, несколько через
  запятую).
- `CORSMiddleware` в `main.py` использует список из env, а не `["*"]`.

---

### - [x] 0.3. dashboard-ui: экран ввода API-ключа

**Описание:** UI хранит и отправляет `X-API-Key` на каждый запрос к `dashboard-api`.

**Действия:**
- Создать `dashboard-ui/src/auth.ts`: чтение/запись ключа в `localStorage`, хелпер
  `authFetch(url, options)`, добавляющий заголовок `X-API-Key`.
- В `App.tsx` заменить прямые `fetch(...)` к `/api/*` на `authFetch`.
- Добавить простую форму ввода ключа, показываемую вместо дашборда, если ключ не задан или
  последний запрос вернул `401`.

**Готово, когда:**
- Без сохранённого ключа UI показывает форму вместо графиков/таблиц.
- После ввода верного ключа — обычная работа дашборда без дополнительных изменений в
  остальном коде `App.tsx`.
- Неверный ключ → явное сообщение об ошибке, а не пустой экран/необработанное исключение.

---

### - [ ] 0.4. Безопасные дефолты в install-скриптах

**Описание:** `install.sh`/`install.ps1` не оставляют `postgres:postgres` и пустой
`DASHBOARD_API_KEY` при создании `.env` с нуля.

**Действия:**
- В `runtimes/hermes/install.sh` и `install.ps1`: при первом создании `.env` из
  `.env.example` генерировать случайные значения для `POSTGRES_PASSWORD` и
  `DASHBOARD_API_KEY` (openssl/`New-Guid` или аналог) и подставлять их в файл.
- Не трогать `.env`, если он уже существует (сохранить текущее поведение "never
  overwrites").

**Готово, когда:**
- Свежий `.env`, сгенерированный install-скриптом, не содержит `postgres`/`postgres` и
  пустого `DASHBOARD_API_KEY`.
- `runtimes/hermes/scripts/verify-install.sh`/`.ps1` дополнены проверкой, что эти значения
  не дефолтные/не пустые, и явно предупреждают, если .env создавался вручную со старыми
  дефолтами.

---

## Этап 1. Слой данных

### - [ ] 1.1. Единый источник схемы БД

**Описание:** устранить дублирование `SCHEMA_SQL` между `hermes/app/telemetry.py` и
`dashboard-api/app/main.py`.

**Действия:**
- Создать `db/schema.sql` в корне репозитория, перенести туда текущий SQL дословно (из
  любого из двух файлов — они идентичны).
- В `docker-compose.yml` изменить `dashboard-api.build`: `context: .`,
  `dockerfile: dashboard-api/Dockerfile` (сейчас `context: ./dashboard-api` — не видит
  корень репозитория).
- В `dashboard-api/Dockerfile` поправить пути: `COPY dashboard-api/requirements.txt .`,
  `COPY dashboard-api/app ./app`, добавить `COPY db/schema.sql /app/db/schema.sql`.
- В `hermes/Dockerfile` добавить `COPY db/schema.sql /app/db/schema.sql` (контекст уже
  корень репозитория, менять не нужно).
- В `hermes/app/telemetry.py` и `dashboard-api/app/main.py` заменить константу
  `SCHEMA_SQL` на чтение файла (`Path("/app/db/schema.sql").read_text()` либо путь из env
  для локального запуска без Docker).

**Готово, когда:**
- `grep -rn "CREATE TABLE IF NOT EXISTS sessions" .` находит определение только в
  `db/schema.sql`.
- `docker compose up -d --build` проходит, оба сервиса стартуют и создают схему.
- Существующие тесты (`hermes/tests`) проходят без изменений в логике, только в способе
  получения SQL.

---

### - [ ] 1.2. Alembic-миграции

**Описание:** версионирование схемы вместо `CREATE TABLE IF NOT EXISTS` при каждом старте.

**Действия:**
- `alembic init db/migrations`, настроить `db/alembic.ini` на `DATABASE_URL` из env.
- Создать baseline-ревизию, воспроизводящую содержимое `db/schema.sql` (используется как
  документ-источник для ревизии, не как исполняемый файл после этого шага — либо оставить
  `schema.sql` как справочный дамп, финальное решение зафиксировать в PR-описании).
- Заменить `telemetry.initialize()` (`hermes/app/telemetry.py`) и `startup()`
  (`dashboard-api/app/main.py`) на запуск `alembic upgrade head` (например через
  `subprocess` или `alembic.command.upgrade` из кода — выбрать один способ и
  задокументировать).
- Обновить `runtimes/hermes/docs/SMOKE_TEST_PLAN.md` и `TROUBLESHOOTING.md` с шагом
  проверки миграций.

**Готово, когда:**
- `alembic -c db/alembic.ini upgrade head` на чистой БД создаёт схему, идентичную текущей.
- Retry-логика инициализации (10 попыток с паузой, уже есть в `telemetry.initialize()`)
  сохранена поверх вызова миграций.
- Ревизия `alembic downgrade -1` явно определена (даже если как документированный no-op).

---

### - [ ] 1.3. Пул соединений

**Описание:** заменить `psycopg.connect()` на каждый вызов на переиспользуемый пул.

**Действия:**
- Добавить `psycopg_pool` в `hermes/requirements.txt` и `dashboard-api/requirements.txt`.
- Создать `hermes/app/db.py` и `dashboard-api/app/db.py` с `ConnectionPool`, инициализируемым
  один раз при старте процесса.
- Заменить все вызовы `_connect()`/`connect(DATABASE_URL)` в `hermes/app/telemetry.py` и
  `dashboard-api/app/main.py` на получение соединения из пула.

**Готово, когда:**
- Все существующие тесты (`hermes/tests`, новые из этапа 4) проходят без изменения
  поведения функций.
- Нагрузочная проверка (можно вручную: N параллельных запросов к `/api/overview`) не
  показывает роста числа соединений к Postgres пропорционально N.

---

### - [ ] 1.4. Retention-задача

**Описание:** периодическая очистка старых `events`/`llm_calls`.

**Действия:**
- Добавить `telemetry.purge_old_events(days: int) -> int` (возвращает число удалённых
  записей) в `hermes/app/telemetry.py`.
- Добавить скрипт `runtimes/hermes/scripts/purge-telemetry.py` (или `.ps1`-обёртку),
  вызывающий функцию с параметром из аргумента командной строки / env
  `TELEMETRY_RETENTION_DAYS`.
- Задокументировать способ запуска (вручную / cron / `docker compose run`) в
  `runtimes/hermes/README.md`.

**Готово, когда:**
- Тест создаёт записи со старой и свежей `created_at`, вызывает `purge_old_events`,
  проверяет, что удалены только старые.
- Скрипт запускается локально и в контейнере `hermes-discord` без дополнительных
  зависимостей сверх уже установленных.

---

## Этап 2. Отказоустойчивость вызовов

### - [ ] 2.1. Ретраи для LLM-вызовов

**Описание:** `hermes/app/skills/llm.py` и `hermes/app/vision.py` переживают единичный
сетевой сбой OpenRouter.

**Действия:**
- Добавить `tenacity` в `hermes/requirements.txt`.
- Обернуть вызов `client.chat.completions.create(...)` в обоих файлах декоратором
  `@retry(...)`: экспоненциальный бэкофф, 3 попытки, повтор только на
  `RateLimitError`/`APIConnectionError`/`APITimeoutError` (не на 4xx кроме 429).
- Передать явный `timeout=config.REQUEST_TIMEOUT` (или отдельная переменная
  `LLM_REQUEST_TIMEOUT`) в конструктор `OpenAI(...)`.

**Готово, когда:**
- Тест с моком клиента, падающим 2 раза подряд и успешным на 3-й попытке, — функция
  возвращает результат.
- Тест с моком, возвращающим `400 Bad Request`, — повтора нет, исключение пробрасывается
  сразу.
- Существующие тесты `hermes/tests/test_skills.py` и `test_telemetry_llm.py` проходят без
  изменений.

---

### - [ ] 2.2. Ретраи для внешних интеграций

**Описание:** аналогичная защита для клиентов GitHub/GitLab/Jira/Figma в
`hermes/app/skills/*.py`.

**Действия:**
- Создать `hermes/app/http_client.py` — обёртку над `requests`/`httpx` с тем же
  retry/backoff (429/5xx/timeout), без повтора на 401/403/404.
- Найти все прямые вызовы `requests.get/post`/`httpx` в `hermes/app/skills/spec2doc.py`,
  `release_notes.py`, `figma.py`, `api_docs.py` и заменить на обёртку.

**Готово, когда:**
- Существующие тесты на обработку `401`/`403` от GitLab (см. `SMOKE_TEST_PLAN.md`, пункт про
  «Ошибка сервиса: GitLab вернул 401/403…») проходят без изменения текста ошибки.
- Новый тест подтверждает повтор на `503`/timeout и отсутствие повтора на `404`.

---

### - [ ] 2.3. Healthcheck для discord-gateway

**Описание:** различать «процесс жив» и «процесс реально подключён к Discord и работает».

**Действия:**
- Добавить в `hermes/app/discord_bot.py` периодический heartbeat-лог (например в
  `on_ready`/фоновой задаче раз в N секунд) со статусом подключения.
- Добавить лёгкий HTTP-эндпоинт (минимальный `aiohttp`/`http.server` на localhost внутри
  контейнера), отдающий `200`, пока `discord.Client` в состоянии `is_ready()`.
- Добавить `HEALTHCHECK` в `hermes/Dockerfile`, использующий этот эндпоинт.

**Готово, когда:**
- `docker compose ps` показывает health-статус для `hermes-discord` (`healthy`/`unhealthy`).
- Искусственный обрыв соединения с Discord (например через `DISCORD_BOT_TOKEN=invalid` при
  старте) отражается как `unhealthy` в разумный срок.

---

## Этап 3. CI/CD

### - [ ] 3.1. CI workflow

**Описание:** автоматическая проверка на каждый push/PR.

**Действия:**
- Создать `.github/workflows/ci.yml`: шаги — `pytest hermes/tests -q`,
  `pytest dashboard-api/tests -q` (после этапа 4), `compileall hermes dashboard-api -q`,
  `docker compose config -q`, `npm --prefix dashboard-ui ci && npm --prefix dashboard-ui run
  build`.
- Добавить `eslint` в `dashboard-ui` (конфиг + `devDependencies` в `package.json`, скрипт
  `"lint": "eslint src"`), включить в workflow.

**Готово, когда:**
- Workflow зелёный на текущем состоянии `main` после выполнения предыдущих этапов.
- Намеренно сломанный тест на тестовой ветке даёт красный статус и блокирует мердж (если
  включена branch protection — задокументировать это как отдельный ручной шаг для владельца
  репозитория, PR это не настраивает).

---

### - [ ] 3.2. Release workflow

**Описание:** на тег `v*` — сборка и публикация образов, черновик GitHub Release.

**Действия:**
- Создать `.github/workflows/release.yml`: триггер на тег `v*.*.*`, сборка
  `hermes`/`dashboard-api`/`dashboard-ui` образов, публикация в GHCR
  (`ghcr.io/<owner>/techwriter-multi-agent-<service>`), создание Release-черновика (например
  через `softprops/action-gh-release`) с телом из соответствующего раздела `CHANGELOG.md`
  (после этапа 6) или из commit-сообщений, если `CHANGELOG.md` ещё не готов на момент
  выполнения этой задачи.

**Готово, когда:**
- Тестовый тег на форке (например `v0.3.1-test`) создаёт Release-черновик и публикует
  образы, либо (если публикация в GHCR недоступна в среде проверки) шаг публикации явно
  задокументирован как проверенный локально через `docker build`, а не в реальном workflow.

---

### - [ ] 3.3. Пиннинг зависимостей

**Описание:** детерминированная сборка образов.

**Действия:**
- Установить `pip-tools`, сгенерировать `hermes/requirements.lock` и
  `dashboard-api/requirements.lock` через `pip-compile` из соответствующих
  `requirements.txt`.
- Обновить `hermes/Dockerfile` и `dashboard-api/Dockerfile`: `pip install -r
  requirements.lock` вместо `requirements.txt` (сам `requirements.txt` остаётся как
  редактируемый источник верхнеуровневых ограничений).
- В `dashboard-ui/Dockerfile` заменить `npm install` на `npm ci`.

**Готово, когда:**
- Повторный запуск `pip-compile` без изменений в `requirements.txt` даёт тот же
  `requirements.lock` (детерминированность).
- `docker compose up -d --build` собирается на lock-файлах без ошибок.

---

## Этап 4. Тестовое покрытие

### - [ ] 4.1. Тесты dashboard-api

**Описание:** покрыть все эндпоинты `dashboard-api`, включая auth из задачи 0.1.

**Действия:**
- Добавить `testcontainers` в `dashboard-api/requirements.txt` (dev-группа, если она
  появится, иначе — отдельный `requirements-dev.txt`).
- Создать `dashboard-api/tests/` с фикстурой на эфемерный Postgres (testcontainers),
  применяющей `db/schema.sql`/миграции.
- Тесты на `/health`, `/api/overview`, `/api/activity`, `/api/sessions`, `/api/runs`,
  `/api/errors`, `/api/run-events/{run_id}`: пустая БД, БД с данными, невалидный `run_id`.
- Тест на `auth.py` из задачи 0.1 (если ещё не создан отдельно).

**Готово, когда:**
- `pytest dashboard-api/tests -q` зелёный локально и в CI (этап 3).
- Каждый эндпоинт имеет минимум по одному тесту на happy path и один на пустой/граничный
  случай.

---

### - [ ] 4.2. Тесты telemetry.py

**Описание:** закрыть тестами слой работы с БД в `hermes` (сейчас 0% покрытия).

**Действия:**
- Создать `hermes/tests/test_telemetry.py` с той же testcontainers-фикстурой, что в 4.1
  (вынести общую фикстуру в `conftest.py`, если формат тестов совпадает).
- Тесты на `ensure_session` (создание и `ON CONFLICT` обновление), `start_run`,
  `add_attachment`, `record_event`, `complete_run` (проверка `duration_ms`,
  `status`), `record_llm_call` (проверка агрегации `input_tokens`/`total_cost_usd` на
  `runs`).

**Готово, когда:**
- Все публичные функции модуля `telemetry.py` покрыты минимум одним тестом.
- `pytest hermes/tests -q` проходит вместе с уже существующими тестами.

---

### - [ ] 4.3. Тесты discord_bot.py

**Описание:** покрыть оркестрацию — маршрутизацию, обработку ошибок, форматирование ответа.

**Действия:**
- Создать `hermes/tests/test_discord_bot.py` с моками `discord.Message`/`discord.Client`
  (без реального подключения к Discord).
- Тесты на `_handle_route` (маршруты `unknown_short`, `unsupported_media`, обычный маршрут
  через мок `run_route`), `_result_filename` (разные комбинации route.kind/вложений),
  `_send_answer` (короткий ответ inline, длинный — файлом), обработку `SkillError` и общего
  `Exception` с/без активной телеметрии (`DATABASE_URL` пуст).

**Готово, когда:**
- Основные ветки функций покрыты, включая путь без телеметрии (`telemetry.is_enabled() ==
  False`).
- `pytest hermes/tests -q` проходит.

---

### - [ ] 4.4. Автоматизация smoke-теста

**Описание:** перенести автоматизируемую часть `SMOKE_TEST_PLAN.md` в CI-скрипт.

**Действия:**
- Создать скрипт (например `scripts/smoke-check.sh`/`.ps1` или Python-скрипт), который:
  поднимает `docker compose up -d --build`, дожидается готовности всех 4 сервисов, дёргает
  `/health` каждого, проверяет один happy-path через прямой вызов
  `hermes/app/router.classify` + `hermes/app/skills/runner.run_route` (без реального
  Discord — это физически недостижимо в CI).
- Обновить `runtimes/hermes/docs/SMOKE_TEST_PLAN.md`: явно разметить, какие пункты
  автоматизированы этим скриптом, а какие (раздел 3 «Discord end-to-end») остаются ручными.
- Подключить скрипт как шаг в `.github/workflows/release.yml` (этап 3.2) перед публикацией
  образов.

**Готово, когда:**
- Скрипт завершается с ненулевым кодом при недоступности любого из `/health`.
- `SMOKE_TEST_PLAN.md` однозначно показывает разделение «автоматизировано» / «вручную».

---

## Этап 5. Наблюдаемость

### - [ ] 5.1. `/metrics` эндпоинт

**Описание:** Prometheus-совместимые метрики поверх существующей телеметрии.

**Действия:**
- Добавить `prometheus-fastapi-instrumentator` в `dashboard-api/requirements.txt` либо
  реализовать ручной `/metrics`, отдающий агрегаты (`total_runs`, `error_runs`,
  `avg_duration_ms`, `total_cost_usd`) в формате Prometheus exposition из уже существующих
  запросов `overview()`.
- Задокументировать в `runtimes/hermes/README.md`, как подключить внешний Prometheus для
  scrape (эндпоинт `/metrics`, порт).

**Готово, когда:**
- `curl http://.../metrics` отдаёт корректный текст в формате Prometheus exposition
  (проверяется парсером `prometheus_client.parser`, если библиотека доступна, либо вручную по
  формату).

---

### - [ ] 5.2. Алерты на всплеск ошибок

**Описание:** уведомление при N `run_failed` за период.

**Действия:**
- Добавить `ALERT_WEBHOOK_URL` в `.env.example` как `[Уточнить позже]` — без значения по
  умолчанию, функциональность отключена, если переменная пуста.
- В `hermes/app/telemetry.py` (или отдельном модуле `hermes/app/alerts.py`) добавить
  проверку частоты ошибок при каждом `_complete_telemetry_failure` (`hermes/app/
  discord_bot.py`): если за последние 5 минут ≥ N ошибок (N — env
  `ALERT_ERROR_THRESHOLD`, дефолт 3), отправить POST на `ALERT_WEBHOOK_URL`.
- Не делать блокирующий HTTP-вызов в основном потоке обработки сообщения — выполнять через
  `asyncio.to_thread` по аналогии с остальной телеметрией.

**Готово, когда:**
- Тест с моком вебхука подтверждает вызов при достижении порога и отсутствие вызова при
  единичной ошибке ниже порога.
- Отсутствие `ALERT_WEBHOOK_URL` не приводит к ошибкам — функциональность тихо отключена
  (аналогично `telemetry.is_enabled()`).

---

## Этап 6. Гигиена релиза и документации

### - [ ] 6.1. Консолидация CHANGELOG

**Описание:** единый `CHANGELOG.md` по формату Keep a Changelog вместо трёх
`RELEASE_*.md`.

**Действия:**
- Создать `CHANGELOG.md`, перенести содержимое `RELEASE_v0.1.0-alpha.1.md`,
  `RELEASE_v0.2.0-alpha.1.md`, `RELEASE_v0.3.0-alpha.1.md` как разделы `## [0.1.0-alpha.1]`,
  `## [0.2.0-alpha.1]`, `## [0.3.0-alpha.1]` (в хронологическом порядке, новые сверху).
- Обновить `README.md`: раздел "Release Recommendation" — указать актуальную версию
  (совпадающую с последней записью `CHANGELOG.md`), убрать хардкод `v0.2.0-alpha.1`.
- Решить судьбу файлов `RELEASE_*.md` (оставить как архив или удалить) —
  **зафиксировать решение явно в описании PR**, не удалять молча.

**Готово, когда:**
- `README.md` и `CHANGELOG.md` называют одну и ту же версию.
- Ссылки в `README.md` на релизные заметки (если есть) ведут на актуальный файл.

---

### - [ ] 6.2. CONTRIBUTING.md, SECURITY.md, issue/PR-шаблоны

**Описание:** стандартный набор файлов для репозитория, рассчитанного на внешних
контрибьюторов.

**Действия:**
- `CONTRIBUTING.md`: процесс контрибьюции, ссылка на `AGENTS.md` как источник конвенций
  (не дублировать содержимое), команды верификации из раздела "Верификация перед коммитом".
- `SECURITY.md`: как сообщать об уязвимостях (email/issue с меткой security), сроки ответа —
  `[Уточнить у владельца]`, если процесс ещё не определён.
- `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`,
  `.github/PULL_REQUEST_TEMPLATE.md` — минимальные, со ссылкой на `AGENTS.md` и чек-лист
  верификации.

**Готово, когда:**
- Все перечисленные файлы существуют и ссылаются на реальные, актуальные команды/пути
  репозитория (не на вымышленные).

---

### - [ ] 6.3. Судьба DOC_LINTER_SPEC.md

**Описание:** закрыть статус функциональности doc-review, упомянутой как «в разработке» в
`RELEASE_v0.3.0-alpha.1.md`, но фактически не присутствующей в репозитории (файл
игнорируется гитом).

**Действия:**
- **Не принимать решение самостоятельно.** Подготовить в PR-описании два варианта:
  (а) закоммитить `DOC_LINTER_SPEC.md` как публичную дорожную карту (убрать из
  `.gitignore`), (б) явно зафиксировать в `CHANGELOG.md`/README, что doc-review отложен без
  даты, без публикации спеки.
- Пометить задачу `[Требует решения владельца репозитория]` в трекере задач.

**Готово, когда:**
- В `CHANGELOG.md`/`README.md` появилась одна однозначная формулировка статуса
  doc-review-функциональности — по итогам решения владельца, принятого вне этого
  автоматизированного плана.

---

## Этап 7. Расширение (опционально, после релиза)

> Выполняется только после того, как этапы 0–6 приняты и смёржены. Не начинать без
> отдельного подтверждения — это функциональные изменения, а не инфраструктурный хардненинг.

### - [ ] 7.1. LLM-ассистированная классификация намерений (fallback)

**Описание:** добавить fallback-классификатор для случаев, когда `router.classify()` не даёт
уверенного маршрута — не заменяя существующую regex/keyword логику.

**Действия:**
- Определить критерий «неуверенного» результата в `hermes/app/router.py` (например,
  сообщение попадает в `spec_text` по умолчанию, но не содержит признаков постановки).
  `[Уточнить позже]` — конкретный критерий и модель для fallback-вызова.
- Добавить вызов LLM-классификатора только для пограничных случаев, с записью в телеметрию
  (`record_event`), что маршрут определён через fallback, а не regex.

**Готово, когда:**
- `hermes/tests/test_router.py` проходит без изменений (regex остаётся основным путём для
  всех текущих тестовых кейсов).
- Новые тесты покрывают fallback-путь с моком LLM-вызова.

---

### - [ ] 7.2. Абстракция канала ввода

**Описание:** подготовить интерфейс, не привязанный жёстко к `discord.py`, для будущих
каналов (Slack, web-widget) — без подключения новых каналов в рамках этой задачи.

**Действия:**
- Выделить `Protocol`/интерфейс (например `IncomingChannel`) в `hermes/app/`, описывающий
  минимальный контракт: получение `IncomingMessage`, отправка ответа, вложения.
- Переоформить `HermesDiscordClient` (`hermes/app/discord_bot.py`) как одну из реализаций
  этого интерфейса, не меняя его внешнего поведения.

**Готово, когда:**
- Все существующие тесты (`hermes/tests`) проходят без изменений в ожидаемом поведении.
- Интерфейс задокументирован в `core/README.md` как runtime-независимая точка расширения
  (сам `core/` остаётся runtime-независимым, конкретная реализация — в `hermes/`).

---

## Заметки

> Сюда кодинговый агент добавляет вопросы, возникшие в процессе, и решения, принятые по
> пунктам `[Уточнить позже]` / `[Требует решения владельца]`.
