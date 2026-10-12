# =============================================================================
# SIMAP - levantar el backend en local.
#
#   .\tools\levantar-backend.ps1
#
# 1. Arranca PostgreSQL y Redis (docker compose) y espera a que la base responda.
# 2. Aplica las migraciones pendientes (no hace nada si no hay).
# 3. Libera el puerto 8000 si quedo un servidor colgado.
# 4. Arranca la API con recarga automatica en http://localhost:8000 (docs en /docs).
#
# COOKIE_SECURE=false porque en local no hay HTTPS: con true el navegador descarta la cookie de
# sesion y no se puede entrar. Solo afecta a esta terminal.
# La API escucha solo en 127.0.0.1: el telefono no habla con ella, habla con el frontend, que le
# reenvia las llamadas.
# =============================================================================

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "No existe .venv. Ejecuta primero .\tools\setup.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "1/4 Base de datos y Redis..." -ForegroundColor Cyan
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    Docker no responde. Abre Docker Desktop y vuelve a ejecutar este script." -ForegroundColor Red
    exit 1
}
Push-Location $raiz
docker compose up -d db redis | Out-Null
Pop-Location
for ($i = 0; $i -lt 30; $i++) {
    docker compose -f (Join-Path $raiz "docker-compose.yml") exec -T db pg_isready -U simap *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
}

$env:PYTHONIOENCODING = "utf-8"
Push-Location (Join-Path $raiz "backend")
try {
    Write-Host "2/4 Migraciones..." -ForegroundColor Cyan
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Fallaron las migraciones." }

    Write-Host "3/4 Puerto 8000..." -ForegroundColor Cyan
    Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

    Write-Host "4/4 API en http://localhost:8000  (Ctrl+C para parar)" -ForegroundColor Green
    $env:COOKIE_SECURE = "false"
    & $python -m uvicorn app.main:app --reload --port 8000
}
finally {
    Pop-Location
}
