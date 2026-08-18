# Reset Onehunga layout to the bundled default template (PowerShell)
$Root = Split-Path -Parent $PSScriptRoot
$Template = Join-Path $Root "data\layouts\_templates\onehunga.json"
$Target = Join-Path $Root "data\layouts\onehunga.json"
$Last = Join-Path $Root "data\layouts\_last.json"

if (-not (Test-Path $Template)) {
    Write-Host "Template missing. Run: python tools\generate_onehunga_layout.py" -ForegroundColor Red
    exit 1
}

Copy-Item -Force $Template $Target
if (Test-Path $Last) { Remove-Item -Force $Last }
Write-Host "OK: restored onehunga.json (43 x 76.3 m). Start: python layout.py" -ForegroundColor Green
