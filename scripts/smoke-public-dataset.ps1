param([string]$BaseUrl = 'http://localhost:8080')
$ErrorActionPreference = 'Stop'
$session = Invoke-RestMethod "$BaseUrl/api/v1/auth/login" -Method Post -ContentType 'application/x-www-form-urlencoded' -Body @{username='admin';password='Admin123!'}
$headers = @{Authorization="Bearer $($session.access_token)"}
try {
    $first = Invoke-RestMethod "$BaseUrl/api/v1/datasets/loghub-openssh/import" -Method Post -Headers $headers
    if ($first.imported + $first.skipped -ne 2000) { throw 'Importación incompleta.' }
    Write-Host "OK: primera importación: $($first.imported) nuevos, $($first.skipped) existentes."
    $repeat = Invoke-RestMethod "$BaseUrl/api/v1/datasets/loghub-openssh/import" -Method Post -Headers $headers
    if ($repeat.imported -ne 0 -or $repeat.skipped -ne 2000) { throw 'La importación no fue idempotente.' }
    Write-Host 'OK: repetición sin duplicados.'
    $summary = Invoke-RestMethod "$BaseUrl/api/v1/datasets/loghub-openssh" -Headers $headers
    if ($summary.imported_records -ne 2000) { throw 'Conteo de PostgreSQL incorrecto.' }
    $sum = ($summary.event_types | Measure-Object count -Sum).Sum
    if ($sum -ne 2000) { throw 'Estadísticas incompletas.' }
    $source = [Uri]::EscapeDataString('Loghub OpenSSH · registros reales')
    $page = Invoke-RestMethod "$BaseUrl/api/v1/alerts?source_name=$source&page_size=1" -Headers $headers
    if ($page.total -ne 2000) { throw 'Filtro del dataset incorrecto.' }
    $detail = Invoke-RestMethod "$BaseUrl/api/v1/alerts/$($page.items[0].id)" -Headers $headers
    if ($detail.raw_payload.data_origin -ne 'public_dataset' -or $detail.verdict -or $detail.triaged_at) { throw 'Procedencia o veredicto inválidos.' }
    if ($detail.full_log -ne $detail.raw_payload.original_line) { throw 'Se modificó la evidencia original.' }
    $export = Invoke-RestMethod "$BaseUrl/api/v1/datasets/loghub-openssh/export" -Headers $headers
    if ($export.records.Count -ne 2000 -or $export.manifest.sha256 -ne $summary.manifest.sha256) { throw 'Exportación no reproducible.' }
    Write-Host 'OK: estadísticas, evidencia original, filtro y exportación JSON de 2000 registros.'
    $viewer = Invoke-RestMethod "$BaseUrl/api/v1/auth/login" -Method Post -ContentType 'application/x-www-form-urlencoded' -Body @{username='visor1';password='Viewer123!'}
    try {
        try {
            $null = Invoke-RestMethod "$BaseUrl/api/v1/datasets/loghub-openssh/import" -Method Post -Headers @{Authorization="Bearer $($viewer.access_token)"}
            throw 'RBAC permitió importar al visor.'
        } catch {
            if ($_.Exception.Response.StatusCode.value__ -ne 403) { throw }
        }
    } finally {
        $null = Invoke-RestMethod "$BaseUrl/api/v1/auth/logout" -Method Post -Headers @{Authorization="Bearer $($viewer.access_token)"} -ContentType 'application/json' -Body (@{refresh_token=$viewer.refresh_token} | ConvertTo-Json)
    }
    Write-Host 'OK: importación protegida por RBAC.'
    $summary | Select-Object imported_records,other_records,unique_ips,unique_users,event_types | ConvertTo-Json -Depth 5
} finally {
    $null = Invoke-RestMethod "$BaseUrl/api/v1/auth/logout" -Method Post -Headers $headers -ContentType 'application/json' -Body (@{refresh_token=$session.refresh_token} | ConvertTo-Json)
}
