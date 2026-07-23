param(
    [string]$DistroName = "Ubuntu-26.04",
    [string]$LinuxUser = "drwho1985"
)

$ErrorActionPreference = "Stop"
$installer = Join-Path $PSScriptRoot "install_beidanlot_wsl_autostart.ps1"
$powershell = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $installer,
    "-DistroName", $DistroName,
    "-LinuxUser", $LinuxUser
)

$process = Start-Process `
    -FilePath $powershell `
    -Verb RunAs `
    -ArgumentList $arguments `
    -Wait `
    -PassThru
exit $process.ExitCode

