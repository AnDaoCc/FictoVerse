# Backup dev launcher, build PyInstaller exe, and publish to release/.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[release] Step 1/4: backup dev launcher..."
& (Join-Path $Root "scripts\backup_launcher_dev.ps1")

Write-Host "[release] Step 2/4: sync icon..."
& (Join-Path $Root "scripts\sync_launcher_icon.ps1")

Write-Host "[release] Step 3/4: build exe..."
& (Join-Path $Root "scripts\build_launcher.ps1")

$builtExe = Get-ChildItem -Path (Join-Path $Root "dist") -Recurse -Filter "*.exe" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.DirectoryName -notmatch '\\_internal(\\|$)' } |
    Select-Object -First 1
if (-not $builtExe) {
    Write-Error "Build output missing: no exe under dist\"
    exit 1
}
$distDir = $builtExe.Directory.FullName
$releaseParent = Join-Path $Root "release"
$releaseDir = Join-Path $releaseParent $builtExe.Directory.Name

Write-Host "[release] Step 4/4: publish to release\..."
if (Test-Path $releaseParent) {
    Get-ChildItem -Path $releaseParent -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
} else {
    New-Item -ItemType Directory -Force -Path $releaseParent | Out-Null
}
Copy-Item -Path $distDir -Destination $releaseDir -Recurse -Force

Write-Host ""
Write-Host "[release] Done."
Write-Host "  Dev:   GUI启动器.bat"
Write-Host "  Prod:  release\小说世界书启动器\小说世界书启动器.exe"
Write-Host "  Backup: packaging\backup\launcher-dev-*"
