param(
    [Parameter(Mandatory)][string]$PreviousInstaller,
    [Parameter(Mandatory)][string]$PreviousVersion,
    [Parameter(Mandatory)][string]$PreviousChecksumFile,
    [Parameter(Mandatory)][string]$CurrentInstaller,
    [Parameter(Mandatory)][string]$CurrentVersion,
    [Parameter(Mandatory)][string]$CurrentChecksumFile,
    [Parameter(Mandatory)][string]$EvidenceDir
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'updater_diagnostics.ps1')

if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'This destructive updater UI smoke only runs on an ephemeral GitHub Actions runner.'
}

$installDir = Join-Path $env:LOCALAPPDATA 'TikTokAffiliateReport'
$appExe = Join-Path $installDir 'TikTokAffiliateReport.exe'
$dataDir = Join-Path $installDir 'data'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{E729344A-643D-4B99-98B4-455B79060530}_is1'
$markerCode = 'UPDATER_SMOKE'
$markerMonth = '2099-11'
$markerValue = 246813579
$baseUrl = 'http://127.0.0.1:43130'

function Assert-Version([string]$Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid version: $Version" }
}

function Assert-Installer([string]$Path, [string]$Version, [string]$ChecksumFile) {
    Assert-Version $Version
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Installer not found for v$Version." }
    if (!(Test-Path -LiteralPath $ChecksumFile -PathType Leaf)) { throw "Checksum file not found for v$Version." }
    $expectedName = "TikTokAffiliateReportSetup-v$Version.exe"
    if ((Split-Path -Leaf $Path) -ne $expectedName) { throw "Installer filename does not match v$Version." }
    $escapedName = [regex]::Escape($expectedName)
    $matches = @(Get-Content -LiteralPath $ChecksumFile | Where-Object { $_ -match "^([A-Fa-f0-9]{64})\s+\*?$escapedName$" })
    if ($matches.Count -ne 1) { throw "Checksum file must contain exactly one entry for v$Version." }
    $expected = ([regex]::Match($matches[0], '^([A-Fa-f0-9]{64})').Groups[1].Value).ToUpperInvariant()
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $expected) { throw "Installer checksum mismatch for v$Version." }
}

function Install-App([string]$Path) {
    $process = Start-Process -FilePath $Path -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-' -PassThru
    if (!$process.WaitForExit(120000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw 'Previous installer timed out.'
    }
    if ($process.ExitCode -ne 0) { throw "Previous installer failed with exit code $($process.ExitCode)." }
    if (!(Test-Path -LiteralPath $appExe -PathType Leaf)) { throw 'Installed application was not found.' }
}

function Assert-InstalledVersion([string]$Version) {
    $actual = (Get-ItemProperty -LiteralPath $uninstallKey).DisplayVersion
    if ($actual -ne $Version) { throw "Installed version is $actual, expected $Version." }
}

function Wait-Health([int]$Attempts = 180) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $health = Invoke-RestMethod "$baseUrl/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { return }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw 'Application did not become healthy after updater reconnect.'
}

function Start-App {
    $env:API_PORT = '43130'
    try {
        Start-Process -FilePath $appExe -WorkingDirectory $installDir | Out-Null
    } finally {
        Remove-Item Env:\API_PORT -ErrorAction SilentlyContinue
    }
    Wait-Health 180
}

function Stop-App {
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        $processes = @(Get-CimInstance Win32_Process -Filter "Name = 'TikTokAffiliateReport.exe'" |
            Where-Object { $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($appExe) })
        if ($processes.Count -eq 0) { return }
        $processes | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 500
    }
    throw 'Installed application processes did not stop.'
}

function ConvertTo-UpdaterPathReplacements {
    $result = @{}
    foreach ($replacement in @(
        @{ Value = $installDir; Label = '[install dir]' },
        @{ Value = $env:GITHUB_WORKSPACE; Label = '[workspace]' },
        @{ Value = $env:RUNNER_TEMP; Label = '[runner temp]' },
        @{ Value = $env:LOCALAPPDATA; Label = '[local app data]' },
        @{ Value = $env:USERPROFILE; Label = '[user profile]' }
    )) {
        if ($replacement.Value) {
            $result[[string]$replacement.Value] = [string]$replacement.Label
        }
    }
    return $result
}

function Export-ScrubbedUpdaterDiagnostics {
    New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
    $updateDir = Join-Path $dataDir "updates\v$CurrentVersion"
    $sources = @(
        @{ Path = (Join-Path $dataDir 'update-status.json'); Name = 'diagnostic-update-status.json' },
        @{ Path = (Join-Path $dataDir 'updater.log'); Name = 'diagnostic-updater.log' },
        @{ Path = (Join-Path $updateDir 'bootstrap-ack.json'); Name = 'diagnostic-bootstrap-ack.json' },
        @{ Path = (Join-Path $updateDir 'updater-bootstrap.log'); Name = 'diagnostic-updater-bootstrap.log' },
        @{ Path = (Join-Path $updateDir 'installer.log'); Name = 'diagnostic-installer.log' },
        @{ Path = (Join-Path $dataDir 'launcher.log'); Name = 'diagnostic-launcher.log' }
    )
    foreach ($source in $sources) {
        if (!(Test-Path -LiteralPath $source.Path -PathType Leaf)) { continue }
        try {
            $content = Get-Content -LiteralPath $source.Path -Raw -ErrorAction Stop
            if ($content.Length -gt 65536) { $content = $content.Substring($content.Length - 65536) }
            $scrubbed = ConvertTo-ScrubbedUpdaterText -Text $content -PathReplacements (ConvertTo-UpdaterPathReplacements)
            Set-Content -LiteralPath (Join-Path $EvidenceDir $source.Name) -Value $scrubbed -Encoding utf8
        } catch {
            Set-Content -LiteralPath (Join-Path $EvidenceDir ($source.Name + '.unavailable.txt')) -Value 'Diagnostic file could not be read.' -Encoding utf8
        }
    }
}

