#!/usr/bin/env bash
# Проверяет установку techwriter-super-agent: .env, skill-пакеты, docker compose.
# Код выхода 1, если есть хотя бы один FAIL.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
FAILURES=0

report() {
  local level="$1"; shift
  echo "[$level] $*"
  if [ "$level" = "FAIL" ]; then FAILURES=$((FAILURES + 1)); fi
}

# --- .env и секреты ---
if [ -f "$REPO_ROOT/.env" ]; then
  report OK ".env найден"
  for key in DISCORD_BOT_TOKEN OPENROUTER_API_KEY; do
    if grep -qE "^${key}=.+" "$REPO_ROOT/.env"; then report OK "$key задан"; else report FAIL "$key не задан в .env"; fi
  done
  for key in GITHUB_TOKEN GITLAB_TOKEN JIRA_API_TOKEN FIGMA_TOKEN; do
    if grep -qE "^${key}=.+" "$REPO_ROOT/.env"; then report OK "$key задан (опционально)"; else report WARN "$key не задан — связанные сценарии будут недоступны"; fi
  done
  if grep -qE "^POSTGRES_PASSWORD=postgres\s*$" "$REPO_ROOT/.env"; then
    report FAIL "POSTGRES_PASSWORD всё ещё дефолтный 'postgres' — .env создан вручную из старого .env.example, замените пароль"
  elif grep -qE "^POSTGRES_PASSWORD=.+" "$REPO_ROOT/.env"; then
    report OK "POSTGRES_PASSWORD не дефолтный"
  else
    report FAIL "POSTGRES_PASSWORD не задан в .env"
  fi
  if grep -qE "^DASHBOARD_API_KEY=.+" "$REPO_ROOT/.env"; then
    report OK "DASHBOARD_API_KEY задан"
  else
    report FAIL "DASHBOARD_API_KEY не задан в .env — dashboard-api откажется стартовать"
  fi
else
  report FAIL ".env не найден. Запустите runtimes/hermes/install.sh"
fi

# --- manifest ---
if [ -f "$REPO_ROOT/manifest.yaml" ]; then report OK "manifest.yaml найден"; else report FAIL "manifest.yaml не найден в корне репозитория"; fi

# --- skill-пакеты ---
for skill in spec2doc api-docs release-notes figma-guide; do
  pkg="$REPO_ROOT/runtimes/hermes/skills/$skill"
  if [ -f "$pkg/SKILL.md" ] && compgen -G "$pkg/instructions*.md" >/dev/null; then
    report OK "skill $skill: пакет в порядке"
  else
    report FAIL "skill $skill: нет SKILL.md или instructions*.md в $pkg"
  fi
done

# --- docker compose ---
if command -v docker >/dev/null 2>&1; then
  if docker compose -f "$REPO_ROOT/docker-compose.yml" config -q >/dev/null 2>&1; then
    report OK "docker compose config валиден"
  else
    report FAIL "docker compose config вернул ошибку"
  fi
else
  report WARN "docker не найден — проверка compose пропущена"
fi

# --- state ---
if [ -d "$REPO_ROOT/hermes/state" ]; then report OK "hermes/state существует"; else report WARN "hermes/state не создан — install.sh создаст его автоматически"; fi

echo ""
if [ "$FAILURES" -gt 0 ]; then echo "Итог: $FAILURES FAIL"; exit 1; fi
echo "Итог: установка в порядке"
exit 0
