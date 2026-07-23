[CmdletBinding()]
param(
    [string]$RunDirectory = "",
    [string]$AuditPrivateKey = "",
    [string]$ConfigPath = "",
    [string]$ConfigPublicKey = "",
    [string]$OperatorId = "local.operator",
    [string]$TelemetryCsv = "",
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$commercialRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = Split-Path $commercialRoot -Parent
$siteRoot = Join-Path $workspaceRoot "SATISH-Public-Site"
$runtimeRoot = Join-Path $commercialRoot ".local-runtime"
$statePath = Join-Path $runtimeRoot "state.json"

function Test-LocalPort {
    param([int]$Port)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        if (-not $task.Wait(300)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Start-DirectProcess {
    param(
        [string]$FileName,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [hashtable]$Environment
    )

    $savedEnvironment = @{}
    try {
        foreach ($name in $Environment.Keys) {
            $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
            [Environment]::SetEnvironmentVariable(
                $name,
                [string]$Environment[$name],
                "Process"
            )
        }

        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $FileName
        $startInfo.Arguments = $Arguments
        $startInfo.WorkingDirectory = $WorkingDirectory
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        if (-not $process.Start()) {
            throw "Failed to start $FileName"
        }
        return $process
    }
    finally {
        foreach ($name in $savedEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable(
                $name,
                $savedEnvironment[$name],
                "Process"
            )
        }
    }
}

function Wait-LocalEndpoint {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 400
        }
    }
    return $false
}

function Get-LocalListenerProcessId {
    param([int]$Port)

    $pattern = "^\s*TCP\s+127\.0\.0\.1:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    foreach ($line in (& (Join-Path $env:SystemRoot "System32\netstat.exe") -ano -p TCP)) {
        if ($line -match $pattern) {
            return [int]$Matches[1]
        }
    }
    throw "Could not identify the process listening on local port $Port."
}

if (Test-Path -LiteralPath $statePath) {
    $priorState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $liveProcesses = @($priorState.processes | Where-Object {
        $null -ne (Get-Process -Id $_.pid -ErrorAction SilentlyContinue)
    })
    if ($liveProcesses.Count -gt 0) {
        throw "SATISH Local is already running. Use scripts\Stop-SATISH-Local.ps1 first."
    }
}

foreach ($port in @(3000, 3001, 8501, 8765)) {
    if (Test-LocalPort -Port $port) {
        throw "Local port $port is already in use. SATISH did not stop or replace that process."
    }
}

if (-not (Test-Path -LiteralPath $siteRoot -PathType Container)) {
    throw "The sibling SATISH-Public-Site directory was not found at $siteRoot"
}

$python = Join-Path $commercialRoot ".venv\Scripts\python.exe"
$streamlitApp = Join-Path $commercialRoot "src\satish_commercial\app.py"
$nodeCommand = Get-Command node.exe -ErrorAction Stop
$node = $nodeCommand.Source
$vinextCli = Join-Path $siteRoot "node_modules\vinext\dist\cli.js"
$siteBuild = Join-Path $siteRoot "dist\server\index.js"
$gatewayScript = Join-Path $siteRoot "scripts\local-gateway.mjs"

foreach ($requiredPath in @($python, $streamlitApp, $vinextCli, $siteBuild, $gatewayScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required local runtime file is missing: $requiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($RunDirectory)) {
    $candidate = Get-ChildItem -LiteralPath (Join-Path $commercialRoot "outputs") -Directory -Filter "demo-*" |
        Sort-Object LastWriteTime -Descending |
        Where-Object {
            Test-Path -LiteralPath (Join-Path $_.FullName "evidence\run-manifest.json")
        } |
        Select-Object -First 1
    if ($null -eq $candidate) {
        throw "No completed local demo evidence was found. Supply -RunDirectory explicitly."
    }
    $RunDirectory = Join-Path $candidate.FullName "evidence"
    if ([string]::IsNullOrWhiteSpace($AuditPrivateKey)) {
        $AuditPrivateKey = Join-Path $candidate.FullName "keys\demo-private.pem"
    }
    if ([string]::IsNullOrWhiteSpace($ConfigPublicKey)) {
        $ConfigPublicKey = Join-Path $candidate.FullName "keys\demo-public.pem"
    }
    if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
        $ConfigPath = Join-Path $candidate.FullName "signed-evaluation-config.json"
    }
}