function Set-Marker {
    $meta = Invoke-RestMethod "$baseUrl/api/v1/meta" -TimeoutSec 10
    if ($markerCode -notin @($meta.accounts)) {
        $body = @{ code = $markerCode; display_name = 'Updater Smoke'; display_order = 1 } | ConvertTo-Json -Compress
        Invoke-RestMethod "$baseUrl/api/v1/accounts" -Method Post -ContentType 'application/json' -Body $body | Out-Null
    }
    $target = @{ daily_target_commission = $markerValue } | ConvertTo-Json -Compress
    Invoke-RestMethod "$baseUrl/api/v1/targets/$markerCode/$markerMonth" -Method Put -ContentType 'application/json' -Body $target | Out-Null
}

Assert-Installer $PreviousInstaller $PreviousVersion $PreviousChecksumFile
Assert-Installer $CurrentInstaller $CurrentVersion $CurrentChecksumFile
if ([version]$PreviousVersion -ge [version]$CurrentVersion) {
    throw 'PreviousVersion must be lower than CurrentVersion for updater UI smoke.'
}
if ((Test-Path -LiteralPath $installDir) -or (Test-Path -LiteralPath $uninstallKey)) {
    throw 'Ephemeral runner is not clean.'
}

New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null

try {
    Install-App $PreviousInstaller
    Assert-InstalledVersion $PreviousVersion
    Start-App
    Set-Marker

    $env:UPDATER_BASE_URL = $baseUrl
    $env:PREVIOUS_VERSION = $PreviousVersion
    $env:CURRENT_VERSION = $CurrentVersion
    $env:UPDATER_EVIDENCE_DIR = (Resolve-Path -LiteralPath $EvidenceDir).Path
    & pnpm --dir web exec node scripts/windows-updater-ui-smoke.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Playwright updater UI smoke failed.' }

    Wait-Health 180
    Assert-InstalledVersion $CurrentVersion
    $meta = Invoke-RestMethod "$baseUrl/api/v1/meta" -TimeoutSec 10
    if ($meta.app_version -ne $CurrentVersion) { throw 'Runtime version did not change after updater reconnect.' }
    if ($markerCode -notin @($meta.accounts)) { throw 'Marker account was not preserved by updater.' }
    $targets = Invoke-RestMethod "$baseUrl/api/v1/targets?account=$markerCode&month=$markerMonth" -TimeoutSec 10
    $marker = @($targets.items | Where-Object { $_.account -eq $markerCode -and [int64]$_.daily_target_commission -eq $markerValue })
    if ($marker.Count -ne 1) { throw 'Marker target was not preserved by updater.' }
    $progress = Invoke-RestMethod "$baseUrl/api/v1/admin/update/progress" -TimeoutSec 10
    if ($progress.phase -ne 'installed' -or $progress.current_version -ne $CurrentVersion -or $progress.error) {
        throw 'Updater did not reach a clean installed state.'
    }
    # Bootstrap ghi trạng thái 'installed' RỒI mới thoát, nên kiểm ngay tại thời điểm ứng dụng
    # báo installed là kiểm một cuộc đua vừa tự tạo ra: tiến trình gần như chắc chắn còn sống
    # thêm một nhịp. Quan sát thật: gate 2.0.7 -> 2.0.9 hỏng 1/5 đúng ở đây, dù bản cập nhật đã
    # cài xong, đúng phiên bản và dữ liệu marker còn nguyên. Đợi có giới hạn — bootstrap treo
    # hẳn vẫn là lỗi thật và vẫn bị bắt.
    $orphanWait = [System.Diagnostics.Stopwatch]::StartNew()
    do {
        $orphanBootstraps = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
            Where-Object { $_.CommandLine -and $_.CommandLine -match 'TikTokAffiliateUpdater-v\d+\.\d+\.\d+\.ps1' })
        if ($orphanBootstraps.Count -eq 0) { break }
        Start-Sleep -Milliseconds 500
    } while ($orphanWait.ElapsedMilliseconds -lt 30000)
    if ($orphanBootstraps.Count -ne 0) { throw 'Updater bootstrap process was not cleaned up within 30s.' }

    @"
## Public updater UI smoke
- Upgrade: $PreviousVersion -> $CurrentVersion
- UI flow: PASS
- Reconnect: PASS
- Marker persistence: PASS
- Final phase: installed
"@ >> $env:GITHUB_STEP_SUMMARY
} finally {
    Export-ScrubbedUpdaterDiagnostics
    Remove-Item Env:\UPDATER_BASE_URL, Env:\PREVIOUS_VERSION, Env:\CURRENT_VERSION, Env:\UPDATER_EVIDENCE_DIR -ErrorAction SilentlyContinue
    Stop-App
}
