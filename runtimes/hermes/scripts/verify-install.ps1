#Requires -Version 5.1
<#
.SYNOPSIS
  Проверяет установку techwriter-super-agent: .env, skill-пакеты, docker compose.
  Код выхода 1, если есть хотя бы один FAIL.
#>
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..\..')).Path
$script:failures = 0

function Report([string]$Level, [string]$Message) {
  Write-Host "[$Level] $Message"
  if ($Level -eq 'FAIL') { $script:failures++ }
}

# --- .env и секреты ---
$EnvFile = Join-Path $RepoRoot '.env'
if (Test-Path $EnvFile) {
  Report 'OK' '.env найден'
  $envContent = Get-Content $EnvFile -Raw
  foreach ($key in 'DISCORD_BOT_TOKEN', 'OPENROUTER_API_KEY') {
    if ($envContent -match "(?m)^$key=\S+") { Report 'OK' "$key задан" }
    else { Report 'FAIL' "$key не задан в .env" }
  }
  foreach ($key in 'GITHUB_TOKEN', 'GITLAB_TOKEN', 'JIRA_API_TOKEN', 'FIGMA_TOKEN') {
    if ($envContent -match "(?m)^$key=\S+") { Report 'OK' "$key задан (опционально)" }
    else { Report 'WARN' "$key не задан — связанные сценарии будут недоступны" }
  }
  if ($envContent -match '(?m)^POSTGRES_PASSWORD=postgres\s*$') {
    Report 'FAIL' "POSTGRES_PASSWORD всё ещё дефолтный 'postgres' — .env создан вручную из старого .env.example, замените пароль"
  } elseif ($envContent -match '(?m)^POSTGRES_PASSWORD=\S+') {
    Report 'OK' 'POSTGRES_PASSWORD не дефолтный'
  } else {
    Report 'FAIL' 'POSTGRES_PASSWORD не задан в .env'
  }
  if ($envContent -match '(?m)^DASHBOARD_API_KEY=\S+') {
    Report 'OK' 'DASHBOARD_API_KEY задан'
  } else {
    Report 'FAIL' 'DASHBOARD_API_KEY не задан в .env — dashboard-api откажется стартовать'
  }
} else {
  Report 'FAIL' '.env не найден. Запустите runtimes\hermes\install.ps1'
}

# --- manifest ---
if (Test-Path (Join-Path $RepoRoot 'manifest.yaml')) { Report 'OK' 'manifest.yaml найден' }
else { Report 'FAIL' 'manifest.yaml не найден в корне репозитория' }

# --- skill-пакеты ---
$SkillsDir = Join-Path $RepoRoot 'runtimes\hermes\skills'
foreach ($skill in 'spec2doc', 'api-docs', 'release-notes', 'figma-guide') {
  $pkg = Join-Path $SkillsDir $skill
  $hasSkill = Test-Path (Join-Path $pkg 'SKILL.md')
  $hasInstructions = @(Get-ChildItem (Join-Path $pkg 'instructions*.md') -ErrorAction SilentlyContinue).Count -gt 0
  if ($hasSkill -and $hasInstructions) { Report 'OK' "skill ${skill}: пакет в порядке" }
  else { Report 'FAIL' "skill ${skill}: нет SKILL.md или instructions*.md в $pkg" }
}

# --- docker compose ---
if (Get-Command docker -ErrorAction SilentlyContinue) {
  docker compose -f (Join-Path $RepoRoot 'docker-compose.yml') config -q 2>$null
  if ($LASTEXITCODE -eq 0) { Report 'OK' 'docker compose config валиден' }
  else { Report 'FAIL' 'docker compose config вернул ошибку' }
} else {
  Report 'WARN' 'docker не найден — проверка compose пропущена'
}

# --- state ---
if (Test-Path (Join-Path $RepoRoot 'hermes\state')) { Report 'OK' 'hermes\state существует' }
else { Report 'WARN' 'hermes\state не создан — install.ps1 создаст его автоматически' }

Write-Host ''
if ($script:failures -gt 0) { Write-Host "Итог: $($script:failures) FAIL"; exit 1 }
Write-Host 'Итог: установка в порядке'
exit 0
