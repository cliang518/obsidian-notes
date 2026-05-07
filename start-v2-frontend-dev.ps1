$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $root "frontend"
$nodeModules = Join-Path $frontendDir "node_modules"
$legacyNodeModules = "E:\\cctv-maintenance\\frontend\\node_modules"

if (!(Test-Path $nodeModules) -and (Test-Path $legacyNodeModules)) {
    New-Item -ItemType Junction -Path $nodeModules -Target $legacyNodeModules | Out-Null
}

Push-Location $frontendDir
try {
    cmd /c npm run dev -- --host 127.0.0.1 --port 3011 --strictPort
}
finally {
    Pop-Location
}
