param([string]$Path)
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
try {
    Write-Output ("Total entries: " + $zip.Entries.Count)
    Write-Output "--- Top-level + key files ---"
    $zip.Entries |
        Where-Object { $_.FullName -notmatch '__pycache__' } |
        Sort-Object FullName |
        Select-Object -First 40 |
        ForEach-Object { Write-Output $_.FullName }
} finally {
    $zip.Dispose()
}
