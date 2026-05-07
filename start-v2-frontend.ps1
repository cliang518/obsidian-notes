$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $root "frontend"
$distDir = Join-Path $frontendDir "dist"
$srcDir = Join-Path $frontendDir "src"
$pythonCandidates = @(
    (Join-Path $root "backend\\venv\\Scripts\\python.exe"),
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe",
    "D:\Python314\python.exe",
    "E:\cctv-maintenance\backend\venv\Scripts\python.exe"
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    throw "No usable Python runtime found for V2 frontend static server."
}
$logDir = Join-Path $root "runtime\logs"
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$nodeModules = Join-Path $frontendDir "node_modules"
$legacyNodeModules = "E:\cctv-maintenance\frontend\node_modules"

if (!(Test-Path $nodeModules) -and (Test-Path $legacyNodeModules)) {
    New-Item -ItemType Junction -Path $nodeModules -Target $legacyNodeModules | Out-Null
}

Push-Location $frontendDir
try {
    $distIndex = Join-Path $distDir "index.html"
    $needsBuild = !(Test-Path $distIndex)
    if (-not $needsBuild) {
        $distTimestamp = (Get-Item $distIndex).LastWriteTimeUtc
        $latestSource = Get-ChildItem -Path $srcDir -Recurse -File |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($latestSource -and $latestSource.LastWriteTimeUtc -gt $distTimestamp) {
            $needsBuild = $true
        }
    }

    if ($needsBuild) {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm", "run", "build" -WorkingDirectory $frontendDir -WindowStyle Hidden -Wait
    }

    $existing = Get-NetTCPConnection -LocalPort 3011 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existing) {
        Write-Output "V2 frontend already listening on 3011."
        exit 0
    }

    $serverScript = Join-Path $root "tools\\spa_static_server.py"
    $stdoutLog = Join-Path $logDir "frontend.hidden.out.log"
    $stderrLog = Join-Path $logDir "frontend.hidden.err.log"
    Start-Process -FilePath $python -ArgumentList $serverScript, "--host", "0.0.0.0", "--port", "3011", "--dir", $distDir, "--api-host", "127.0.0.1", "--api-port", "8011" -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    Write-Output "V2 frontend started in background on 3011 using $python."
}
finally {
    Pop-Location
}
