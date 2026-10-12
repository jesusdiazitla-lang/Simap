# =============================================================================
# SIMAP - levantar el frontend en local.
#
#   .\tools\levantar-frontend.ps1          compila y arranca la version de produccion
#   .\tools\levantar-frontend.ps1 -Dev     modo desarrollo (recarga al editar)
#
# Por defecto compila y arranca la version de PRODUCCION, que es la unica en la que funcionan el
# service worker (modo sin conexion) y la entrada desde el telefono por la red local: `next dev`
# bloquea parte de sus recursos cuando no se entra por localhost.
#
# Libera el puerto 3000 ANTES de compilar. Si un servidor viejo sigue vivo mientras se recompila,
# sirve archivos que ya no existen y la pagina sale sin estilos (paso el 2026-10-07).
#
# Necesita el backend levantado (.\tools\levantar-backend.ps1).
# =============================================================================

param([switch]$Dev)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $raiz "frontend")
try {
    Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

    # Direccion por la que el telefono llega a este PC en la Wi-Fi, solo para mostrarla.
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -like "Wi-Fi*" -or $_.InterfaceAlias -like "Ethernet*" } |
        Where-Object { $_.IPAddress -notlike "169.254*" } |
        Select-Object -First 1 -ExpandProperty IPAddress

    if ($Dev) {
        Write-Host "Modo desarrollo en http://localhost:3000  (Ctrl+C para parar)" -ForegroundColor Green
        Write-Host "Sin modo sin conexion ni acceso desde el telefono: para eso, sin -Dev." -ForegroundColor Yellow
        # --webpack: el compilador nativo de Next suele fallar en esta maquina por Avast.
        npx next dev --webpack --port 3000
        return
    }

    Write-Host "1/2 Compilando..." -ForegroundColor Cyan
    npx next build --webpack
    if ($LASTEXITCODE -ne 0) { throw "La compilacion fallo." }

    Write-Host "2/2 Frontend en marcha  (Ctrl+C para parar)" -ForegroundColor Green
    Write-Host "    En este PC:       http://localhost:3000"
    if ($ip) {
        Write-Host "    En el telefono:   http://${ip}:3000"
        Write-Host "    (los QR llevan APP_BASE_URL de backend\.env; si la IP cambio, actualizala alli)" -ForegroundColor DarkGray
    }
    npx next start --port 3000
}
finally {
    Pop-Location
}
