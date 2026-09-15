# Troubleshooting

Формат: симптом → вероятная причина → исправление.

## Discord-бот молчит (вообще не отвечает)

- Причина: не включен **Message Content Intent** в настройках бота.
  Исправление: Discord Developer Portal → Bot → Privileged Gateway Intents → Message Content Intent.
- Причина: сообщение не проходит allowlist (`DISCORD_ALLOWED_GUILD_IDS` / `CHANNEL_IDS` / `USER_IDS`).
  Исправление: сверить ID сервера/канала/пользователя с `.env`; при пустых списках бот отвечает всем.
- Причина: контейнер упал. Исправление: `docker compose logs hermes-discord`.

## «Ошибка сервиса: OPENROUTER_API_KEY is not set»

- Причина: ключ не задан или `.env` не подхвачен. Исправление: заполнить `OPENROUTER_API_KEY` в `.env`,
  `docker compose up -d` (compose читает `.env` из корня репозитория).

## GitHub: «вернул 401/403»

- Причина: приватный репозиторий без `GITHUB_TOKEN` или невалидный токен.
  Исправление: задать `GITHUB_TOKEN` (scope `repo`); для публичных репозиториев токен не нужен.

## GitLab: «вернул 401/403» или «Merge request не найден»

- Причина: приватный проект без `GITLAB_TOKEN` или токен без scope `read_api`.
  Исправление: выпустить Personal/Project Access Token со scope `read_api` и задать `GITLAB_TOKEN`.
- Причина: self-hosted GitLab недоступен из контейнера (VPN, внутренний DNS).
  Исправление: проверить `docker compose exec hermes-discord python -c "import requests; print(requests.get('<base>/api/v4/version').status_code)"`.
- Причина: ссылка ведет на GitHub pull request — этот источник не поддерживается,
  запрос уйдет в другой маршрут.

## Jira: «вернул 401/403/404»

- Причина: неверные `JIRA_EMAIL` / `JIRA_API_TOKEN` или нет доступа к задаче.
  Исправление: перевыпустить API-токен в Atlassian, проверить доступ к задаче в браузере той же учеткой.

## Figma: «Ошибка авторизации» / «файл не найден»

- Причина: файл приватный, а `FIGMA_TOKEN` не задан; либо ссылка не содержит file id.
  Исправление: задать `FIGMA_TOKEN` или открыть доступ «anyone with the link can view».
  Rate limit (429) — повторить через минуту.

## Файл не разбирается: «Неподдерживаемый формат …»

- Поддерживаются `.pdf`, `.doc`, `.docx`, `.md`, `.markdown`, `.txt` (до 50 МБ).
  Исправление: пересохранить документ в один из этих форматов. `.rtf` разбирается
  только если он пришел с расширением `.doc`.
- Причина (`.doc`): «Файл .doc не распознан как документ Word» — это не OLE-файл
  (например, RTF или HTML с расширением `.doc`). Исправление: пересохранить в DOCX или PDF.
- Причина (`.doc`): «Для чтения .doc требуется пакет olefile» — образ собран до добавления
  зависимости. Исправление: `docker compose build hermes-discord`.

## Дашборд пустой / нет данных

- Причина: `DATABASE_URL` недоступен или схема еще не создана (создается миграциями Alembic
  при первом старте `hermes-discord`/`dashboard-api`, см. «Ошибка миграции Alembic» ниже).
  Исправление: убедиться, что `postgres` в `running`, отправить любой запрос боту, обновить дашборд.
- Причина: запросы были до включения телеметрии. Backfill не поддерживается (alpha-ограничение).

## Дашборд: «API key required» / запрос к `/api/*` вернул 401

- Причина: в `dashboard-ui` не введён или неверен ключ. Исправление: взять значение
  `DASHBOARD_API_KEY` из `.env` и ввести его на экране входа.
- Причина: `DASHBOARD_API_KEY` в `.env` пуст. Исправление: задать значение и
  `docker compose up -d dashboard-api` (сервис откажется стартовать с пустым ключом).

## Ошибка миграции Alembic при старте (`hermes-discord` / `dashboard-api` не поднимаются)

- Причина: `DATABASE_URL` указывает не на ту БД, либо Postgres еще не готов принимать
  соединения. Исправление: `hermes-discord` уже повторяет `alembic upgrade head` 10 раз с
  паузой — подождать; если не помогает, проверить `docker compose logs postgres`.
- Причина: схема была создана вручную/старым кодом (до Alembic) и отличается от
  `db/migrations/versions/d4b6fd9bff93_baseline_schema.py`. Исправление: проверить
  `SELECT * FROM alembic_version;` — если таблицы `sessions`/`runs`/… уже существуют, а
  строки `alembic_version` нет, миграция безопасно доотметит текущую версию, так как
  baseline использует `CREATE TABLE IF NOT EXISTS`/`CREATE INDEX IF NOT EXISTS`.
- Проверка вручную из корня репозитория:
  `DATABASE_URL=... .venv/Scripts/python -m alembic -c db/alembic.ini current`.

## «Skill instructions not found: /app/skills/...»

- Причина: образ собран без skill-пакетов (старый Dockerfile с контекстом `./hermes`).
  Исправление: пересобрать из корня репозитория: `docker compose build hermes-discord`.
  Проверить, что `runtimes/hermes/skills/` содержит 4 пакета.

## Транскрибация аудио/видео не работает

- Это намеренное ограничение alpha: лимиты Discord на размер вложений.
  Ответ бота об этом — ожидаемое поведение, а не сбой.

## Медленные ответы / таймауты внешних API

- Причина: `REQUEST_TIMEOUT` слишком мал для медленной сети. Исправление: увеличить в `.env` (по умолчанию 15 с).
