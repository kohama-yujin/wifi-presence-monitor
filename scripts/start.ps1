#Requires -Version 5.1
<#
.SYNOPSIS
  在室管理 (Flask) と Cloudflare Quick Tunnel を起動し、公開 URL を data/tunnel_url.txt に保存する。

.NOTES
  タスクスケジューラからは次のように実行する:
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "...\scripts\start.ps1"

  cloudflared の場所（優先順）:
    1. 環境変数 CLOUDFLARED_EXE
    2. リポジトリの tools\cloudflared-windows-amd64.exe
    3. %USERPROFILE%\Downloads\cloudflared-windows-amd64.exe
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DataDir = Join-Path $RepoRoot "data"
$RuntimeDir = Join-Path $DataDir "runtime"
$TunnelUrlFile = Join-Path $DataDir "tunnel_url.txt"
$CloudflaredOutLog = Join-Path $DataDir "cloudflared.out.log"
$CloudflaredErrLog = Join-Path $DataDir "cloudflared.err.log"
$AppPidFile = Join-Path $RuntimeDir "app.pid"
$TunnelPidFile = Join-Path $RuntimeDir "cloudflared.pid"
$AppOutLog = Join-Path $DataDir "app.out.log"
$AppErrLog = Join-Path $DataDir "app.err.log"
$Port = 5000
$OriginUrl = "http://127.0.0.1:$Port"

New-Item -ItemType Directory -Force -Path $DataDir, $RuntimeDir | Out-Null

function Write-Info([string]$Message) {
    Write-Host "[start] $Message"
}

function Resolve-Cloudflared {
    if ($env:CLOUDFLARED_EXE -and (Test-Path -LiteralPath $env:CLOUDFLARED_EXE)) {
        return (Resolve-Path -LiteralPath $env:CLOUDFLARED_EXE).Path
    }
    $candidates = @(
        (Join-Path $RepoRoot "tools\cloudflared-windows-amd64.exe"),
        (Join-Path $env:USERPROFILE "Downloads\cloudflared-windows-amd64.exe")
    )
    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    throw "cloudflared が見つかりません。tools\ に置くか CLOUDFLARED_EXE を設定してください。"
}

function Resolve-Python {
    $venvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return (Resolve-Path -LiteralPath $venvPython).Path
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    throw "Python が見つかりません。先に venv を作成してください。"
}

function Test-PortOpen([int]$PortNumber) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect("127.0.0.1", $PortNumber, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne(400)
        if ($ok -and $client.Connected) {
            $client.EndConnect($async) | Out-Null
            $client.Close()
            return $true
        }
        $client.Close()
    } catch {
        # ignore
    }
    return $false
}

function Stop-PidFromFile([string]$PidFile, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PidFile)) {
        return
    }
    $raw = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $raw) {
        return
    }
    $procId = 0
    if (-not [int]::TryParse($raw.Trim(), [ref]$procId)) {
        return
    }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Info "既存の $Label (PID $procId) を停止します"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Find-TunnelUrl {
    $pattern = 'https://[a-zA-Z0-9-]+\.trycloudflare\.com'
    foreach ($logPath in @($CloudflaredOutLog, $CloudflaredErrLog)) {
        if (-not (Test-Path -LiteralPath $logPath)) {
            continue
        }
        $match = Select-String -Path $logPath -Pattern $pattern -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($match -and $match.Matches.Count -gt 0) {
            return $match.Matches[0].Value
        }
    }
    return $null
}

# 前回の残骸を掃除
Stop-PidFromFile -PidFile $TunnelPidFile -Label "cloudflared"
Stop-PidFromFile -PidFile $AppPidFile -Label "app"
Remove-Item -LiteralPath $TunnelUrlFile -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $CloudflaredOutLog, $CloudflaredErrLog -Force -ErrorAction SilentlyContinue

$Python = Resolve-Python
$Cloudflared = Resolve-Cloudflared
Write-Info "repo: $RepoRoot"
Write-Info "python: $Python"
Write-Info "cloudflared: $Cloudflared"

if (Test-PortOpen -PortNumber $Port) {
    Write-Info "ポート $Port は既に使用中です。既存プロセスを利用します。"
} else {
    Write-Info "在室管理を起動します"
    $app = Start-Process -FilePath $Python `
        -ArgumentList "main.py" `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $AppOutLog `
        -RedirectStandardError $AppErrLog `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -LiteralPath $AppPidFile -Value $app.Id -Encoding ascii

    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if (Test-PortOpen -PortNumber $Port) {
            $ready = $true
            break
        }
        if ($app.HasExited) {
            throw "在室管理の起動に失敗しました。$AppErrLog / $AppOutLog を確認してください。"
        }
    }
    if (-not $ready) {
        throw "在室管理がポート $Port で応答しません。"
    }
    Write-Info "在室管理が起動しました (PID $($app.Id))"
}

Write-Info "cloudflared Quick Tunnel を起動します"
$cfArgs = @("tunnel", "--url", $OriginUrl)
$cf = Start-Process -FilePath $Cloudflared `
    -ArgumentList $cfArgs `
    -WorkingDirectory $RepoRoot `
    -RedirectStandardOutput $CloudflaredOutLog `
    -RedirectStandardError $CloudflaredErrLog `
    -WindowStyle Hidden `
    -PassThru
Set-Content -LiteralPath $TunnelPidFile -Value $cf.Id -Encoding ascii

$url = $null
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 1
    if ($cf.HasExited) {
        throw "cloudflared が終了しました。$CloudflaredErrLog / $CloudflaredOutLog を確認してください。"
    }
    $url = Find-TunnelUrl
    if ($url) {
        break
    }
}

if (-not $url) {
    throw "Quick Tunnel URL を取得できませんでした。ログを確認してください。"
}

# PowerShell 5.1 の utf8 は BOM 付きなので、BOM なし UTF-8 で書く
[System.IO.File]::WriteAllText($TunnelUrlFile, $url + [Environment]::NewLine)
Write-Info "公開 URL: $url"
Write-Info "完了（このウィンドウは閉じて構いません。プロセスは常駐します）"
