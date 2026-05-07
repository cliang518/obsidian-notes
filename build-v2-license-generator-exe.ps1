$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tool = Join-Path $root "tools\\v2_license_generator.py"
$python = "E:\\cctv-maintenance\\backend\\venv\\Scripts\\python.exe"

Push-Location $root
try {
    & $python -m PyInstaller `
        --console `
        --onefile `
        --clean `
        --name YongjiaWeakCurrentV2LicenseGenerator `
        $tool
}
finally {
    Pop-Location
}
