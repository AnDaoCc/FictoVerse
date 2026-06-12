# Create a desktop shortcut for the GUI launcher .bat with the custom launcher icon.
# Re-run after replacing packaging/assets/launcher-icon.png and syncing.

param(
    [string]$ShortcutName = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $ShortcutName) {
    $ShortcutName = -join @(
        [char]0x5C0F, [char]0x8BF4, [char]0x4E16, [char]0x754C, [char]0x4E66
    )
}

& (Join-Path $Root "scripts\sync_launcher_icon.ps1")

$bat = Get-ChildItem -Path $Root -Filter "*.bat" -File |
    Where-Object {
        $content = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        $content -and ($content -match "novel_world\.launcher")
    } |
    Select-Object -First 1

if (-not $bat) {
    Write-Error "Missing GUI launcher batch file (expected *novel_world.launcher* in a .bat at project root)."
    exit 1
}

$icon = Join-Path $Root "packaging\assets\launcher-icon.ico"
if (-not (Test-Path $icon)) {
    Write-Error "Missing icon file: $icon"
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "$ShortcutName.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath = $bat.FullName
$shortcut.WorkingDirectory = $Root
$shortcut.IconLocation = "$icon,0"
$shortcut.Save()

Write-Host "[shortcut] OK: $lnkPath -> $($bat.Name)"
