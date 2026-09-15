# Runtime: Hermes (Discord gateway)

Runtime-упаковка techwriter-super-agent: skill-пакеты, установка, проверка и эксплуатация
поверх self-hosted Docker Compose стека.

## Состав

```text
skills/                 Skill-пакеты (SKILL.md + instructions*.md + references/)
  spec2doc/             Черновик инструкции из постановки (текст, PDF, DOC, DOCX, MD) или merge request GitLab
  api-docs/             Документация по API (OpenAPI или текст)
  release-notes/        Release notes / changelog из GitHub и Jira
  figma-guide/          Руководство по интерфейсу (Figma URL или скриншот)
install.ps1             Установка на Windows (идемпотентная, не перезаписывает .env)
install.sh              Установка на Linux/macOS (зеркало install.ps1)
scripts/
  verify-install.ps1    Проверка установки (OK/WARN/FAIL, код выхода 1 при FAIL)
  verify-install.sh     Зеркало для Linux/macOS
  purge-telemetry.py    Ретеншн: удаляет старые events/llm_calls (кроссплатформенный)
docs/
  SMOKE_TEST_PLAN.md    Ручная проверка после установки/обновления
  TROUBLESHOOTING.md    Симптом → причина → исправление
```

## Установка

```powershell
# Windows
runtimes\hermes\install.ps1

# Linux/macOS
runtimes/hermes/install.sh
```

Скрипт создает `.env` из `.env.example` (если отсутствует) и каталог состояния
`hermes/state/`. Существующие файлы не перезаписываются.

## Настройка

Обязательные секреты в `.env` (см. также `manifest.yaml`):

| Переменная | Назначение |
|---|---|
| `DISCORD_BOT_TOKEN` | Токен Discord-бота (нужен Message Content Intent) |
| `OPENROUTER_API_KEY` | Ключ OpenRouter для LLM и vision |

Опциональные: `GITHUB_TOKEN` (приватные репозитории), `GITLAB_TOKEN` (merge request'ы,
для приватных проектов обязателен), `JIRA_EMAIL` + `JIRA_API_TOKEN` (Jira-маршруты),
`FIGMA_TOKEN` (приватные Figma-файлы). Полный список — в `.env.example`.

## Запуск

```powershell
docker compose up -d --build
```

Сервис `hermes-discord` собирается из контекста репозитория: код gateway (`hermes/app/`)
и skill-пакеты (`runtimes/hermes/skills/` → `/app/skills/`, переменная `HERMES_SKILLS_DIR`).

## Проверка

```powershell
runtimes\hermes\scripts\verify-install.ps1   # установка
# smoke test — по чек-листу docs/SMOKE_TEST_PLAN.md
```

## Ретеншн телеметрии

`events` и `llm_calls` хранят подробный лог по каждому запросу/LLM-вызову и растут быстрее,
чем `sessions`/`runs`. `scripts/purge-telemetry.py` удаляет из них строки старше N дней
(агрегаты в `runs.total_tokens`/`runs.total_cost_usd` не трогает — они уже посчитаны).

Разово, локально (нужен `.env` с `DATABASE_URL`):

```powershell
.venv\Scripts\python runtimes\hermes\scripts\purge-telemetry.py 90
```

Внутри уже запущенного стека:

```powershell
docker compose exec hermes-discord python scripts/purge-telemetry.py 90
```

Без аргумента скрипт берет `TELEMETRY_RETENTION_DAYS` из окружения (по умолчанию 90).
Для регулярного запуска — обычный cron/Task Scheduler на хосте, вызывающий команду выше;
отдельного сервиса в `docker-compose.yml` под это не заводится.

## Пути

| Назначение | Локально | В контейнере |
|---|---|---|
| Skill-пакеты | `runtimes/hermes/skills/` | `/app/skills/` |
| Состояние рантайма | `hermes/state/` | `/app/state/` (volume) |
| Код gateway | `hermes/app/` | `/app/app/` |
