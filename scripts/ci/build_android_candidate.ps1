[CmdletBinding()]
param(
    [ValidateSet("arm64Release", "ciRelease", "ciDebug")]
    [string]$Variant = "arm64Release",
    [switch]$SkipWebBuild
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$android = Join-Path $repo "android"
$native = Join-Path $android "native"
$version = "2.1.2"
$versionCode = "2001002"
$releaseCertificateSha256 = "d59c870025c9f9ee493046e52cc0cd25160e2d4b4204ba86ad3629d0dfe5fbe4"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is missing: $Name"
    }
}

Require-Command node
Require-Command npm
Require-Command java

$previousErrorActionPreference = $ErrorActionPreference
try {
    # java -version writes its normal output to stderr. Windows PowerShell 5.1
    # otherwise promotes that output to a terminating NativeCommandError.
    $ErrorActionPreference = "Continue"
    $javaOutput = @(& java -version 2>&1)
    $javaExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
$javaVersion = ($javaOutput | Select-Object -First 1).ToString()
if ($javaExitCode -ne 0) {
    throw "Unable to inspect the installed JDK: $javaVersion"
}
if ($javaVersion -notmatch 'version "(21|2[2-9]|[3-9][0-9])') {
    throw "JDK 21 or newer is required by Capacitor 8.5/AGP 8.13. Found: $javaVersion"
}
if (-not $env:ANDROID_HOME -and -not $env:ANDROID_SDK_ROOT) {
    throw "ANDROID_HOME or ANDROID_SDK_ROOT must point to Android SDK 36."
}
$sdkRoot = if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } else { $env:ANDROID_HOME }
$buildTools = Get-ChildItem -LiteralPath (Join-Path $sdkRoot "build-tools") -Directory |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if (-not $buildTools) { throw "Android SDK build-tools are missing under $sdkRoot." }
$aapt = Join-Path $buildTools.FullName "aapt.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
if (-not (Test-Path -LiteralPath $aapt -PathType Leaf) -or -not (Test-Path -LiteralPath $apksigner -PathType Leaf)) {
    throw "Android SDK build-tools must provide aapt.exe and apksigner.bat."
}

$isRelease = $Variant -in @("arm64Release", "ciRelease")
if ($isRelease) {
    $required = @(
        "ANDROID_KEYSTORE_PATH",
        "ANDROID_KEYSTORE_PASSWORD",
        "ANDROID_KEY_ALIAS",
        "ANDROID_KEY_PASSWORD"
    )
    $missing = @($required | Where-Object { -not [Environment]::GetEnvironmentVariable($_) })
    if ($missing.Count -gt 0) {
        throw "Release signing is fail-closed. Missing environment variables: $($missing -join ', ')"
    }
    if (-not (Test-Path -LiteralPath $env:ANDROID_KEYSTORE_PATH -PathType Leaf)) {
        throw "ANDROID_KEYSTORE_PATH does not point to a file."
    }
}

if (-not $SkipWebBuild) {
    Push-Location (Join-Path $repo "web")
    try {
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "pnpm install failed" }
        & pnpm build
        if ($LASTEXITCODE -ne 0) { throw "web production build failed" }
    } finally {
        Pop-Location
    }
}

Push-Location $android
try {
    & npm ci --ignore-scripts
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    & npx cap sync android
    if ($LASTEXITCODE -ne 0) { throw "Capacitor sync failed" }
} finally {
    Pop-Location
}

$task = switch ($Variant) {
    "arm64Release" { "assembleArm64Release" }
    "ciRelease" { "assembleCiSmoke" }
    default { "assembleCiDebug" }
}
Push-Location $native
try {
    & .\gradlew.bat --no-daemon --stacktrace $task
    if ($LASTEXITCODE -ne 0) { throw "Gradle task $task failed" }
} finally {
    Pop-Location
}

$source = switch ($Variant) {
    "arm64Release" { Join-Path $native "app\build\outputs\apk\arm64\release\app-arm64-release.apk" }
    "ciRelease" { Join-Path $native "app\build\outputs\apk\ci\smoke\app-ci-smoke.apk" }
    default { Join-Path $native "app\build\outputs\apk\ci\debug\app-ci-debug.apk" }
}
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Expected APK was not produced: $source"
}

$badging = (& $aapt dump badging $source 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect APK metadata: $badging" }
foreach ($expected in @(
    "name='vn.io.huuhungn.affiliatereport'",
    "versionCode='$versionCode'",
    "versionName='$version",
    "sdkVersion:'24'",
    "targetSdkVersion:'36'",
    "application-label:'Affiliate Report'"
)) {
    if ($badging -notmatch [regex]::Escape($expected)) { throw "APK metadata is missing $expected" }
}
$isDebuggable = $badging -match "(?m)^application-debuggable$"
if ($Variant -eq "arm64Release" -and $isDebuggable) {
    throw "Published arm64 APK must not be debuggable."
}
if ($Variant -ne "arm64Release" -and -not $isDebuggable) {
    throw "Internal x86_64 APK must be debuggable for private runtime-token smoke tests."
}

$apkEntries = (& $aapt list $source 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect APK contents: $apkEntries" }
$requiredAbi = if ($Variant -eq "arm64Release") { "arm64-v8a" } else { "x86_64" }
if ($apkEntries -notmatch "(?m)^lib/$([regex]::Escape($requiredAbi))/libpython3\.12\.so$") {
    throw "APK does not contain the expected $requiredAbi Python runtime."
}

$signature = (& $apksigner verify --verbose --print-certs $source 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0 -or $signature -notmatch "(?m)^Verifies$") {
    throw "APK signature verification failed: $signature"
}
if ($isRelease) {
    # apksigner giữ cùng ý nghĩa nhưng cách viết nhãn/dấu phân cách có thể khác giữa
    # các build-tools. Chỉ chọn đúng dòng certificate SHA-256 rồi chuẩn hoá separator;
    # không lấy public-key digest và không in fingerprint/secret vào log CI.
    $certificateLines = @($signature -split "`r?`n" | Where-Object {
        $_ -match '(?i)certificate' -and $_ -match '(?i)SHA[^0-9]*256' -and $_ -match '(?i)digest'
    })
    $fingerprints = @($certificateLines | ForEach-Object {
        $value = if ($_ -match ':') { ($_ -split ':', 2)[1] } else { $_ }
        $digestMatches = [regex]::Matches(
            $value,
            '(?i)(?<![0-9a-f])(?:[0-9a-f]{2}(?:[:\s-]?)){31}[0-9a-f]{2}(?![0-9a-f])'
        )
        foreach ($digestMatch in $digestMatches) {
            ([regex]::Replace($digestMatch.Value, '[^0-9a-fA-F]', '')).ToLowerInvariant()
        }
    } | Select-Object -Unique)
    if ($fingerprints.Count -ne 1) {
        throw "Release APK signer fingerprint is missing or ambiguous (certificate SHA-256 fields: $($certificateLines.Count))."
    }
    if ($fingerprints[0] -ne $releaseCertificateSha256) {
        throw "Release APK was signed by an unexpected certificate."
    }
}

$artifactDir = Join-Path $repo "artifacts\android"
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
$destination = switch ($Variant) {
    "arm64Release" { Join-Path $artifactDir "AffiliateReport-v$version-arm64.apk" }
    "ciRelease" { Join-Path $artifactDir "AffiliateReport-v$version-x86_64-release.apk" }
    default { Join-Path $artifactDir "AffiliateReport-v$version-x86_64-debug.apk" }
}
Copy-Item -LiteralPath $source -Destination $destination -Force
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
Write-Host "APK=$destination"
Write-Host "SHA256=$hash"
