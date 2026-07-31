#Requires -Version 5.1
<#
.SYNOPSIS
  start.ps1 で起動した在室管理と cloudflared を停止する。
#>
$ErrorActionPreference = "Continue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DataDir = Join-Path $RepoRoot "data"
$RuntimeDir = Join-Path $DataDir "runtime"
$TunnelUrlFile = Join-Path $DataDir "tunnel_url.txt"
$AppPidFile = Join-Path $RuntimeDir "app.pid"
$TunnelPidFile = Join-Path $RuntimeDir "cloudflared.pid"

function Write-Info([string]$Message) {
    Write-Host "[stop] $Message"
}

function Stop-PidFromFile([string]$PidFile, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Info "$Label の PID ファイルはありません"
        return
    }
    $raw = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $procId = 0
    if ($raw -and [int]::TryParse($raw.Trim(), [ref]$procId)) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Info "$Label (PID $procId) を停止します"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        } else {
            Write-Info "$Label (PID $procId) は既に終了しています"
        }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

Stop-PidFromFile -PidFile $TunnelPidFile -Label "cloudflared"
Stop-PidFromFile -PidFile $AppPidFile -Label "app"
Remove-Item -LiteralPath $TunnelUrlFile -Force -ErrorAction SilentlyContinue
Write-Info "完了"
