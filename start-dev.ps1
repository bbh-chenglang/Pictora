$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendRoot = Join-Path $projectRoot "frontend"
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$pythonVersionFile = Join-Path $projectRoot ".python-version"
$venvPath = Join-Path $projectRoot "backend\.venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$node = Get-Command node -ErrorAction SilentlyContinue
$backendPort = 8002
$frontendPort = 5175

function Get-DescendantProcessIds([int]$parentId) {
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $parentId")
    foreach ($child in $children) {
        $child.ProcessId
        Get-DescendantProcessIds $child.ProcessId
    }
}

function Stop-ProcessTree([int]$rootId) {
    $processIds = @($rootId) + @(Get-DescendantProcessIds $rootId) | Select-Object -Unique
    foreach ($processId in ($processIds | Sort-Object -Descending)) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

function Get-ProjectProcessIds {
    $rootPattern = [regex]::Escape($projectRoot)
    $frontendPattern = [regex]::Escape($frontendRoot)
    $processes = Get-CimInstance Win32_Process
    foreach ($process in $processes) {
        $commandLine = [string]$process.CommandLine
        $isBackend = $commandLine -match 'uvicorn app\.main:app.*--app-dir backend'
        $isProjectBackend = $commandLine -match $rootPattern -and $isBackend
        $isProjectFrontend = $commandLine -match $frontendPattern -and ($commandLine -match 'vite|npm-cli')
        if ($isProjectBackend -or $isProjectFrontend) {
            $process.ProcessId
        }
    }
}

function Test-PortInUse([int]$port) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        if (Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue) {
            return $true
        }
    }
    return $false
}

function Wait-Endpoint([string]$url, [int]$timeoutSeconds = 15) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Service did not become ready: $url"
}

if (-not $uvCommand) {
    throw "uv was not found. Install uv and run this script again."
}
if (-not $node) {
    throw "node was not found. Install Node.js and run this script again."
}
if (-not (Test-Path $pythonVersionFile)) {
    throw "Missing .python-version; cannot determine the project Python version."
}

foreach ($processId in @(Get-ProjectProcessIds)) {
    Stop-ProcessTree $processId
}
Start-Sleep -Milliseconds 500

foreach ($port in @($backendPort, $frontendPort)) {
    if (Test-PortInUse $port) {
        throw "Port $port is already used by another running process."
    }
}

$pythonVersion = (Get-Content $pythonVersionFile -Raw).Trim()
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating the Python $pythonVersion virtual environment with uv..." -ForegroundColor Cyan
    & $uvCommand.Source venv $venvPath --python $pythonVersion
    if ($LASTEXITCODE -ne 0) {
        throw "uv failed to create the Python virtual environment."
    }
}

Write-Host "Installing backend dependencies with uv..." -ForegroundColor Cyan
& $uvCommand.Source pip install --python $venvPython --link-mode=copy -r (Join-Path $projectRoot "backend\requirements-dev.txt")
if ($LASTEXITCODE -ne 0) {
    throw "uv failed to install backend dependencies."
}

$npmCli = Join-Path (Split-Path $node.Source) "node_modules\npm\bin\npm-cli.js"
if (-not (Test-Path $npmCli)) {
    throw "npm CLI was not found: $npmCli"
}

$backend = $null
$frontend = $null
try {
    $backend = Start-Process `
        -FilePath $venvPython `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "$backendPort", "--reload") `
        -WorkingDirectory $projectRoot `
        -PassThru

    $frontend = Start-Process `
        -FilePath $node.Source `
        -ArgumentList @($npmCli, "run", "dev", "--", "--host", "localhost", "--port", "$frontendPort", "--strictPort") `
        -WorkingDirectory $frontendRoot `
        -PassThru

    Wait-Endpoint "http://127.0.0.1:$backendPort/health"
    Wait-Endpoint "http://localhost:$frontendPort/"

    Write-Host "GenImage development services started:" -ForegroundColor Green
    Write-Host "Frontend: http://localhost:$frontendPort/"
    Write-Host "Backend: http://localhost:$backendPort/"
    Write-Host "Press Ctrl+C to stop both services."

    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    if ($backend) { Stop-ProcessTree $backend.Id }
    if ($frontend) { Stop-ProcessTree $frontend.Id }
}
