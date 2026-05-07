$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$releaseRoot = Join-Path $root "release"
$bundleName = "YongjiaWeakCurrentV2"
$staging = Join-Path $releaseRoot $bundleName
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$zipPath = Join-Path $releaseRoot "$bundleName-$timestamp.zip"

function Copy-PathItem {
    param(
        [Parameter(Mandatory = $true)] [string] $Source,
        [Parameter(Mandatory = $true)] [string] $Destination
    )

    if (!(Test-Path $Source)) {
        return
    }

    $parent = Split-Path -Parent $Destination
    if ($parent -and !(Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    if (Test-Path $Destination) {
        Remove-Item $Destination -Recurse -Force
    }

    Copy-Item -Path $Source -Destination $Destination -Recurse -Force
}

if (Test-Path $staging) {
    Remove-Item $staging -Recurse -Force
}
New-Item -ItemType Directory -Path $staging -Force | Out-Null

Push-Location (Join-Path $root "frontend")
try {
    cmd /c npm run build
}
finally {
    Pop-Location
}

$trayExe = Join-Path $root "dist\YongjiaWeakCurrentV2Tray.exe"
if (!(Test-Path $trayExe)) {
    & (Join-Path $root "build-v2-tray-exe.ps1")
}

$licenseExe = Join-Path $root "dist\YongjiaWeakCurrentV2LicenseGenerator.exe"
if (!(Test-Path $licenseExe)) {
    & (Join-Path $root "build-v2-license-generator-exe.ps1")
}

Copy-PathItem (Join-Path $root "backend\app") (Join-Path $staging "backend\app")
Copy-PathItem (Join-Path $root "backend\run.py") (Join-Path $staging "backend\run.py")
Copy-PathItem (Join-Path $root "backend\requirements.txt") (Join-Path $staging "backend\requirements.txt")
Copy-PathItem (Join-Path $root "backend\venv") (Join-Path $staging "backend\venv")

Copy-PathItem (Join-Path $root "frontend\src") (Join-Path $staging "frontend\src")
Copy-PathItem (Join-Path $root "frontend\dist") (Join-Path $staging "frontend\dist")
Copy-PathItem (Join-Path $root "frontend\package.json") (Join-Path $staging "frontend\package.json")
Copy-PathItem (Join-Path $root "frontend\package-lock.json") (Join-Path $staging "frontend\package-lock.json")
Copy-PathItem (Join-Path $root "frontend\vite.config.js") (Join-Path $staging "frontend\vite.config.js")
Copy-PathItem (Join-Path $root "frontend\index.html") (Join-Path $staging "frontend\index.html")

Copy-PathItem (Join-Path $root "tools") (Join-Path $staging "tools")
Copy-PathItem (Join-Path $root "docs") (Join-Path $staging "docs")
Copy-PathItem (Join-Path $root "runtime\platform_v2.db") (Join-Path $staging "runtime\platform_v2.db")
Copy-PathItem (Join-Path $root "runtime\alert_guard_settings.json") (Join-Path $staging "runtime\alert_guard_settings.json")
Copy-PathItem (Join-Path $root "runtime\floor_plans") (Join-Path $staging "runtime\floor_plans")
Copy-PathItem (Join-Path $root "runtime\license") (Join-Path $staging "runtime\license")

$scripts = @(
    "backup-v2-state.ps1",
    "build-v2-license-generator-exe.ps1",
    "build-v2-tray-exe.ps1",
    "install-v2-tray-startup.ps1",
    "remove-v2-tray-startup.ps1",
    "start-v2-backend.ps1",
    "start-v2-frontend-dev.ps1",
    "start-v2-frontend.ps1",
    "start-v2-stack.ps1",
    "stop-v2-stack.ps1",
    "publish-v2-release.ps1"
)

foreach ($script in $scripts) {
    Copy-PathItem (Join-Path $root $script) (Join-Path $staging $script)
}

Copy-PathItem (Join-Path $root "dist") (Join-Path $staging "dist")

$manifest = @(
    "bundle=$bundleName"
    "timestamp=$timestamp"
    "root=$root"
    "notes=Portable release bundle with backend source, backend venv, built frontend, tray exe, and license generator."
)
Set-Content -Path (Join-Path $staging "release-manifest.txt") -Value $manifest -Encoding UTF8

$readme = @"
# Yongjia Weak Current Ops Platform V2 Release

## Start

```powershell
.\start-v2-stack.ps1
```

## Tray

```powershell
.\dist\YongjiaWeakCurrentV2Tray.exe
```

## License

```powershell
.\dist\YongjiaWeakCurrentV2LicenseGenerator.exe
```

## Notes

- backend listens on `127.0.0.1:8011`
- frontend listens on `127.0.0.1:3011`
- the bundle keeps the current runtime database and alert-guard settings
- if you want a clean deploy, stop the stack first and then copy this folder to the new server
"@
Set-Content -Path (Join-Path $staging "RELEASE.md") -Value $readme -Encoding UTF8

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force

Write-Output "Release bundle created:"
Write-Output $zipPath
