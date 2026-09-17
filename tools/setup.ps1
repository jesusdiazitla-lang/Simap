# Prepara el entorno de desarrollo de SIMAP en Windows.
#   - venv + dependencias backend (con CA de Avast si está presente, sin desactivar TLS)
#   - npm install del frontend
#   - registra .githooks como hooksPath
#   - construye el grafo inicial
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== [1/4] Python venv" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = Join-Path $root ".venv\Scripts\python.exe"

# Avast intercepta TLS: añadimos su CA al bundle de certifi para pip.
$avast = "C:\ProgramData\Avast Software\Avast\wscert.pem"
if (Test-Path $avast) {
    $certDir = Join-Path $env:USERPROFILE ".certs"
    New-Item -ItemType Directory -Force -Path $certDir | Out-Null
    $bundle = Join-Path $certDir "ca-bundle-avast.pem"
    $base = & $py -c "from pip._vendor import certifi; print(certifi.where())"
    (Get-Content $base -Raw) + "`n# Avast Web/Mail Shield Root`n" + (Get-Content $avast -Raw) | Set-Content $bundle -Encoding ascii
    "[global]`ncert = $bundle" | Set-Content ".venv\pip.ini" -Encoding ascii
    Write-Host "   CA de Avast añadida al bundle de pip ($bundle)"
}
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r backend\requirements-dev.txt --quiet

Write-Host "== [2/4] Frontend npm install" -ForegroundColor Cyan
Push-Location frontend; npm install; Pop-Location

Write-Host "== [3/4] Git hooks" -ForegroundColor Cyan
git config core.hooksPath .githooks

Write-Host "== [4/4] Grafo inicial" -ForegroundColor Cyan
$env:PYTHONIOENCODING = "utf-8"
& $py tools\graph\graph.py build

Write-Host "`nListo. Activa el venv con: .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
