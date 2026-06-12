# Snapshot the dev launcher sources before packaging a release build.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = Join-Path $Root "packaging\backup\launcher-dev-$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

function Copy-Tree($src, $rel) {
    $from = Join-Path $Root $src
    if (-not (Test-Path $from)) {
        Write-Warning "Skip missing: $src"
        return
    }
    $to = Join-Path $dest $rel
    if (Test-Path $from -PathType Container) {
        Copy-Item -Path $from -Destination $to -Recurse -Force
    } else {
        $parent = Split-Path $to -Parent
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        Copy-Item -Path $from -Destination $to -Force
    }
}

Copy-Tree "src\novel_world\launcher" "src\novel_world\launcher"
$guiBat = Get-ChildItem -Path $Root -Filter "*.bat" -File |
    Where-Object {
        $content = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        $content -and ($content -match "novel_world\.launcher")
    } |
    Select-Object -First 1
if ($guiBat) {
    Copy-Tree $guiBat.Name $guiBat.Name
} else {
    Write-Warning "Skip missing: GUI launcher .bat"
}
Copy-Tree "packaging\launcher.spec" "packaging\launcher.spec"
Copy-Tree "packaging\assets" "packaging\assets"
Copy-Tree "scripts\build_launcher.ps1" "scripts\build_launcher.ps1"
Copy-Tree "scripts\sync_launcher_icon.ps1" "scripts\sync_launcher_icon.ps1"
Copy-Tree "scripts\create_launcher_shortcut.ps1" "scripts\create_launcher_shortcut.ps1"
Copy-Tree "scripts\build_release.ps1" "scripts\build_release.ps1"

$manifest = @"
Launcher dev backup
Created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Purpose: Snapshot before packaging release/小说世界书启动器

Restore: copy files from this folder back to project root (merge carefully).
Daily dev: use GUI启动器.bat at project root instead of this backup.
"@
Set-Content -Path (Join-Path $dest "MANIFEST.txt") -Value $manifest -Encoding UTF8

Write-Host "[backup] OK: $dest"
