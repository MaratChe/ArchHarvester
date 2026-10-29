$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
docker build -t architecture-registry-python:2 (Join-Path $projectRoot 'backend/runner')
if ($LASTEXITCODE -ne 0) { throw 'Failed to build isolated Python runner' }
