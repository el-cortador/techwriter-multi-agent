#Requires -Version 5.1
<#
.SYNOPSIS
  Подготавливает локальную установку techwriter-super-agent (Docker Compose).
.DESCRIPTION
  Идемпотентно: существующий .env и состояние не перезаписываются.
#>
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$RuntimeDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $RuntimeDir '..\..')).Path

if (-not (Test-Path (Join-Path $RepoRoot 'hermes\app\main.py'))) {
  throw "Скрипт должен находиться в runtimes\hermes\ репозитория techwriter-super-agent"
}

Write-Host "==> techwriter-super-agent install"

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
  Write-Host "  [ok] docker найден"
} else {
  Write-Host "  [warn] docker не найден в PATH. Установите Docker Desktop перед запуском."
}

function New-Secret {
  ((New-Guid).ToString('N') + (New-Guid).ToString('N'))
}

$EnvExample = Join-Path $RepoRoot '.env.example'
$EnvFile = Join-Path $RepoRoot '.env'
if (Test-Path $EnvFile) {
  Write-Host "  [skip] .env уже существует — не перезаписываю"
} else {
  Copy-Item $EnvExample $EnvFile
  $postgresPassword = New-Secret
  $dashboardApiKey = New-Secret
  $content = Get-Content $EnvFile -Raw
  $content = $content -replace '(?m)^POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$postgresPassword"
  $content = $content -replace '(?m)^DASHBOARD_API_KEY=.*', "DASHBOARD_API_KEY=$dashboardApiKey"
  $content = $content -replace '(?m)^DATABASE_URL=.*', "DATABASE_URL=postgresql://postgres:$postgresPassword@postgres:5432/agent_dashboard"
  Set-Content -Path $EnvFile -Value $content -NoNewline -Encoding utf8
  Write-Host "  [ok] создан .env из .env.example (сгенерированы POSTGRES_PASSWORD и DASHBOARD_API_KEY)"
}

$StateDir = Join-Path $RepoRoot 'hermes\state'
if (Test-Path $StateDir) {
  Write-Host "  [skip] hermes\state уже существует"
} else {
  New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
  Write-Host "  [ok] создан hermes\state"
}

Write-Host @"

Готово. Следующие шаги:
  1. Заполните секреты в .env (минимум DISCORD_BOT_TOKEN и OPENROUTER_API_KEY)
  2. docker compose up -d --build
  3. Откройте дашборд: http://127.0.0.1:4173
  4. Проверьте установку: runtimes\hermes\scripts\verify-install.ps1
"@
