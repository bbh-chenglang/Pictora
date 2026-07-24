$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python).Source
$node = (Get-Command node).Source
$npmCli = Join-Path (Split-Path $node) "node_modules\npm\bin\npm-cli.js"

if (-not (Test-Path $npmCli)) {
    throw "找不到 npm CLI: $npmCli"
}

$backend = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8002", "--reload") `
    -WorkingDirectory $projectRoot `
    -PassThru

$frontend = Start-Process `
    -FilePath $node `
    -ArgumentList @($npmCli, "run", "dev", "--", "--host", "localhost", "--port", "5174") `
    -WorkingDirectory (Join-Path $projectRoot "frontend") `
    -PassThru

Write-Host "GenImage 开发服务已启动：" -ForegroundColor Green
Write-Host "前端: http://localhost:5174/"
Write-Host "后端: http://localhost:8002/"
Write-Host "按 Ctrl+C 停止前后端服务。"

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
