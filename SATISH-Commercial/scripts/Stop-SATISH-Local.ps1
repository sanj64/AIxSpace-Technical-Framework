[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$commercialRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$statePath = Join-Path $commercialRoot ".local-runtime\state.json"

if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    Write-Host "SATISH Local is not running; no local runtime state was found."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$failures = @()

if ($state.PSObject.Properties.Name -contains "internal_token") {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:8765/api/v1/live/shutdown" `
            -Method Post `
            -Headers @{ Authorization = "Bearer $($state.internal_token)" } `
            -UseBasicParsing `
            -TimeoutSec 5 | Out-Null
        Start-Sleep -Milliseconds 700
    }
    catch {
        Write-Warning "The live session could not be finalized through its local endpoint; process cleanup will continue."
    }
}

foreach ($entry in $state.processes) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        continue
    }

    $actualPath = $process.Path
    if (-not [string]::Equals($actualPath, [string]$entry.executable, [System.StringComparison]::OrdinalIgnoreCase)) {
        $failures += "PID $($entry.pid) ($($entry.name)) executable did not match the recorded process."
        continue
    }

    try {
        Stop-Process -Id $entry.pid -Force -ErrorAction Stop
    }
    catch {
        $failures += "Could not stop PID $($entry.pid) ($($entry.name)): $($_.Exception.Message)"
    }
}

Start-Sleep -Milliseconds 400
foreach ($entry in $state.processes) {
    if ($null -ne (Get-Process -Id $entry.pid -ErrorAction SilentlyContinue)) {
        $failures += "PID $($entry.pid) ($($entry.name)) is still running."
    }
}

if ($failures.Count -gt 0) {
    $failures | Select-Object -Unique | ForEach-Object { Write-Warning $_ }
    throw "One or more processes were not stopped because their identity could not be verified."
}

Remove-Item -LiteralPath $statePath -Force
Write-Host "SATISH Local has stopped." -ForegroundColor Green
