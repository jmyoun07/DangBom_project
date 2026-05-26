param([int]$Port = 8000)
$procIds = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $procIds) {
    taskkill /F /PID $procId 2>&1 | Out-Null
}
Start-Sleep -Seconds 1
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Write-Output "still-listening"
    exit 1
} else {
    Write-Output "killed"
}
