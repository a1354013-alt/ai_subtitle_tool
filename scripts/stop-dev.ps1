$ErrorActionPreference = "SilentlyContinue"

$ports = @(8891, 5173)
foreach ($port in $ports) {
    Get-NetTCPConnection -LocalPort $port | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force
        Write-Host "Stopped process $($_.OwningProcess) on port $port"
    }
}

$celery = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like "celery*" -or $_.CommandLine -like "*backend.celery_app*"
}
$celery | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
    Write-Host "Stopped Celery-related process $($_.ProcessId)"
}
Write-Host "Dev services stopped where matching processes were found."
