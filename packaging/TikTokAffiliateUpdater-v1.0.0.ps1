param(
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][string]$AppExe,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [Parameter(Mandatory=$true)][string]$InstallerLog,
    [Parameter(Mandatory=$true)][string]$StatusPath,
    [Parameter(Mandatory=$true)][string]$TargetVersion,
    [Parameter(Mandatory=$true)][int64]$InstallerSize,
    [Parameter(Mandatory=$true)][string]$InstanceStatePath,
    [Parameter(Mandatory=$true)][int]$BootstrapProtocol,
    [Parameter(Mandatory=$true)][string]$BootstrapVersion,
    [Parameter(Mandatory=$true)][string]$AttemptId,
    [Parameter(Mandatory=$true)][string]$AckPath
)
$ErrorActionPreference = 'Stop'
if ($BootstrapProtocol -ne 1) { throw 'Unsupported updater bootstrap protocol.' }
$bootstrapNameMatch = [System.Text.RegularExpressions.Regex]::Match([System.IO.Path]::GetFileName($PSCommandPath), '^TikTokAffiliateUpdater-v(\d+\.\d+\.\d+)\.ps1$')
if (-not $bootstrapNameMatch.Success -or $bootstrapNameMatch.Groups[1].Value -ne $BootstrapVersion) { throw 'Updater bootstrap version does not match its signed filename.' }
if ($AttemptId -notmatch '^[A-Fa-f0-9]{32}$') { throw 'Invalid updater attempt id.' }
$Utf8 = [System.Text.UTF8Encoding]::new($false)
function Ensure-Directory([string]$FilePath) {
    $directory = [System.IO.Path]::GetDirectoryName($FilePath)
    if ($directory) { [System.IO.Directory]::CreateDirectory($directory) > $null }
}
function Write-UpdateLog([string]$Message) {
    Ensure-Directory $LogPath
    [System.IO.File]::AppendAllText($LogPath, ([System.DateTimeOffset]::UtcNow.ToString('o') + ' ' + $Message + [System.Environment]::NewLine), $Utf8)
}
function Write-AtomicJson([string]$FilePath, $Value) {
    Ensure-Directory $FilePath
    $json = ConvertTo-Json -InputObject $Value -Compress
    $tmp = $FilePath + '.' + $PID + '.tmp'
    [System.IO.File]::WriteAllText($tmp, $json + [System.Environment]::NewLine, $Utf8)
    if ([System.IO.File]::Exists($FilePath)) {
        $backup = $FilePath + '.' + $PID + '.bak'
        try {
            if ([System.IO.File]::Exists($backup)) { [System.IO.File]::Delete($backup) }
            [System.IO.File]::Replace($tmp, $FilePath, $backup, $true)
        } finally {
            try { if ([System.IO.File]::Exists($backup)) { [System.IO.File]::Delete($backup) } } catch {}
        }
    } else {
        [System.IO.File]::Move($tmp, $FilePath)
    }
}
function Write-UpdateStatus([string]$Phase, [string]$ErrorText) {
    Write-AtomicJson $StatusPath ([ordered]@{
        bytes_downloaded = $InstallerSize
        bytes_total = $InstallerSize
        error = $(if ($ErrorText) { $ErrorText } else { $null })
        phase = $Phase
        schema = 'tiktok-affiliate-report.update-status.v1'
        target_version = $TargetVersion
        updated_at = [System.DateTimeOffset]::UtcNow.ToString('o')
    })
}
function Write-BootstrapAck {
    Write-AtomicJson $AckPath ([ordered]@{
        attempt_id = $AttemptId
        bootstrap_version = $BootstrapVersion
        phase = 'ready'
        protocol = $BootstrapProtocol
        schema = 'tiktok-affiliate-report.update-bootstrap-ack.v1'
        target_version = $TargetVersion
        updated_at = [System.DateTimeOffset]::UtcNow.ToString('o')
    })
}
function Get-Sha256Hex([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToUpperInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}
function Start-Child([string]$FilePath, [string]$Arguments, [string]$WorkingDirectory, [bool]$Wait) {
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $process = [System.Diagnostics.Process]::Start($psi)
    if ($Wait) { $process.WaitForExit(); return $process.ExitCode }
    return 0
}
function Wait-FileUnlocked([string]$Path, [int]$TimeoutMs) {
    # $ParentPid is only the PyInstaller onefile *child* process. Its bootloader parent keeps
    # $AppExe open a little longer while it unpacks/cleans up its _MEI temp directory, so
    # WaitForExit($ParentPid) alone can return before the file is actually unlocked. If the
    # installer's /CLOSEAPPLICATIONS still finds it in use it defaults to Abort (exit code 5)
    # instead of prompting, since Setup runs /SUPPRESSMSGBOXES. Poll the file handle itself
    # (deliberately not enumerating processes — see forbidden cmdlets in test_updater.py) so we
    # cover any lingering process, not just the one PID we happen to know about.
    $deadline = [System.Diagnostics.Stopwatch]::StartNew()
    while ($deadline.ElapsedMilliseconds -lt $TimeoutMs) {
        if (-not [System.IO.File]::Exists($Path)) { return $true }
        try {
            $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            $stream.Close()
            return $true
        } catch [System.IO.IOException] {
            Start-Sleep -Milliseconds 200
        }
    }
    return $false
}
function Test-Health([string]$Url, [string]$ExpectedVersion) {
    try {
        $client = [System.Net.WebClient]::new()
        try {
            $health = $client.DownloadString($Url + '/health') | ConvertFrom-Json
            return $health.status -eq 'ok' -and $health.app_version -eq $ExpectedVersion
        } finally { $client.Dispose() }
    } catch {
        return $false
    }
}
function Wait-AppHealthy([string]$StatePath, [string]$ExpectedVersion, [int]$TimeoutMs) {
    # The relaunched app writes instance.json after the single-instance and tray startup gates.
    # Poll for both the exact target version and a real /health response instead of treating a
    # successful process launch as proof that the updated app is usable.
    $deadline = [System.Diagnostics.Stopwatch]::StartNew()
    while ($deadline.ElapsedMilliseconds -lt $TimeoutMs) {
        if ([System.IO.File]::Exists($StatePath)) {
            try {
                $raw = [System.IO.File]::ReadAllText($StatePath)
                $urlMatch = [System.Text.RegularExpressions.Regex]::Match($raw, '"url"\s*:\s*"([^"]+)"')
                $versionMatch = [System.Text.RegularExpressions.Regex]::Match($raw, '"app_version"\s*:\s*"([^"]+)"')
                if ($urlMatch.Success -and $versionMatch.Success -and $versionMatch.Groups[1].Value -eq $ExpectedVersion -and (Test-Health $urlMatch.Groups[1].Value $ExpectedVersion)) { return $true }
            } catch {}
        }
        Start-Sleep -Milliseconds 400
    }
    return $false
}
$parentExited = $false
$appLaunchAttempted = $false
try {
    Write-UpdateLog 'Updater bootstrap protocol 1 started.'
    Write-UpdateStatus 'waiting_for_exit' $null
    Write-BootstrapAck
    try {
        $parent = [System.Diagnostics.Process]::GetProcessById($ParentPid)
        if (-not $parent.WaitForExit(120000)) { throw 'Timed out waiting for app to exit.' }
    } catch [System.ArgumentException] {
    }
    $parentExited = $true
    if (-not (Wait-FileUnlocked $AppExe 15000)) {
        Write-UpdateLog 'Warning: app executable still locked 15s after process exit; proceeding anyway.'
    }
    Write-UpdateStatus 'installing' $null
    if (([System.IO.FileInfo]::new($Installer)).Length -ne $InstallerSize) { throw 'Installer size changed after download.' }
    $actual = Get-Sha256Hex $Installer
    if ($actual -ne $ExpectedSha256) { throw 'Installer SHA-256 changed after download.' }
    $arguments = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LOG="' + $InstallerLog + '"'
    $exitCode = Start-Child $Installer $arguments ([System.IO.Path]::GetDirectoryName($Installer)) $true
    if ($exitCode -ne 0) { throw "Installer exited with code $exitCode." }
    Write-UpdateStatus 'restarting' $null
    Start-Child $AppExe '--updated' ([System.IO.Path]::GetDirectoryName($AppExe)) $false > $null
    $appLaunchAttempted = $true
    # Antivirus có thể làm lần mở đầu chậm. Không mở lần thứ hai khi chờ quá hạn vì một tiến trình
    # đang khởi động phải là nguồn sự thật duy nhất cho reconnect.
    if (-not (Wait-AppHealthy $InstanceStatePath $TargetVersion 90000)) {
        throw 'Target app did not report the expected version and healthy state within 90s.'
    }
    Write-UpdateStatus 'installed' $null
    Write-UpdateLog 'Update installed successfully.'
} catch {
    $failure = $_.Exception.Message
    try {
        if ($failure -eq 'Target app did not report the expected version and healthy state within 90s.') {
            # Giữ trạng thái ở reconnecting. Nếu target mở chậm hoặc người dùng mở thủ công,
            # chính API target sẽ chuẩn hóa trạng thái này thành installed.
            Write-UpdateStatus 'restarting' $failure
        } else {
            Write-UpdateStatus 'failed' $failure
        }
    } catch {}
    try { Write-UpdateLog ('Update failed: ' + $failure) } catch {}
    if ($parentExited -and -not $appLaunchAttempted -and [System.IO.File]::Exists($AppExe)) {
        try {
            Start-Child $AppExe '' ([System.IO.Path]::GetDirectoryName($AppExe)) $false > $null
            Write-UpdateLog 'App restarted after a pre-launch update failure.'
        } catch {
            Write-UpdateLog ('App restart failed: ' + $_.Exception.Message)
        }
    }
}
