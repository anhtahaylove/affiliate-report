[CmdletBinding()]
param(
    [string]$SdkRoot,
    [switch]$ForceRecreate,
    [switch]$PersistUserEnvironment
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedSdkRoot = if ($SdkRoot) {
    [System.IO.Path]::GetFullPath($SdkRoot)
} elseif ($env:ANDROID_SDK_ROOT) {
    [System.IO.Path]::GetFullPath($env:ANDROID_SDK_ROOT)
} elseif ($env:ANDROID_HOME) {
    [System.IO.Path]::GetFullPath($env:ANDROID_HOME)
} else {
    Join-Path $env:LOCALAPPDATA "Android\Sdk"
}
$sdkManager = Join-Path $resolvedSdkRoot "cmdline-tools\latest\bin\sdkmanager.bat"
$avdManager = Join-Path $resolvedSdkRoot "cmdline-tools\latest\bin\avdmanager.bat"
$emulator = Join-Path $resolvedSdkRoot "emulator\emulator.exe"

if (-not (Test-Path -LiteralPath $sdkManager -PathType Leaf)) {
    throw "Android SDK Command-line Tools are missing: $sdkManager"
}

$env:ANDROID_HOME = $resolvedSdkRoot
$env:ANDROID_SDK_ROOT = $resolvedSdkRoot
if ($PersistUserEnvironment) {
    [Environment]::SetEnvironmentVariable("ANDROID_HOME", $resolvedSdkRoot, "User")
    [Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $resolvedSdkRoot, "User")
}

$androidPathItems = @(
    (Join-Path $resolvedSdkRoot "platform-tools"),
    (Join-Path $resolvedSdkRoot "emulator"),
    (Join-Path $resolvedSdkRoot "cmdline-tools\latest\bin")
)
$env:Path = ($androidPathItems -join ";") + ";" + $env:Path
if ($PersistUserEnvironment) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $userPathItems = @($userPath -split ";" | Where-Object { $_ })
    foreach ($pathItem in $androidPathItems) {
        if ($userPathItems -notcontains $pathItem) {
            $userPathItems += $pathItem
        }
    }
    [Environment]::SetEnvironmentVariable("Path", ($userPathItems -join ";"), "User")
}

$packages = @(
    "emulator",
    "platform-tools",
    "platforms;android-24",
    "platforms;android-36",
    "build-tools;36.0.0",
    "system-images;android-24;google_apis;x86_64",
    "system-images;android-36;google_apis;x86_64"
)

Write-Output "[INFO] Accepting Android SDK licenses."
1..40 | ForEach-Object { "y" } | & $sdkManager --licenses | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Android SDK license acceptance failed with exit code $LASTEXITCODE."
}

Write-Output "[INFO] Installing required Android SDK packages."
& $sdkManager --install @packages
if ($LASTEXITCODE -ne 0) {
    throw "Android SDK package installation failed with exit code $LASTEXITCODE."
}
if (-not (Test-Path -LiteralPath $emulator -PathType Leaf)) {
    throw "Android Emulator was not installed: $emulator"
}

$previousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $rawAcceleration = @(& $emulator -accel-check 2>&1)
    $accelerationExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
$acceleration = ($rawAcceleration | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
Write-Output $acceleration
if ($accelerationExitCode -ne 0 -or $acceleration -notmatch "installed and usable") {
    throw "Android Emulator hardware acceleration is unavailable. Enable Windows Hypervisor Platform and virtualization."
}

$avds = @(
    [pscustomobject]@{
        Name = "AffiliateReport_API24"
        Package = "system-images;android-24;google_apis;x86_64"
    },
    [pscustomobject]@{
        Name = "AffiliateReport_API36"
        Package = "system-images;android-36;google_apis;x86_64"
    }
)

$existing = @(& $emulator -list-avds)
foreach ($avd in $avds) {
    if ($ForceRecreate -and ($existing -contains $avd.Name)) {
        Write-Output "[INFO] Deleting AVD $($avd.Name)."
        & $avdManager delete avd --name $avd.Name | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to delete AVD $($avd.Name)."
        }
        $existing = @($existing | Where-Object { $_ -ne $avd.Name })
    }

    if ($existing -contains $avd.Name) {
        Write-Output "[SKIP] AVD already exists: $($avd.Name)"
        continue
    }

    Write-Output "[INFO] Creating AVD $($avd.Name)."
    "no" | & $avdManager create avd --name $avd.Name --package $avd.Package --device "pixel_2" --force | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create AVD $($avd.Name)."
    }
}

$finalAvds = @(& $emulator -list-avds)
foreach ($avd in $avds) {
    if ($finalAvds -notcontains $avd.Name) {
        throw "Expected AVD is missing after setup: $($avd.Name)"
    }
}

Write-Output "[OK] Android Emulator setup is ready."
$avds | Select-Object Name, Package | Format-Table -AutoSize
