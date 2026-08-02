param(
    [switch]$SkipAppBuild,
    [switch]$SkipSigning,
    [switch]$CreateSelfSignedCert,
    [switch]$RequireTrustedCertificate,
    [string]$CertificateThumbprint,
    [string]$TimestampServer,
    [string]$AppVersion = '1.0.0'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$distExe = Join-Path $root 'dist\TikTokAffiliateReport.exe'
$setupExe = Join-Path $root 'artifacts\installer\TikTokAffiliateReportSetup.exe'
$installerScript = Join-Path $PSScriptRoot 'TikTokAffiliateReport.iss'
$privacyGate = Join-Path $PSScriptRoot 'assert_no_embedded_database.ps1'
$signTool = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe' -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1
$iscc = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1

function Get-InstallerSigningCert {
    $certs = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) }
    if ($CertificateThumbprint) {
        $cert = $certs | Where-Object Thumbprint -eq $CertificateThumbprint | Select-Object -First 1
        if (!$cert) { throw "Code-signing certificate not found: $CertificateThumbprint" }
    } else {
        $cert = $certs |
            Where-Object Subject -Like '*TikTok Affiliate Report*' |
            Sort-Object NotAfter -Descending |
            Select-Object -First 1
    }

    if (!$cert -and $CreateSelfSignedCert) {
        $cert = New-SelfSignedCertificate `
            -Type CodeSigningCert `
            -Subject 'CN=TikTok Affiliate Report Local Development Code Signing' `
            -CertStoreLocation Cert:\CurrentUser\My `
            -Provider 'Microsoft Enhanced RSA and AES Cryptographic Provider' `
            -KeyAlgorithm RSA `
            -KeyLength 3072 `
            -HashAlgorithm SHA256 `
            -NotAfter (Get-Date).AddYears(2)
    }

    $cert
}

function Sign-Artifact($path, $cert) {
    if (!$cert) { return }
    if ($TimestampServer -and $signTool) {
        & $signTool sign /sha1 $cert.Thumbprint /fd SHA256 /tr $TimestampServer /td SHA256 $path
        if ($LASTEXITCODE) { throw "signtool failed for $path with exit code $LASTEXITCODE" }
    } else {
        $parameters = @{ FilePath = $path; Certificate = $cert; HashAlgorithm = 'SHA256' }
        if ($TimestampServer) { $parameters.TimestampServer = $TimestampServer }
        $result = Set-AuthenticodeSignature @parameters
    }
    $check = Get-AuthenticodeSignature $path
    if (!$check.SignerCertificate -or $check.SignerCertificate.Thumbprint -ne $cert.Thumbprint) {
        throw "Signing failed for $path`: $($result.Status) $($result.StatusMessage)"
    }
    if ($RequireTrustedCertificate -and $check.Status -ne 'Valid') {
        throw "Trusted signing gate failed for $path`: $($check.Status) $($check.StatusMessage)"
    }
    if (!$RequireTrustedCertificate -and $check.Status -notin @('Valid', 'UnknownError')) {
        throw "Signing failed for $path`: $($check.Status) $($check.StatusMessage)"
    }
    if ($TimestampServer -and !$check.TimeStamperCertificate) {
        throw "Timestamp verification failed for $path"
    }
}

if ($RequireTrustedCertificate) {
    if (!$CertificateThumbprint) { throw '-RequireTrustedCertificate requires -CertificateThumbprint.' }
    if (!$TimestampServer) { throw '-RequireTrustedCertificate requires -TimestampServer.' }
    if ($CreateSelfSignedCert) { throw '-CreateSelfSignedCert cannot be used for a trusted public release.' }
}

if (!$SkipAppBuild) {
    & (Join-Path $root 'BUILD_EXE.bat')
    if ($LASTEXITCODE) { throw "BUILD_EXE.bat failed with exit code $LASTEXITCODE" }
}

if (!(Test-Path -LiteralPath $distExe)) { throw "Missing app EXE: $distExe" }
& $privacyGate -Path $distExe
if (!(Test-Path -LiteralPath $installerScript)) { throw "Missing Inno Setup script: $installerScript" }
if (!$iscc) { throw 'Inno Setup 6 is required. Install it with: winget install --id JRSoftware.InnoSetup --exact' }

$cert = $null
if (!$SkipSigning) {
    $cert = Get-InstallerSigningCert
    if ($cert) {
        if ($RequireTrustedCertificate -and $cert.Subject -eq $cert.Issuer) {
            throw "Trusted release certificate is self-signed: $($cert.Subject)"
        }
        Write-Host "Signing with certificate: $($cert.Subject) [$($cert.Thumbprint)]"
        Sign-Artifact $distExe $cert
    } else {
        Write-Warning 'No TikTok Affiliate Report code-signing certificate found. Re-run with -CreateSelfSignedCert for local/dev signing.'
    }
}

& $iscc "/DMyAppVersion=$AppVersion" $installerScript
if ($LASTEXITCODE) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
if (!(Test-Path -LiteralPath $setupExe)) { throw "Installer was not created: $setupExe" }

if ($cert -and !$SkipSigning) { Sign-Artifact $setupExe $cert }

Get-FileHash -Algorithm SHA256 $distExe, $setupExe | Format-Table Path, Hash -AutoSize
Get-AuthenticodeSignature $distExe, $setupExe | Format-Table Path, Status, StatusMessage -AutoSize
