param([string]$BaseUrl = 'http://localhost:8080')
$ErrorActionPreference = 'Stop'
$health = Invoke-RestMethod "$BaseUrl/api/v1/health/ready"
if ($health.status -ne 'ok' -or $health.components.database.status -ne 'ok' -or
    $health.components.llm_service.provider -ne 'mock') { throw 'Readiness demo inválido.' }
Write-Host 'OK: PostgreSQL y triaje mock disponibles.'

$session = Invoke-RestMethod "$BaseUrl/api/v1/auth/login" -Method Post -ContentType 'application/x-www-form-urlencoded' -Body @{username='admin';password='Admin123!'}
$headers = @{Authorization="Bearer $($session.access_token)"}
try {
    foreach ($path in @('/auth/me','/dashboard/summary','/alerts','/incidents','/users','/roles','/audit/logs','/triage/stats')) {
        $null = Invoke-RestMethod "$BaseUrl/api/v1$path" -Headers $headers
        Write-Host "OK: $path"
    }
    $renewed = Invoke-RestMethod "$BaseUrl/api/v1/auth/refresh" -Method Post -ContentType 'application/json' -Body (@{refresh_token=$session.refresh_token} | ConvertTo-Json)
    $session = $renewed
    $headers = @{Authorization="Bearer $($session.access_token)"}
    Write-Host 'OK: rotación de refresh token.'
    $alerts = Invoke-RestMethod "$BaseUrl/api/v1/alerts?page_size=1" -Headers $headers
    if ($alerts.items.Count -gt 0) {
        $id = $alerts.items[0].id
        $null = Invoke-RestMethod "$BaseUrl/api/v1/triage/$id/run?force=true" -Method Post -Headers $headers
        Write-Host 'OK: triaje demo persistido.'
    }
    foreach ($format in @('pdf','docx','xlsx')) {
        $response = Invoke-WebRequest "$BaseUrl/api/v1/reports/operational?format=$format" -Headers $headers
        if ($response.RawContentLength -lt 100) { throw "Reporte $format vacío." }
        Write-Host "OK: reporte $format ($($response.RawContentLength) bytes)."
    }
    $viewer = Invoke-RestMethod "$BaseUrl/api/v1/auth/login" -Method Post -ContentType 'application/x-www-form-urlencoded' -Body @{username='visor1';password='Viewer123!'}
    try {
        try {
            $null = Invoke-RestMethod "$BaseUrl/api/v1/users" -Headers @{Authorization="Bearer $($viewer.access_token)"}
            throw 'RBAC permitió consultar usuarios al rol consulta.'
        } catch {
            if ($_.Exception.Response.StatusCode.value__ -ne 403) { throw }
            Write-Host 'OK: RBAC devuelve 403 para consulta de usuarios por visor.'
        }
    } finally {
        $null = Invoke-RestMethod "$BaseUrl/api/v1/auth/logout" -Method Post -Headers @{Authorization="Bearer $($viewer.access_token)"} -ContentType 'application/json' -Body (@{refresh_token=$viewer.refresh_token} | ConvertTo-Json)
    }
} finally {
    $null = Invoke-RestMethod "$BaseUrl/api/v1/auth/logout" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{refresh_token=$session.refresh_token} | ConvertTo-Json)
}
Write-Host 'OK: prueba de humo finalizada.'
