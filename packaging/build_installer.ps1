param(
    [switch]$SkipAppBuild,
    [string]$AppVersion = '2.0.5'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
# onedir: staging là một THƯ MỤC (exe + _internal), không còn là một file .exe đơn lẻ.
$appDir = Join-Path $root 'build\installer-app\TikTokAffiliateReport'
$outputDir = Join-Path $root 'artifacts\installer'
$setupExe = Join-Path $root "artifacts\installer\TikTokAffiliateReportSetup-v$AppVersion.exe"
$checksumFile = Join-Path $root 'artifacts\installer\SHA256SUMS.txt'
$staleMetadata = @($checksumFile, (Join-Path $outputDir 'stable.json'), (Join-Path $outputDir 'stable.json.sig'))
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

if (!(Test-Path -LiteralPath $appDir)) { throw "Missing staged app folder: $appDir" }
& $privacyGate -Path $appDir
if (!(Test-Path -LiteralPath $installerScript)) { throw "Missing Inno Setup script: $installerScript" }
if (!$iscc) { throw 'Inno Setup 6 is required. Install it with: winget install --id JRSoftware.InnoSetup --exact' }

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
Get-ChildItem -LiteralPath $outputDir -Filter 'TikTokAffiliateReportSetup*.exe' -File | Remove-Item -Force
Remove-Item -LiteralPath $staleMetadata -Force -ErrorAction SilentlyContinue

& $iscc "/DMyAppVersion=$AppVersion" $installerScript
if ($LASTEXITCODE) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
if (!(Test-Path -LiteralPath $setupExe)) { throw "Installer was not created: $setupExe" }

$hash = Get-FileHash -Algorithm SHA256 $setupExe
[IO.File]::WriteAllText($checksumFile, ("{0}  {1}`n" -f $hash.Hash, (Split-Path -Leaf $hash.Path)), [Text.UTF8Encoding]::new($false))
$hash | Format-Table Path, Hash -AutoSize
Write-Output "SHA256SUMS: $checksumFile"
Write-Warning 'Installer không được code-sign; Windows SmartScreen có thể cảnh báo.'
