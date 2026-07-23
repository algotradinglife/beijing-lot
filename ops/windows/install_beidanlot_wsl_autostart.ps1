param(
    [string]$DistroName = "Ubuntu-26.04",
    [string]$LinuxUser = "drwho1985",
    [string]$TaskName = "BeijingLot-WSL-AutoStart",
    [switch]$LogonOnly
)

$ErrorActionPreference = "Stop"
$windowsIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$wslPath = Join-Path $env:WINDIR "System32\wsl.exe"
$arguments = "-d $DistroName -u $LinuxUser --exec /bin/true"

$action = New-ScheduledTaskAction -Execute $wslPath -Argument $arguments
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $windowsIdentity
$triggers = @($logonTrigger)
if ($LogonOnly) {
    $principal = New-ScheduledTaskPrincipal `
        -UserId $windowsIdentity `
        -LogonType Interactive `
        -RunLevel Limited
} else {
    $startupTrigger = New-ScheduledTaskTrigger -AtStartup
    $triggers = @($startupTrigger, $logonTrigger)
    $principal = New-ScheduledTaskPrincipal `
        -UserId $windowsIdentity `
        -LogonType S4U `
        -RunLevel Highest
}
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Principal $principal `
    -Settings $settings `
    -Description "Start WSL so the Beijing-Lot systemd services recover after Windows reboot or logon." `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
[pscustomobject]@{
    TaskName = $task.TaskName
    State = $task.State
    WindowsIdentity = $windowsIdentity
    DistroName = $DistroName
    LinuxUser = $LinuxUser
    TriggerMode = $(if ($LogonOnly) { "logon" } else { "startup_and_logon" })
    Action = "$wslPath $arguments"
} | Format-List
