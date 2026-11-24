# Arranca los 4 servicios en local sin Docker (SQLite + eventos por HTTP).
# Uso:  .\run_local.ps1        Detener:  .\run_local.ps1 -Stop
param([switch]$Stop)

$root = $PSScriptRoot
$pidFile = Join-Path $root ".local-pids"

if ($Stop) {
    if (Test-Path $pidFile) {
        Get-Content $pidFile | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
        Remove-Item $pidFile
    }
    Write-Host "Servicios detenidos."
    return
}

$venv = Join-Path $root ".venv"
if (-not (Test-Path $venv)) {
    python -m venv $venv
    & "$venv\Scripts\pip.exe" install -q fastapi "uvicorn[standard]" httpx "sqlalchemy[asyncio]" aiosqlite redis
}
$py = "$venv\Scripts\python.exe"

$services = @(
    @{ Name = "shortener"; Port = 8001 },
    @{ Name = "redirect";  Port = 8002 },
    @{ Name = "analytics"; Port = 8003 },
    @{ Name = "gateway";   Port = 8000 }
)
$pids = foreach ($s in $services) {
    $dir = Join-Path $root "services\$($s.Name)"
    $p = Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "app.main:app", "--port", $s.Port `
        -WorkingDirectory $dir -WindowStyle Hidden -PassThru
    $p.Id
}
$pids | Set-Content $pidFile
Write-Host "Listo: http://localhost:8000  (detener con .\run_local.ps1 -Stop)"
