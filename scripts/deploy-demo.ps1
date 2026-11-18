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
    & docker @composeArgs up -d --wait postgres
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar PostgreSQL.' }
    & docker @composeArgs exec -T postgres sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/03-access-monitoring.sql -f /docker-entrypoint-initdb.d/04-access-evaluation.sql -f /docker-entrypoint-initdb.d/05-access-models.sql'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo actualizar la base de datos para el Caso 5.' }
    $upArgs = @('up', '-d', '--wait', '--wait-timeout', '180')
    if (-not $SkipBuild) { $upArgs += '--build' }
    & docker @composeArgs @upArgs
    if ($LASTEXITCODE -ne 0) { throw 'El despliegue falló. Consulta docker compose logs.' }
    $workflowList = & docker @composeArgs exec -T n8n n8n list:workflow 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar los workflows de n8n.' }
    if (-not $workflowList) {
        & docker @composeArgs exec -T n8n n8n import:workflow --separate --input=/workflows
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron importar los workflows de n8n.' }
        Write-Host 'n8n: workflows importados (inactivos).'
    } elseif (-not ($workflowList -match 'Case05AccessLogs')) {
        & docker @composeArgs exec -T n8n n8n import:workflow --input=/workflows/soc_lite_access_monitoring_workflow.json
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo importar el workflow del Caso 5.' }
        Write-Host 'n8n: workflow del Caso 5 importado (inactivo).'
    }
    Write-Host 'SOC-Lite: http://localhost:8080'
    Write-Host 'API: http://localhost:8080/docs'
    Write-Host 'n8n: http://localhost:5678'
    Write-Host 'Demo: admin / Admin123!'
} finally { Pop-Location }
