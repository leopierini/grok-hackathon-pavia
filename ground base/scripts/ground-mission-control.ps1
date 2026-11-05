$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

$Ui = Join-Path $Root "ui\mission-control"
if (-not (Test-Path (Join-Path $Ui "node_modules"))) {
    Push-Location $Ui
    npm install
    Pop-Location
}

$env:GROUND_OPERATOR_TOKEN = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
$env:GROUND_API_ORIGIN = "http://127.0.0.1:8765"

$Python = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList @("-m", "patrol.ground.operator", "--host", "127.0.0.1", "--port", "8765") -WorkingDirectory $Root -PassThru -NoNewWindow
$Web = Start-Process -FilePath "npm" -ArgumentList @("run", "dev") -WorkingDirectory $Ui -PassThru -NoNewWindow

Write-Host "Ground Mission Control"
Write-Host "UI    http://127.0.0.1:3000"
Write-Host "API   http://127.0.0.1:8765"
Write-Host "Close this window to stop both processes."

try {
    while (-not $Python.HasExited -and -not $Web.HasExited) {
        Start-Sleep -Seconds 1
    }
}
finally {
    foreach ($Process in @($Python, $Web)) {
        if ($Process -and -not $Process.HasExited) {
            taskkill /PID $Process.Id /T /F | Out-Null
        }
    }
}
