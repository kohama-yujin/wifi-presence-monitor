#Requires -Version 5.1
<#
.SYNOPSIS
  ログオン時に start.ps1 を実行するタスクスケジューラ登録を行う。

.EXAMPLE
  .\scripts\register-task.ps1
  .\scripts\register-task.ps1 -Unregister
#>
param(
    [switch]$Unregister,
    [string]$TaskName = "WiFi Presence Monitor",
    [int]$DelaySeconds = 60
)

$ErrorActionPreference = "Stop"

$StartScript = Join-Path $PSScriptRoot "start.ps1"
if (-not (Test-Path -LiteralPath $StartScript)) {
    throw "start.ps1 が見つかりません: $StartScript"
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Unregister) {
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[register-task] タスク '$TaskName' を削除しました"
    } else {
        Write-Host "[register-task] タスク '$TaskName' は存在しません"
    }
    return
}

$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# ネットワーク待ち（PT60S など）
if ($DelaySeconds -gt 0) {
    $trigger.Delay = "PT${DelaySeconds}S"
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

# ログオン中ユーザーとして対話実行（音・ネットワーク用）
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "[register-task] タスク '$TaskName' を登録しました"
Write-Host "[register-task] 操作: powershell.exe $arg"
Write-Host "[register-task] トリガー: ログオン時 + ${DelaySeconds}s 遅延"
Write-Host "[register-task] 手動実行: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "[register-task] 失敗時ログ: data\start.log / data\start.err.log"
