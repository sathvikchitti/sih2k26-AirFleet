[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1024, 65535)]
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$backendDir = Join-Path $workspace 'backend'
$frontendDir = Join-Path $workspace 'frontend'
$modelPath = Join-Path $backendDir 'models/cmapss_fd001_rf_v1.joblib'
$testDataPath = Join-Path $workspace 'CMAPSSData/test_FD001.txt'
$backendProcess = $null
$frontendProcess = $null

function Test-LoopbackPortAvailable([int]$Port) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Stop-OwnedProcess($Process) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        try {
            $Process.Kill($true)
            $Process.WaitForExit(5000) | Out-Null
        } catch {
            Write-Warning "Could not stop launcher-owned process $($Process.Id): $($_.Exception.Message)"
        }
    }
}

function Wait-ForHttp([string]$Url, $Process, [string]$Label) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($Process.HasExited) {
            throw "$Label exited during startup. See its run_demo log under backend/."
        }
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "$Label did not become ready at $Url within 60 seconds. See its run_demo log under backend/."
}

if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
    throw "FD001 model artifact is missing: $modelPath. Train it using the command in README.md."
}
if (-not (Test-Path -LiteralPath $testDataPath -PathType Leaf)) {
    throw "FD001 test history is missing: $testDataPath. See README.md for the local dataset files."
}
$pythonCommand = Get-Command python -ErrorAction Stop
$nodeCommand = Get-Command node -ErrorAction Stop
$vitePath = Join-Path $frontendDir 'node_modules/vite/bin/vite.js'
if (-not (Test-Path -LiteralPath $vitePath -PathType Leaf)) {
    throw "Frontend dependencies are not installed. Run 'npm ci' from $frontendDir first."
}
& $pythonCommand.Source -c 'import fastapi, joblib, numpy, sklearn, uvicorn' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Backend dependencies are not installed for '$($pythonCommand.Source)'. Run 'python -m pip install -r backend/requirements.txt' first."
}
foreach ($port in @($BackendPort, $FrontendPort)) {
    if (-not (Test-LoopbackPortAvailable $port)) {
        throw "Port $port is already in use. No process was stopped. Choose an unused port with -BackendPort and -FrontendPort."
    }
}
if ($BackendPort -eq $FrontendPort) {
    throw 'Backend and frontend ports must differ. No process was started.'
}

$runId = [Guid]::NewGuid().ToString('N')
$backendOut = Join-Path $backendDir "run_demo_backend_$runId.out.log"
$backendErr = Join-Path $backendDir "run_demo_backend_$runId.err.log"
$frontendOut = Join-Path $backendDir "run_demo_frontend_$runId.out.log"
$frontendErr = Join-Path $backendDir "run_demo_frontend_$runId.err.log"
$frontendOrigins = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"
$apiProxyTarget = "http://127.0.0.1:$BackendPort"

$env:ML_PROVIDER = 'fd001'
$env:DEMO_SCENARIO = 'fd001_operations'
$env:DEMO_RESET_ENABLED = 'true'
$env:DEMO_PERMISSION_MODE = 'hardened'
$env:DEMO_BACKEND_PORT = "$BackendPort"
$env:DEMO_FRONTEND_PORT = "$FrontendPort"
$env:FRONTEND_ORIGINS = $frontendOrigins
$env:FD001_MODEL_PATH = $modelPath
$env:FD001_DATA_DIR = Join-Path $workspace 'CMAPSSData'
$env:API_PROXY_TARGET = $apiProxyTarget
# An explicit empty process value overrides any developer-local dotenv value.
$env:VITE_API_BASE = ''

try {
    $backendProcess = Start-Process -FilePath $pythonCommand.Source `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
        -WorkingDirectory $backendDir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr
    Wait-ForHttp "http://127.0.0.1:$BackendPort/api/health" $backendProcess 'FD001 backend'

    $frontendProcess = Start-Process -FilePath $nodeCommand.Source `
        -ArgumentList "`"$vitePath`" --host 127.0.0.1 --port $FrontendPort --strictPort" `
        -WorkingDirectory $frontendDir -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr
    Wait-ForHttp "http://127.0.0.1:$FrontendPort/" $frontendProcess 'Vite frontend'

    Write-Host "FD001 operations demo is ready: http://localhost:$FrontendPort/ (API on http://127.0.0.1:$BackendPort)."
    Write-Host "Provider: fd001; scenario: fd001_operations; reset enabled. Press Ctrl+C to stop only launcher-owned processes."
    Write-Host "Logs: $backendOut ; $backendErr ; $frontendOut ; $frontendErr"
    while ($true) {
        if ($backendProcess.HasExited) { throw "Backend exited. See $backendErr" }
        if ($frontendProcess.HasExited) { throw "Frontend exited. See $frontendErr" }
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-OwnedProcess $frontendProcess
    Stop-OwnedProcess $backendProcess
}
