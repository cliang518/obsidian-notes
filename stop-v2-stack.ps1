$ErrorActionPreference = "SilentlyContinue"

$ports = @(8011, 3011)

foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        if ($conn.OwningProcess) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Output "V2 services on ports 8011 and 3011 have been stopped."