$RunDirectory = (Resolve-Path -LiteralPath $RunDirectory).Path
if ([string]::IsNullOrWhiteSpace($AuditPrivateKey)) {
    throw "Supply -AuditPrivateKey when using a custom run directory."
}
$AuditPrivateKey = (Resolve-Path -LiteralPath $AuditPrivateKey).Path
if ([string]::IsNullOrWhiteSpace($ConfigPublicKey) -or [string]::IsNullOrWhiteSpace($ConfigPath)) {
    throw "Supply -ConfigPath and -ConfigPublicKey when using a custom run directory."
}
$ConfigPublicKey = (Resolve-Path -LiteralPath $ConfigPublicKey).Path
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path

$requiredEvidence = @(
    "risk-packets.jsonl",
    "explanation-packets.jsonl",
    "recommendations.jsonl",
    "run-manifest.json",
    "audit.jsonl"
)
foreach ($name in $requiredEvidence) {
    if (-not (Test-Path -LiteralPath (Join-Path $RunDirectory $name) -PathType Leaf)) {
        throw "The selected run is incomplete: missing $name"
    }
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$liveOutputRoot = Join-Path $commercialRoot "outputs\live"
New-Item -ItemType Directory -Path $liveOutputRoot -Force | Out-Null
$internalTokenBytes = New-Object byte[] 32
$tokenGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $tokenGenerator.GetBytes($internalTokenBytes)
}
finally {
    $tokenGenerator.Dispose()
}
$internalToken = ([BitConverter]::ToString($internalTokenBytes) -replace "-", "").ToLowerInvariant()
$started = @()
try {
    $operatorArguments = @(
        "-m streamlit run",
        ('"{0}"' -f $streamlitApp),
        "--server.headless true",
        "--server.address 127.0.0.1",
        "--server.port 8501",
        "--server.fileWatcherType none",
        "--browser.gatherUsageStats false"
    ) -join " "
    $operatorEnvironment = @{
        PYTHONPATH = (Join-Path $commercialRoot "src")
        SATISH_RUN_DIRECTORY = $RunDirectory
        SATISH_OPERATOR_ID = $OperatorId
        SATISH_ROLE = "operator"
        SATISH_REQUIRE_OIDC = "0"
        SATISH_AUDIT_PRIVATE_KEY = $AuditPrivateKey
        SATISH_SECOND_REVIEW = "0"
    }
    $operator = Start-DirectProcess -FileName $python -Arguments $operatorArguments `
        -WorkingDirectory $commercialRoot -Environment $operatorEnvironment
    $started += $operator

    # Optional recorded-telemetry replay: use the explicit path, else the bundled ESA-ADB
    # demo CSV if present. When set, the live monitor streams that recorded telemetry (clearly
    # relabelled) instead of synthesising; otherwise it keeps the synthetic stream.
    if ([string]::IsNullOrWhiteSpace($TelemetryCsv)) {
        $defaultEsa = Join-Path $commercialRoot "datasets\esa-mission1\esa-mission1.csv"
        if (Test-Path -LiteralPath $defaultEsa -PathType Leaf) { $TelemetryCsv = $defaultEsa }
    }
    $liveArgumentList = [System.Collections.Generic.List[string]]::new()
    $liveArgumentList.AddRange([string[]]@(
        "-m satish_commercial.live",
        "--evidence-directory", ('"{0}"' -f $RunDirectory),
        "--config", ('"{0}"' -f $ConfigPath),
        "--public-key", ('"{0}"' -f $ConfigPublicKey),
        "--private-key", ('"{0}"' -f $AuditPrivateKey),
        "--output-root", ('"{0}"' -f $liveOutputRoot),
        "--token", $internalToken,
        "--host", "127.0.0.1",
        "--port", "8765"
    ))
    if (-not [string]::IsNullOrWhiteSpace($TelemetryCsv)) {
        $TelemetryCsv = (Resolve-Path -LiteralPath $TelemetryCsv).Path
        $liveArgumentList.AddRange([string[]]@("--telemetry", ('"{0}"' -f $TelemetryCsv)))
    }
    $liveArguments = $liveArgumentList -join " "
    $live = Start-DirectProcess -FileName $python -Arguments $liveArguments `
        -WorkingDirectory $commercialRoot -Environment @{ PYTHONPATH = (Join-Path $commercialRoot "src") }
    $started += $live

    $siteArguments = @(
        ('"{0}"' -f $vinextCli),
        "start",
        "--hostname 127.0.0.1",
        "--port 3001"
    ) -join " "
    $site = Start-DirectProcess -FileName $node -Arguments $siteArguments `
        -WorkingDirectory $siteRoot -Environment @{ WRANGLER_LOG_PATH = ".wrangler/wrangler.log" }
    $started += $site

    $gateway = Start-DirectProcess -FileName $node -Arguments ('"{0}"' -f $gatewayScript) `
        -WorkingDirectory $siteRoot -Environment @{
            SATISH_GATEWAY_HOST = "127.0.0.1"
            SATISH_GATEWAY_PORT = "3000"
            SATISH_RENDERER_PORT = "3001"
            SATISH_LIVE_PORT = "8765"
            SATISH_INTERNAL_TOKEN = $internalToken
        }
    $started += $gateway

    if (-not (Wait-LocalEndpoint -Uri "http://127.0.0.1:8501/_stcore/health")) {
        throw "The local operator console did not become healthy."
    }
    if (-not (Wait-LocalEndpoint -Uri "http://127.0.0.1:8765/api/v1/live/health")) {
        throw "The local live anomaly service did not become healthy."
    }
    if (-not (Wait-LocalEndpoint -Uri "http://127.0.0.1:3001/")) {
        throw "The internal site renderer did not become healthy."
    }
    if (-not (Wait-LocalEndpoint -Uri "http://127.0.0.1:3000/")) {
        throw "The local dashboard gateway did not become healthy."
    }

    $homeResponse = Invoke-WebRequest -Uri "http://127.0.0.1:3000/" -UseBasicParsing -TimeoutSec 5
    $styleMatch = [regex]::Match($homeResponse.Content, 'href="(?<path>/assets/[^"?]+\.css)"')
    if (-not $styleMatch.Success) {
        throw "The local page did not reference a compiled stylesheet."
    }
    $styleResponse = Invoke-WebRequest -Uri ("http://127.0.0.1:3000" + $styleMatch.Groups["path"].Value) -UseBasicParsing -TimeoutSec 5
    if ($styleResponse.StatusCode -ne 200 -or $styleResponse.Headers["Content-Type"] -notmatch "text/css") {
        throw "The local compiled stylesheet was not served correctly."
    }
    $snapshotResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8765/api/v1/live/snapshot" `
        -Headers @{ Authorization = "Bearer $internalToken" } -UseBasicParsing -TimeoutSec 5
    $snapshot = $snapshotResponse.Content | ConvertFrom-Json
    if (-not $snapshot.artifact_hash -or -not $snapshot.config_hash) {
        throw "The live service did not report verified artifact and configuration identities."
    }

    $operatorListenerId = Get-LocalListenerProcessId -Port 8501
    $liveListenerId = Get-LocalListenerProcessId -Port 8765
    $rendererListenerId = Get-LocalListenerProcessId -Port 3001
    $gatewayListenerId = Get-LocalListenerProcessId -Port 3000
    $operatorListener = Get-Process -Id $operatorListenerId -ErrorAction Stop
    $liveListener = Get-Process -Id $liveListenerId -ErrorAction Stop
    $rendererListener = Get-Process -Id $rendererListenerId -ErrorAction Stop
    $gatewayListener = Get-Process -Id $gatewayListenerId -ErrorAction Stop

    $state = [ordered]@{
        schema_version = "1.0.0"
        started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        binding = "127.0.0.1-only"
        run_directory = $RunDirectory
        internal_token = $internalToken
        processes = @(
            [ordered]@{
                name = "operator-console"
                pid = $operatorListener.Id
                executable = $operatorListener.Path
                url = "http://127.0.0.1:8501/"
            },
            [ordered]@{
                name = "live-anomaly-engine"
                pid = $liveListener.Id
                executable = $liveListener.Path
                url = "http://127.0.0.1:8765/api/v1/live/health"
            },
            [ordered]@{
                name = "internal-site-renderer"
                pid = $rendererListener.Id
                executable = $rendererListener.Path
                url = "http://127.0.0.1:3001/"
            },
            [ordered]@{
                name = "local-dashboard"
                pid = $gatewayListener.Id
                executable = $gatewayListener.Path
                url = "http://127.0.0.1:3000/"
            }
        )
    }
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8

    Write-Host "SATISH Local is running on this computer only." -ForegroundColor Green
    Write-Host "Operator console: http://127.0.0.1:8501/"
    Write-Host "Live dashboard:   http://127.0.0.1:3000/live"
    Write-Host "Stop both with scripts\Stop-SATISH-Local.cmd"

    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:8501/"
        Start-Process "http://127.0.0.1:3000/"
    }
}
catch {
    foreach ($process in $started) {
        if ($null -ne (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $statePath) {
        Remove-Item -LiteralPath $statePath -Force
    }
    throw
}
