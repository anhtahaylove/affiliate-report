param(
    [Parameter(Mandatory)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$archiveViewer = Join-Path $root '.venv\Scripts\pyi-archive_viewer.exe'
$artifact = (Resolve-Path -LiteralPath $Path).Path

# Bản onedir là một thư mục: quét thẳng cây file, không cần đọc archive nữa.
if (Test-Path -LiteralPath $artifact -PathType Container) {
    # -Include trên -LiteralPath khớp mọi thứ; lọc theo phần mở rộng mới đúng.
    $found = Get-ChildItem -LiteralPath $artifact -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.db', '.sqlite', '.sqlite3' }
    if ($found) {
        throw "Release privacy gate failed: embedded database found: $($found.FullName -join ', ')"
    }
    $exe = Join-Path $artifact 'TikTokAffiliateReport.exe'
    if (!(Test-Path -LiteralPath $exe)) {
        throw "Release privacy gate failed: missing $exe"
    }
    Write-Host "Release privacy gate passed: $artifact"
    exit 0
}

if (!(Test-Path -LiteralPath $archiveViewer)) {
    throw "PyInstaller archive viewer is required for the release privacy gate: $archiveViewer"
}

$listing = & $archiveViewer -l $artifact 2>&1
if ($LASTEXITCODE) { throw "Could not inspect PyInstaller archive: $artifact" }
if (($listing -join "`n") -match "seed[/\\].*\.(db|sqlite|sqlite3)") {
    throw "Release privacy gate failed: embedded database found in $artifact"
}

Write-Host "Release privacy gate passed: $artifact"
