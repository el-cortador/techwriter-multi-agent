#!/usr/bin/env bash
# Подготавливает локальную установку techwriter-super-agent (Docker Compose).
# Идемпотентно: существующий .env и состояние не перезаписываются.
set -euo pipefail

RUNTIME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$RUNTIME_DIR/../.." && pwd)"

if [ ! -f "$REPO_ROOT/hermes/app/main.py" ]; then
  echo "ERROR: скрипт должен находиться в runtimes/hermes/ репозитория techwriter-super-agent" >&2
  exit 1
fi

echo "==> techwriter-super-agent install"

if command -v docker >/dev/null 2>&1; then
  echo "  [ok] docker найден"
else
  echo "  [warn] docker не найден в PATH. Установите Docker перед запуском."
fi

generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

if [ -f "$REPO_ROOT/.env" ]; then
  echo "  [skip] .env уже существует — не перезаписываю"
else
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  postgres_password="$(generate_secret)"
  dashboard_api_key="$(generate_secret)"
  sed -i.bak "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${postgres_password}/" "$REPO_ROOT/.env"
  sed -i.bak "s/^DASHBOARD_API_KEY=.*/DASHBOARD_API_KEY=${dashboard_api_key}/" "$REPO_ROOT/.env"
  sed -i.bak "s#^DATABASE_URL=.*#DATABASE_URL=postgresql://postgres:${postgres_password}@postgres:5432/agent_dashboard#" "$REPO_ROOT/.env"
  rm -f "$REPO_ROOT/.env.bak"
  echo "  [ok] создан .env из .env.example (сгенерированы POSTGRES_PASSWORD и DASHBOARD_API_KEY)"
fi

if [ -d "$REPO_ROOT/hermes/state" ]; then
  echo "  [skip] hermes/state уже существует"
else
  mkdir -p "$REPO_ROOT/hermes/state"
  echo "  [ok] создан hermes/state"
fi

cat <<'EOF'

Готово. Следующие шаги:
  1. Заполните секреты в .env (минимум DISCORD_BOT_TOKEN и OPENROUTER_API_KEY)
  2. docker compose up -d --build
  3. Откройте дашборд: http://127.0.0.1:4173
  4. Проверьте установку: runtimes/hermes/scripts/verify-install.sh
EOF
