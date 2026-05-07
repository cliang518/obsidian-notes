$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$trayExe = Join-Path $root "dist\\YongjiaWeakCurrentV2Tray.exe"
$startupDir = [Environment]::GetFolderPath("Startup")
$startupVbs = Join-Path $startupDir "YongjiaWeakCurrentV2Tray.vbs"

if (!(Test-Path $trayExe)) {
    throw "Tray executable not found: $trayExe"
}

if (!(Test-Path $startupDir)) {
    New-Item -ItemType Directory -Path $startupDir | Out-Null
}

$escapedTray = $trayExe.Replace('"', '""')
$content = @(
    'Set shell = CreateObject("WScript.Shell")'
    "shell.Run Chr(34) & ""$escapedTray"" & Chr(34), 0, False"
    ""
) -join [Environment]::NewLine

Set-Content -Path $startupVbs -Value $content -Encoding UTF8
Write-Output "V2 tray startup installed: $startupVbs"
