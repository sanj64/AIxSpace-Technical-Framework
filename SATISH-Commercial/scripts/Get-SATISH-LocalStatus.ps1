[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$commercialRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$statePath = Join-Path $commercialRoot ".local-runtime\state.json"

if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Write-Host "SATISH Local is stopped."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$status = foreach ($entry in $state.processes) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    [pscustomobject]@{
        Component = $entry.name
        Running = $null -ne $process
        ProcessId = $entry.pid
        Url = $entry.url
        LoopbackOnly = $state.binding -eq "127.0.0.1-only"
    }
}

$status | Format-Table -AutoSize
