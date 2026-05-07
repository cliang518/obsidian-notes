$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tool = Join-Path $root "tools\\v2_tray_launcher.py"
$distDir = Join-Path $root "dist"
$pythonCandidates = @(
    (Join-Path $root "backend\\venv\\Scripts\\python.exe"),
    "E:\\cctv-maintenance\\backend\\venv\\Scripts\\python.exe",
    "D:\\Python314\\python.exe"
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $python) {
    throw "No usable Python runtime found for V2 tray build."
}

if (!(Test-Path $distDir)) {
    New-Item -ItemType Directory -Path $distDir | Out-Null
}

Push-Location $root
try {
    & $python -m PyInstaller `
        --noconsole `
        --onefile `
        --clean `
        --name YongjiaWeakCurrentV2Tray `
        $tool
}
finally {
    Pop-Location
}
