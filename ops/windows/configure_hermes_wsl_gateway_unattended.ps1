param(
    [string]$TaskName = "Start WSL Gateway"
)

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName
if (-not $task) {
    throw "Scheduled task not found: $TaskName"
}

$hasBootTrigger = @($task.Triggers | Where-Object {
    $_.CimClass.CimClassName -eq "MSFT_TaskBootTrigger" -and $_.Enabled
}).Count -gt 0
$hasWslAction = @($task.Actions | Where-Object {
    $_.Execute -match "(?i)wsl\.exe$"
}).Count -gt 0
if (-not $hasBootTrigger -or -not $hasWslAction) {
    throw "Refusing to modify task without an enabled BootTrigger and wsl.exe action."
}

$principal = New-ScheduledTaskPrincipal `
    -UserId $task.Principal.UserId `
    -LogonType S4U `
    -RunLevel Highest
$settings = $task.Settings
$settings.StartWhenAvailable = $true

Set-ScheduledTask `
    -TaskName $task.TaskName `
    -TaskPath $task.TaskPath `
    -Principal $principal `
    -Settings $settings | Out-Null

$updated = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    TaskName = $updated.TaskName
    UserId = $updated.Principal.UserId
    LogonType = [string]$updated.Principal.LogonType
    RunLevel = [string]$updated.Principal.RunLevel
    StartWhenAvailable = $updated.Settings.StartWhenAvailable
    Trigger = $updated.Triggers[0].CimClass.CimClassName
    Execute = $updated.Actions[0].Execute
    Arguments = $updated.Actions[0].Arguments
    LastRunTime = $info.LastRunTime
    LastTaskResult = $info.LastTaskResult
} | Format-List

