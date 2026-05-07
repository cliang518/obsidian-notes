[CmdletBinding()]
param(
    [switch]$Execute
)

$ErrorActionPreference = "Stop"

$root = "E:\cctv-maintenance"
$archiveDir = Join-Path $root "archive_v1"

if (-not (Test-Path $root)) {
    throw "Root path not found: $root"
}

$protectedDirectories = @(
    "platform_v2",
    ".vscode",
    ".ts",
    "data",
    "map",
    "map_test_src",
    "cloudflared_tray",
    "openclaw_tray"
)

$protectedFileNames = @(
    ".env",
    ".env.example",
    "docker-compose.yml",
    "README.md",
    "SPEC.md",
    "cctv_maintenance.db"
)

$protectedDirectoryPrefixes = @(
    "map_test_out",
    "update-feed"
)

$protectedFilePatterns = @(
    "*.xlsx"
)

$legacyDirectories = @(
    "frontend",
    "backend",
    "dist",
    "build",
    "logs"
)

$legacyExactFiles = @(
    "index.html",
    "run_backend.ps1",
    "run_backend.bat",
    "start_backend.ps1",
    "start_backend.bat",
    "start_frontend.bat",
    "start_server.bat",
    "start_server.py",
    "start_uvicorn.bat",
    "start-local.ps1",
    "start-local.ps1",
    "start-monitor.ps1",
    "start-monitor.vbs",
    "start-stack.ps1",
    "stop-local.ps1",
    "restart-backend.ps1",
    "setup-local.ps1",
    "quick-test.ps1",
    "diagnose.ps1",
    "import_test.ps1"
)

$legacyRegexPatterns = @(
    '^test_.*\.py$',
    '^check_.*\.py$',
    '^check_.*\.ps1$',
    '^test_.*\.ps1$',
    '^test-.*\.ps1$'
)

function Test-IsProtectedName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($protectedDirectories -contains $Name) { return $true }
    if ($protectedFileNames -contains $Name) { return $true }

    foreach ($prefix in $protectedDirectoryPrefixes) {
        if ($Name.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    foreach ($pattern in $protectedFilePatterns) {
        if ($Name -like $pattern) {
            return $true
        }
    }

    return $false
}

function Add-Candidate {
    param(
        $Bucket,
        [Parameter(Mandatory = $true)]
        [System.IO.FileSystemInfo]$Item
    )

    $exists = $false
    foreach ($existing in $Bucket) {
        if ($existing.FullName -eq $Item.FullName) {
            $exists = $true
            break
        }
    }

    if (-not $exists) {
        [void]$Bucket.Add($Item)
    }
}

$candidates = New-Object System.Collections.ArrayList

$topLevelItems = Get-ChildItem -LiteralPath $root -Force

foreach ($item in $topLevelItems) {
    if ($item.Name -eq "archive_v1") {
        continue
    }

    if (Test-IsProtectedName -Name $item.Name) {
        continue
    }

    if ($item.PSIsContainer -and ($legacyDirectories -contains $item.Name)) {
        Add-Candidate -Bucket $candidates -Item $item
        continue
    }

    if (-not $item.PSIsContainer) {
        if ($legacyExactFiles -contains $item.Name) {
            Add-Candidate -Bucket $candidates -Item $item
            continue
        }

        if ($item.Extension -in @(".bat", ".vbs", ".html")) {
            Add-Candidate -Bucket $candidates -Item $item
            continue
        }

        foreach ($regex in $legacyRegexPatterns) {
            if ($item.Name -match $regex) {
                Add-Candidate -Bucket $candidates -Item $item
                break
            }
        }
    }
}

$sortedCandidates = $candidates | Sort-Object {
    if ($_.PSIsContainer) { 0 } else { 1 }
}, Name

Write-Host ""
Write-Host "=== V1 归档预演清单 ===" -ForegroundColor Cyan
Write-Host "根目录: $root"
Write-Host "归档目录: $archiveDir"
Write-Host "模式: $(if ($Execute) { '执行模式' } else { 'Dry Run / 仅预演' })"
Write-Host ""

if (-not $sortedCandidates.Count) {
    Write-Host "没有发现需要归档的旧目录或旧文件。" -ForegroundColor Yellow
    exit 0
}

foreach ($item in $sortedCandidates) {
    $kind = if ($item.PSIsContainer) { "[DIR ]" } else { "[FILE]" }
    Write-Host "$kind $($item.FullName)"
}

Write-Host ""
Write-Host ("合计: {0} 项（目录 {1} / 文件 {2}）" -f `
    $sortedCandidates.Count, `
    ($sortedCandidates | Where-Object { $_.PSIsContainer }).Count, `
    ($sortedCandidates | Where-Object { -not $_.PSIsContainer }).Count)

if (-not $Execute) {
    Write-Host ""
    Write-Host "当前是 Dry Run，不会执行任何移动。" -ForegroundColor Green
    Write-Host "确认无误后，请运行：" -ForegroundColor Green
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Execute"
    exit 0
}

if (-not (Test-Path $archiveDir)) {
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
}

Write-Host ""
Write-Host "=== 开始归档旧系统文件 ===" -ForegroundColor Yellow

foreach ($item in $sortedCandidates) {
    $destination = Join-Path $archiveDir $item.Name
    if (Test-Path $destination) {
        throw "目标已存在，停止执行以避免覆盖: $destination"
    }

    Move-Item -LiteralPath $item.FullName -Destination $destination
    Write-Host "已移动 -> $destination"
}

Write-Host ""
Write-Host "归档完成。" -ForegroundColor Green
Write-Host "归档目录: $archiveDir" -ForegroundColor Green
