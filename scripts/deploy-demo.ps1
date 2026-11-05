param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
    }
    $composeArgs = @('compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.demo.yml')
    & docker @composeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Configuración Compose inválida.' }
    $upArgs = @('up', '-d', '--wait', '--wait-timeout', '180')
    if (-not $SkipBuild) { $upArgs += '--build' }
    & docker @composeArgs @upArgs
    if ($LASTEXITCODE -ne 0) { throw 'El despliegue falló. Consulta docker compose logs.' }
    $workflowList = & docker @composeArgs exec -T n8n n8n list:workflow 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar los workflows de n8n.' }
    if (-not $workflowList) {
        & docker @composeArgs exec -T n8n n8n import:workflow --separate --input=/workflows
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron importar los workflows de n8n.' }
        Write-Host 'n8n: 5 workflows importados (inactivos por seguridad).'
    }
    Write-Host 'SOC-Lite: http://localhost:8080'
    Write-Host 'API: http://localhost:8080/docs'
    Write-Host 'n8n: http://localhost:5678'
    Write-Host 'Demo: admin / Admin123!'
} finally { Pop-Location }
