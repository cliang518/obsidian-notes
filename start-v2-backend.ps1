$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$pythonCandidates = @(
    (Join-Path $backendDir "venv\\Scripts\\python.exe"),
    "E:\cctv-maintenance\backend\venv\Scripts\python.exe",
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe",
    "D:\Python314\python.exe"
)

$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    throw "No usable Python runtime found for V2 backend."
}
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (Test-Path $pythonw) {
    $python = $pythonw
}

$existing = Get-NetTCPConnection -LocalPort 8011 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    Write-Output "V2 backend already listening on 8011."
    exit 0
}

Push-Location $backendDir
try {
    Start-Process -FilePath $python -ArgumentList (Join-Path $backendDir "run.py") -WorkingDirectory $backendDir -WindowStyle Hidden
    Write-Output "V2 backend started in background on 8011 using $python."
}
finally {
    Pop-Location
}
