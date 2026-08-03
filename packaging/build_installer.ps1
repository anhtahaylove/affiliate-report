param(
    [switch]$SkipAppBuild,
    [string]$AppVersion = '1.1.0'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$distExe = Join-Path $root 'dist\TikTokAffiliateReport.exe'
$setupExe = Join-Path $root "artifacts\installer\TikTokAffiliateReportSetup-v$AppVersion.exe"
$checksumFile = Join-Path $root 'artifacts\installer\SHA256SUMS.txt'
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

$hashes = Get-FileHash -Algorithm SHA256 $distExe, $setupExe
$lines = $hashes | ForEach-Object { "{0}  {1}" -f $_.Hash, (Split-Path -Leaf $_.Path) }
[IO.File]::WriteAllLines($checksumFile, $lines, [Text.UTF8Encoding]::new($false))
$hashes | Format-Table Path, Hash -AutoSize
Write-Output "SHA256SUMS: $checksumFile"
Write-Warning 'EXE và installer không được code-sign; Windows SmartScreen có thể cảnh báo.'
