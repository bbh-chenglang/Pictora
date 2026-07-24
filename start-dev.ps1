$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$pythonVersionFile = Join-Path $projectRoot ".python-version"
$venvPath = Join-Path $projectRoot "backend\.venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not $uvCommand) {
    throw "uv was not found. Install uv and run this script again."
}

if (-not (Test-Path $pythonVersionFile)) {
    throw "Missing .python-version; cannot determine the project Python version."
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

$node = (Get-Command node).Source
$npmCli = Join-Path (Split-Path $node) "node_modules\npm\bin\npm-cli.js"

if (-not (Test-Path $npmCli)) {
    throw "npm CLI was not found: $npmCli"
}

$backend = Start-Process `
    -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8002", "--reload") `
    -WorkingDirectory $projectRoot `
    -PassThru

$frontend = Start-Process `
    -FilePath $node `
    -ArgumentList @($npmCli, "run", "dev", "--", "--host", "localhost", "--port", "5175", "--strictPort") `
    -WorkingDirectory (Join-Path $projectRoot "frontend") `
    -PassThru

Write-Host "GenImage development services started:" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5175/"
Write-Host "Backend: http://localhost:8002/"
Write-Host "Press Ctrl+C to stop both services."

try {
    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Seconds 1
    }
}
finally {
    foreach ($process in @($backend, $frontend)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
