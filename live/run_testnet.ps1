# live/run_testnet.ps1 — Binance demo botunu calistirir ve loglar.
# Gorev Zamanlayici bunu 4 saatte bir cagirir. Elle de calistirabilirsin:
#   powershell -ExecutionPolicy Bypass -File live\run_testnet.ps1
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$log = Join-Path $root "live\testnet_log.txt"
$ts  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Python ciktisini UTF-8 al, tek seferde UTF-8 olarak yaz (kodlama bozulmasin)
$env:PYTHONIOENCODING = "utf-8"
$out = & python -u "live\testnet_bot.py" 2>&1 | Out-String

$block = "`n===== $ts =====`n" + $out
[System.IO.File]::AppendAllText($log, $block, [System.Text.UTF8Encoding]::new($false))

Write-Output $out
