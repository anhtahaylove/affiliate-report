param(
    [switch]$SkipAppBuild,
    [string]$AppVersion = '1.0.0'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$distExe = Join-Path $root 'dist\TikTokAffiliateReport.exe'
$setupExe = Join-Path $root 'artifacts\installer\TikTokAffiliateReportSetup.exe'
$installerScript = Join-Path $PSScriptRoot 'TikTokAffiliateReport.iss'
$privacyGate = Join-Path $PSScriptRoot 'assert_no_embedded_database.ps1'
$iscc = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1

if (!$SkipAppBuild) {
    & (Join-Path $root 'BUILD_EXE.bat')
    if ($LASTEXITCODE) { throw "BUILD_EXE.bat failed with exit code $LASTEXITCODE" }
}

if (!(Test-Path -LiteralPath $distExe)) { throw "Missing app EXE: $distExe" }
& $privacyGate -Path $distExe
if (!(Test-Path -LiteralPath $installerScript)) { throw "Missing Inno Setup script: $installerScript" }
if (!$iscc) { throw 'Inno Setup 6 is required. Install it with: winget install --id JRSoftware.InnoSetup --exact' }

& $iscc "/DMyAppVersion=$AppVersion" $installerScript
if ($LASTEXITCODE) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
if (!(Test-Path -LiteralPath $setupExe)) { throw "Installer was not created: $setupExe" }

Get-FileHash -Algorithm SHA256 $distExe, $setupExe | Format-Table Path, Hash -AutoSize
Write-Warning 'EXE và installer không được code-sign; Windows SmartScreen có thể cảnh báo.'
