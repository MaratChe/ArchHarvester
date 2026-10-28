param([int]$Port = 8765, [string]$DataDir = '', [switch]$NoBrowser, [string]$CaBundle = '')
$ErrorActionPreference = 'Stop'
if ($CaBundle) { $env:ARCH_REGISTRY_CA_BUNDLE = (Resolve-Path -LiteralPath $CaBundle -ErrorAction Stop).Path }
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend/dist/index.html'))) { throw 'Build frontend first: npm --prefix frontend run build' }
if ($DataDir) { $env:ARCH_REGISTRY_DATA = $DataDir }
& $pythonPath -c "from backend.app.tls import client_ssl_context; client_ssl_context()"
if ($LASTEXITCODE -ne 0) { throw 'HTTPS certificate configuration is invalid.' }
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
try { $listener.Start() } finally { $listener.Stop() }
if (-not $NoBrowser) {
    $browserJob = Start-Job -ArgumentList $Port -ScriptBlock {
        param($localPort)
        for ($i=0; $i -lt 40; $i++) {
            try {
                $result = Invoke-WebRequest -Uri "http://127.0.0.1:$localPort/api/session" -UseBasicParsing -TimeoutSec 1
                if ($result.StatusCode -eq 200) { Start-Process "http://127.0.0.1:$localPort"; break }
            } catch { Start-Sleep -Milliseconds 500 }
        }
    }
}
Write-Host "Architecture Registry Studio: http://127.0.0.1:$Port (Ctrl+C to stop)"
try { & $pythonPath -m uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port $Port }
finally { if ($browserJob) { Stop-Job $browserJob; Remove-Job $browserJob } }
