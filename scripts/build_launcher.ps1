# Build Windows GUI launcher (onedir) with PyInstaller.
# Output: dist/小说世界书启动器/小说世界书启动器.exe
# Copy the exe folder to project root (beside pyproject.toml).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[build] Creating venv..."
    python -m venv .venv
}

Write-Host "[build] Installing launcher + pyinstaller..."
& $venvPy -m pip install -q -e ".[launcher]" pyinstaller

Write-Host "[build] Syncing launcher icon..."
& (Join-Path $Root "scripts\sync_launcher_icon.ps1")

Write-Host "[build] Running PyInstaller..."
& $venvPy -m PyInstaller --noconfirm --clean packaging/launcher.spec

$exe = Get-ChildItem -Path (Join-Path $Root "dist") -Recurse -Filter "*.exe" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.DirectoryName -notmatch '\\_internal(\\|$)' } |
    Select-Object -First 1
if ($exe) {
    Write-Host "[build] OK: $($exe.FullName)"
    Write-Host "Copy the dist launcher folder to your project root, then double-click the exe."
} else {
    Write-Error "Build failed: launcher exe not found under dist\"
    exit 1
}
