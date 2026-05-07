$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Start-Process powershell -WindowStyle Hidden -ArgumentList "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "start-v2-backend.ps1")
Start-Sleep -Seconds 1
Start-Process powershell -WindowStyle Hidden -ArgumentList "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "start-v2-frontend.ps1")
