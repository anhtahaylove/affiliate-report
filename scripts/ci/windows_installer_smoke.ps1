param(
    [Parameter(Mandatory)]
    [ValidateSet('Fresh', 'Upgrade')]
    [string]$Mode,
    [Parameter(Mandatory)]
    [string]$V120Installer,
    [string]$V111Installer
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:GITHUB_ACTIONS -ne 'true') {
    throw 'This destructive installer smoke script only runs on an ephemeral GitHub Actions runner.'
}

$installDir = Join-Path $env:LOCALAPPDATA 'TikTokAffiliateReport'
$appExe = Join-Path $installDir 'TikTokAffiliateReport.exe'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{E729344A-643D-4B99-98B4-455B79060530}_is1'
$expectedHashes = @{
    '1.1.1' = '26B4E0901E696652FDD687CBE01405407CE3816ED761F104AF8A8ED436DC8557'
    '1.2.0' = 'D822B9A74333A45A1979A58F42DC5CD24E86361ADD3BCDFA78C4B48518900406'
}
$routes = @('/', '/accounts', '/analytics', '/imports', '/orders', '/targets', '/settings/data', '/settings/update', '/settings/users')

function Assert-Installer([string]$Path, [string]$Version) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Installer not found: $Path"
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $expectedHashes[$Version]) {
        throw "v$Version installer SHA-256 mismatch: $actual"
    }
}

function Install-App([string]$Path) {
    $process = Start-Process -FilePath $Path -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-' -Wait -PassThru
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
    Get-CimInstance Win32_Process -Filter "Name = 'TikTokAffiliateReport.exe'" |
        Where-Object { $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($appExe) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

function Assert-Routes([string]$BaseUrl) {
    foreach ($route in $routes) {
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
    $body = @{ target_commission = $Value } | ConvertTo-Json -Compress
    Invoke-RestMethod "$BaseUrl/api/v1/targets/$Account/$Month" -Method Put -ContentType 'application/json' -Body $body | Out-Null
}

function Assert-Target([string]$BaseUrl, [string]$Account, [string]$Month, [int64]$Value) {
    $targets = Invoke-RestMethod "$BaseUrl/api/v1/targets?account=$Account&month=$Month" -TimeoutSec 10
    $match = @($targets.items | Where-Object { $_.account -eq $Account -and [int64]$_.target_commission -eq $Value })
    if ($match.Count -ne 1) {
        throw "Target marker was not preserved for $Account/$Month."
    }
}

if ((Test-Path -LiteralPath $installDir) -or (Test-Path -LiteralPath $uninstallKey)) {
    throw "Runner is not clean: $installDir already exists."
}

Assert-Installer $V120Installer '1.2.0'
if ($Mode -eq 'Upgrade') {
    if (!$V111Installer) { throw 'V111Installer is required for upgrade smoke.' }
    Assert-Installer $V111Installer '1.1.1'
}

try {
    if ($Mode -eq 'Fresh') {
        Install-App $V120Installer
        Assert-InstalledVersion '1.2.0'
        $baseUrl = Start-App 43120
        $meta = Assert-Routes $baseUrl
        if (@($meta.accounts).Count -ne 0) { throw 'Fresh v1.2.0 unexpectedly seeded accounts.' }

        $body = @{ code = 'SMOKE'; display_name = 'Smoke Account'; display_order = 1 } | ConvertTo-Json -Compress
        Invoke-RestMethod "$baseUrl/api/v1/accounts" -Method Post -ContentType 'application/json' -Body $body | Out-Null
        Set-Target $baseUrl 'SMOKE' '2099-12' 123456789
        Assert-Target $baseUrl 'SMOKE' '2099-12' 123456789
        Stop-App

        $baseUrl = Start-App 43121
        $meta = Assert-Routes $baseUrl
        if ('SMOKE' -notin @($meta.accounts)) { throw 'Fresh-install data did not persist after restart.' }
        Assert-Target $baseUrl 'SMOKE' '2099-12' 123456789
    } else {
        Install-App $V111Installer
        Assert-InstalledVersion '1.1.1'
        $baseUrl = Start-App 43122
        $meta = Invoke-RestMethod "$baseUrl/api/v1/meta" -TimeoutSec 10
        if ('CHIISTORE' -notin @($meta.accounts)) { throw 'v1.1.1 legacy account is missing.' }
        Set-Target $baseUrl 'CHIISTORE' '2099-12' 987654321
        Assert-Target $baseUrl 'CHIISTORE' '2099-12' 987654321
        Stop-App

        Install-App $V120Installer
        Assert-InstalledVersion '1.2.0'
        $baseUrl = Start-App 43123
        $meta = Assert-Routes $baseUrl
        if ('CHIISTORE' -notin @($meta.accounts)) { throw 'Legacy account was not migrated during upgrade.' }
        Assert-Target $baseUrl 'CHIISTORE' '2099-12' 987654321
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
