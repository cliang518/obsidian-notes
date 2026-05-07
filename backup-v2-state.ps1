$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $root "..\\backups"
$targetDir = Join-Path $backupRoot "v2-state-$timestamp"

New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

$items = @(
    @{ Source = (Join-Path $root "docs"); Destination = "docs" },
    @{ Source = (Join-Path $root "frontend\\src"); Destination = "frontend-src" },
    @{ Source = (Join-Path $root "backend\\app"); Destination = "backend-app" },
    @{ Source = (Join-Path $root "tools"); Destination = "tools" },
    @{ Source = (Join-Path $root "runtime\\platform_v2.db"); Destination = "runtime-platform_v2.db" },
    @{ Source = (Join-Path $root "runtime\\logs"); Destination = "runtime-logs" }
)

foreach ($item in $items) {
    if (Test-Path $item.Source) {
        $destinationPath = Join-Path $targetDir $item.Destination
        Copy-Item -Path $item.Source -Destination $destinationPath -Recurse -Force
    }
}

$manifest = @(
    "timestamp=$timestamp"
    "root=$root"
    "database=runtime\\platform_v2.db"
    "notes=V2 source, docs, logs, and runtime database snapshot"
)

$manifest | Set-Content -Path (Join-Path $targetDir "backup-manifest.txt") -Encoding UTF8

$zipPath = Join-Path $backupRoot "v2-state-$timestamp.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path (Join-Path $targetDir "*") -DestinationPath $zipPath -Force

Write-Output "Backup created:"
Write-Output $zipPath
