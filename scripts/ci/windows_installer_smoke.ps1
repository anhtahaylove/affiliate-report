param(
    [Parameter(Mandatory)]
    [ValidateSet('Fresh', 'Upgrade', 'Bootstrap')]
    [string]$Mode,
    [Parameter(Mandatory)]
    [string]$CurrentInstaller,
    [Parameter(Mandatory)]
    [string]$CurrentVersion,
    [Parameter(Mandatory)]
    [string]$CurrentChecksumFile,
    [string]$PreviousInstaller,
    [string]$PreviousVersion,
    [string]$PreviousChecksumFile,
    [string]$BootstrapPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:GITHUB_ACTIONS -ne 'true') {
    throw 'This destructive installer smoke script only runs on an ephemeral GitHub Actions runner.'
}

$installDir = Join-Path $env:LOCALAPPDATA 'AffiliateReport'
$appExe = Join-Path $installDir 'AffiliateReport.exe'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{E729344A-643D-4B99-98B4-455B79060530}_is1'
$routes = @('/', '/accounts', '/analytics', '/imports', '/orders', '/targets', '/settings/data', '/settings/update', '/settings/users')

function Assert-Version([string]$Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        throw "Invalid version: $Version"
    }
}

function Assert-Installer([string]$Path, [string]$Version, [string]$ChecksumFile) {
    Assert-Version $Version
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Installer not found: $Path"
    }
    if (!(Test-Path -LiteralPath $ChecksumFile -PathType Leaf)) {
        throw "Checksum file not found: $ChecksumFile"
    }

    $expectedName = "AffiliateReportSetup-v$Version.exe"
    $actualName = Split-Path -Leaf $Path
    if ($actualName -ne $expectedName) {
        throw "Installer filename is $actualName, expected $expectedName"
    }

    $escapedName = [regex]::Escape($expectedName)
    $matches = @(Get-Content -LiteralPath $ChecksumFile | Where-Object { $_ -match "^([A-Fa-f0-9]{64})\s+\*?$escapedName$" })
    if ($matches.Count -ne 1) {
        throw "Checksum file must contain exactly one SHA-256 entry for $expectedName."
    }

    $expected = ([regex]::Match($matches[0], '^([A-Fa-f0-9]{64})').Groups[1].Value).ToUpperInvariant()
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $expected) {
        throw "v$Version installer SHA-256 mismatch: $actual"
    }
}

