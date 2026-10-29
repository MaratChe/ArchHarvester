$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
docker build -t architecture-registry-javascript:2 (Join-Path $projectRoot 'backend/javascript-runner')
if ($LASTEXITCODE -ne 0) { throw 'Failed to build JavaScript Worker runner' }
