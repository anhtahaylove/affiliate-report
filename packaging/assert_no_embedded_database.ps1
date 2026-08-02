param(
    [Parameter(Mandatory)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$archiveViewer = Join-Path $root '.venv\Scripts\pyi-archive_viewer.exe'
$artifact = (Resolve-Path -LiteralPath $Path).Path

if (!(Test-Path -LiteralPath $archiveViewer)) {
    throw "PyInstaller archive viewer is required for the release privacy gate: $archiveViewer"
}

$listing = & $archiveViewer -l $artifact 2>&1
if ($LASTEXITCODE) { throw "Could not inspect PyInstaller archive: $artifact" }
if (($listing -join "`n") -match "seed[/\\].*\.(db|sqlite|sqlite3)") {
    throw "Release privacy gate failed: embedded database found in $artifact"
}

Write-Host "Release privacy gate passed: $artifact"
