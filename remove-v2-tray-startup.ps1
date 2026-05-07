$ErrorActionPreference = "Stop"

$startupDir = [Environment]::GetFolderPath("Startup")
$startupVbs = Join-Path $startupDir "YongjiaWeakCurrentV2Tray.vbs"

if (Test-Path $startupVbs) {
    Remove-Item -LiteralPath $startupVbs -Force
    Write-Output "V2 tray startup removed: $startupVbs"
}
else {
    Write-Output "V2 tray startup not present."
}
