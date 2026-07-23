param(
    [string]$TaskName = "Start WSL Gateway"
)

$ErrorActionPreference = "Stop"
$installer = Join-Path $PSScriptRoot "configure_hermes_wsl_gateway_unattended.ps1"
$powershell = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $installer,
    "-TaskName", ('"' + $TaskName + '"')
)

$process = Start-Process `
    -FilePath $powershell `
    -Verb RunAs `
    -ArgumentList $arguments `
    -Wait `
    -PassThru
exit $process.ExitCode

