# Sync launcher icon: PNG source -> multi-size ICO for exe, GUI, and shortcuts.
# Replace packaging/assets/launcher-icon.png, then run this script.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$png = Join-Path $Root "packaging\assets\launcher-icon.png"
if (-not (Test-Path $png)) {
    Write-Error "Missing icon source: $png"
    exit 1
}

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[icon] Creating venv for Pillow..."
    python -m venv .venv
}

Write-Host "[icon] Generating launcher-icon.ico from PNG..."
& $venvPy -m pip install -q Pillow
& $venvPy (Join-Path $Root "scripts\png_to_ico.py")
if ($LASTEXITCODE -ne 0) {
    Write-Error "Icon sync failed."
    exit 1
}

Write-Host "[icon] OK: packaging\assets\launcher-icon.ico"