function Install-App([string]$Path) {
    Write-Host "Installing $(Split-Path -Leaf $Path)..."
    $process = Start-Process -FilePath $Path -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-' -PassThru
    if (!$process.WaitForExit(120000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "Installer timed out after 120 seconds: $Path"
    }
    if ($process.ExitCode -ne 0) {
        throw "Installer exited with code $($process.ExitCode): $Path"
    }
    if (!(Test-Path -LiteralPath $appExe -PathType Leaf)) {
        throw "Installed app not found: $appExe"
    }
}

function Assert-InstalledVersion([string]$Version) {
    $actual = (Get-ItemProperty -LiteralPath $uninstallKey).DisplayVersion
    if ($actual -ne $Version) {
        throw "Installed version is $actual, expected $Version"
    }
}

function Start-App([int]$Port) {
    Write-Host "Starting installed app on port $Port..."
    $env:API_PORT = "$Port"
    try {
        Start-Process -FilePath $appExe -WorkingDirectory $installDir | Out-Null
    } finally {
        Remove-Item Env:\API_PORT -ErrorAction SilentlyContinue
    }

    $baseUrl = "http://127.0.0.1:$Port"
    for ($attempt = 1; $attempt -le 120; $attempt++) {
        try {
            $health = Invoke-RestMethod "$baseUrl/health" -TimeoutSec 2
            if ($health.status -eq 'ok') {
                return $baseUrl
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "App did not become healthy on $baseUrl"
}

function Stop-App {
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        $processes = @(Get-CimInstance Win32_Process -Filter "Name = 'AffiliateReport.exe'" |
            Where-Object { $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($appExe) })
        if ($processes.Count -eq 0) { return }
        $processes | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 500
    }
    throw 'Installed app processes did not stop within 10 seconds.'
}

function Assert-Routes([string]$BaseUrl, [switch]$IncludePreferences) {
    $expectedRoutes = @($routes)
    if ($IncludePreferences) { $expectedRoutes += '/settings/preferences' }
    foreach ($route in $expectedRoutes) {
        $response = Invoke-WebRequest -UseBasicParsing "$BaseUrl$route" -TimeoutSec 10
        if ($response.StatusCode -ne 200 -or $response.Content -notmatch '<html') {
            throw "Static route failed: $route"
        }
    }
    $meta = Invoke-RestMethod "$BaseUrl/api/v1/meta" -TimeoutSec 10
    if ($null -eq $meta.accounts) {
        throw 'Meta response did not include accounts.'
    }
    return $meta
}

function Set-Target([string]$BaseUrl, [string]$Account, [string]$Month, [int64]$Value) {
    $body = @{ daily_target_commission = $Value } | ConvertTo-Json -Compress
    Invoke-RestMethod "$BaseUrl/api/v1/targets/$Account/$Month" -Method Put -ContentType 'application/json' -Body $body | Out-Null
}

function Assert-Target([string]$BaseUrl, [string]$Account, [string]$Month, [int64]$Value) {
    $targets = Invoke-RestMethod "$BaseUrl/api/v1/targets?account=$Account&month=$Month" -TimeoutSec 10
    $match = @($targets.items | Where-Object { $_.account -eq $Account -and [int64]$_.daily_target_commission -eq $Value })
    if ($match.Count -ne 1) {
        throw "Target marker was not preserved for $Account/$Month."
    }
}

if ((Test-Path -LiteralPath $installDir) -or (Test-Path -LiteralPath $uninstallKey)) {
    throw "Runner is not clean: $installDir already exists."
}

Assert-Installer $CurrentInstaller $CurrentVersion $CurrentChecksumFile
if ($Mode -eq 'Upgrade') {
    foreach ($name in 'PreviousInstaller', 'PreviousVersion', 'PreviousChecksumFile') {
        if (!(Get-Variable -Name $name -ValueOnly)) { throw "$name is required for upgrade smoke." }
    }
    Assert-Installer $PreviousInstaller $PreviousVersion $PreviousChecksumFile
    if ([version]$PreviousVersion -ge [version]$CurrentVersion) {
        throw "PreviousVersion must be lower than CurrentVersion for upgrade smoke."
    }
}
if ($Mode -eq 'Bootstrap') {
    if (!(Test-Path -LiteralPath $BootstrapPath -PathType Leaf)) { throw 'BootstrapPath is required for bootstrap smoke.' }
    $bootstrapName = Split-Path -Leaf $BootstrapPath
    $bootstrapMatch = [regex]::Match($bootstrapName, '^TikTokAffiliateUpdater-v(\d+\.\d+\.\d+)\.ps1$')
    if (!$bootstrapMatch.Success) { throw "Invalid updater bootstrap filename: $bootstrapName" }
    $bootstrapLine = @(Get-Content -LiteralPath $CurrentChecksumFile | Where-Object { $_ -match ([regex]::Escape($bootstrapName) + '$') })
    if ($bootstrapLine.Count -ne 1) { throw 'Bootstrap checksum entry is missing.' }
    $bootstrapExpected = ([regex]::Match($bootstrapLine[0], '^([A-Fa-f0-9]{64})').Groups[1].Value).ToUpperInvariant()
    if ((Get-FileHash -LiteralPath $BootstrapPath -Algorithm SHA256).Hash -ne $bootstrapExpected) { throw 'Bootstrap SHA-256 mismatch.' }
}

try {
    if ($Mode -eq 'Fresh') {
        Install-App $CurrentInstaller
        Assert-InstalledVersion $CurrentVersion
        $baseUrl = Start-App 43120
        $meta = Assert-Routes $baseUrl -IncludePreferences
        if (@($meta.accounts).Count -ne 0) { throw "Fresh v$CurrentVersion unexpectedly seeded accounts." }

        $body = @{ code = 'SMOKE'; display_name = 'Smoke Account'; display_order = 1 } | ConvertTo-Json -Compress
        Invoke-RestMethod "$baseUrl/api/v1/accounts" -Method Post -ContentType 'application/json' -Body $body | Out-Null
        Set-Target $baseUrl 'SMOKE' '2099-12' 123456789
        Assert-Target $baseUrl 'SMOKE' '2099-12' 123456789
        Stop-App

        $baseUrl = Start-App 43121
        $meta = Assert-Routes $baseUrl -IncludePreferences
        if ('SMOKE' -notin @($meta.accounts)) { throw 'Fresh-install data did not persist after restart.' }
        Assert-Target $baseUrl 'SMOKE' '2099-12' 123456789
    } elseif ($Mode -eq 'Upgrade') {
        Install-App $PreviousInstaller
        Assert-InstalledVersion $PreviousVersion
        $baseUrl = Start-App 43122
        $meta = Assert-Routes $baseUrl
        if ('SMOKE' -notin @($meta.accounts)) {
            $body = @{ code = 'SMOKE'; display_name = 'Smoke Account'; display_order = 1 } | ConvertTo-Json -Compress
            Invoke-RestMethod "$baseUrl/api/v1/accounts" -Method Post -ContentType 'application/json' -Body $body | Out-Null
        }
        Set-Target $baseUrl 'SMOKE' '2099-12' 987654321
        Assert-Target $baseUrl 'SMOKE' '2099-12' 987654321
        Stop-App

        Install-App $CurrentInstaller
        Assert-InstalledVersion $CurrentVersion
        $baseUrl = Start-App 43123
        $meta = Assert-Routes $baseUrl -IncludePreferences
        if ('SMOKE' -notin @($meta.accounts)) { throw 'Smoke account was not preserved during upgrade.' }
        Assert-Target $baseUrl 'SMOKE' '2099-12' 987654321
    } else {
        Install-App $CurrentInstaller
        Assert-InstalledVersion $CurrentVersion
        $baseUrl = Start-App 43124
        $body = @{ code = 'SMOKE'; display_name = 'Bootstrap Smoke'; display_order = 1 } | ConvertTo-Json -Compress
        Invoke-RestMethod "$baseUrl/api/v1/accounts" -Method Post -ContentType 'application/json' -Body $body | Out-Null
        Set-Target $baseUrl 'SMOKE' '2099-12' 246813579
        Stop-App

        $dataDir = Join-Path $installDir 'data'
        $runtimeDir = Join-Path $dataDir "updates\v$CurrentVersion-bootstrap-runtime"
        New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
        $statusPath = Join-Path $dataDir 'update-status.json'
        $ackPath = Join-Path $runtimeDir 'bootstrap-ack.json'
        $updaterLog = Join-Path $dataDir 'updater.log'
        $installerLog = Join-Path $runtimeDir 'installer.log'
        $installerHash = (Get-FileHash -LiteralPath $CurrentInstaller -Algorithm SHA256).Hash
        $bootstrapVersion = [regex]::Match((Split-Path -Leaf $BootstrapPath), '^TikTokAffiliateUpdater-v(\d+\.\d+\.\d+)\.ps1$').Groups[1].Value
        $attemptId = 'c' * 32
        $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $arguments = @(
            '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', "`"$BootstrapPath`"",
            '-ParentPid', '2147483647', '-Installer', "`"$CurrentInstaller`"", '-ExpectedSha256', $installerHash,
            '-AppExe', "`"$appExe`"", '-LogPath', "`"$updaterLog`"", '-InstallerLog', "`"$installerLog`"",
            '-StatusPath', "`"$statusPath`"", '-TargetVersion', $CurrentVersion,
            '-InstallerSize', ([string](Get-Item -LiteralPath $CurrentInstaller).Length),
            '-InstanceStatePath', "`"$(Join-Path $dataDir 'instance.json')`"", '-BootstrapProtocol', '1',
            '-BootstrapVersion', $bootstrapVersion, '-AttemptId', $attemptId, '-AckPath', "`"$ackPath`""
        )
        $bootstrapProcess = Start-Process -FilePath $powershell -ArgumentList $arguments -PassThru -WindowStyle Hidden
        if (!$bootstrapProcess.WaitForExit(180000)) {
            Stop-Process -Id $bootstrapProcess.Id -Force -ErrorAction SilentlyContinue
            throw 'Updater bootstrap runtime smoke timed out.'
        }
        if ($bootstrapProcess.ExitCode -ne 0) { throw "Updater bootstrap exited with code $($bootstrapProcess.ExitCode)." }
        $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
        if ($status.phase -ne 'installed' -or $status.target_version -ne $CurrentVersion -or $status.error) { throw 'Updater bootstrap did not reach a clean installed state.' }
        $ack = Get-Content -LiteralPath $ackPath -Raw | ConvertFrom-Json
        if ($ack.attempt_id -ne $attemptId -or $ack.bootstrap_version -ne $bootstrapVersion -or $ack.phase -ne 'ready') { throw 'Updater bootstrap ACK is invalid.' }
        Assert-InstalledVersion $CurrentVersion
        $instance = Get-Content -LiteralPath (Join-Path $dataDir 'instance.json') -Raw | ConvertFrom-Json
        $health = Invoke-RestMethod "$($instance.url)/health" -TimeoutSec 10
        if ($health.status -ne 'ok' -or $health.app_version -ne $CurrentVersion) { throw 'Relaunched target health/version proof failed.' }
        Assert-Target $instance.url 'SMOKE' '2099-12' 246813579
        # Cùng cuộc đua như trong windows_updater_ui_smoke.ps1: chưa cắn ở lane này nhưng cùng
        # một lý do, nên đợi có giới hạn thay vì kiểm một phát.
        $orphanWait = [System.Diagnostics.Stopwatch]::StartNew()
        do {
            $orphans = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine -match 'TikTokAffiliateUpdater-v\d+\.\d+\.\d+\.ps1' })
            if ($orphans.Count -eq 0) { break }
            Start-Sleep -Milliseconds 500
        } while ($orphanWait.ElapsedMilliseconds -lt 30000)
        if ($orphans.Count -ne 0) { throw 'Updater bootstrap process remained after successful runtime smoke.' }
    }

    Write-Host "$Mode installer smoke passed."
} catch {
    $log = Join-Path $installDir 'data\launcher.log'
    if (Test-Path -LiteralPath $log) {
        Write-Host '=== launcher.log ==='
        Get-Content -LiteralPath $log -Tail 200
    }
    throw
} finally {
    Stop-App
}
