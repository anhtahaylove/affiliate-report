from pathlib import Path

from tiktok_affiliate_report.version import APP_VERSION


def test_full_installer_preserves_data_and_excludes_portable_release():
    launcher = Path("desktop_launcher.py").read_text(encoding="utf-8")
    installer = Path("packaging/TikTokAffiliateReport.iss").read_text(encoding="utf-8")
    build = Path("packaging/build_installer.ps1").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert 'data_dir = run_dir / "data"' in launcher
    assert "AppId={{E729344A-643D-4B99-98B4-455B79060530}" in installer
    assert 'Name: "{app}\\data"; Flags: uninsneveruninstall' in installer
    assert "[UninstallDelete]" not in installer
    assert ".db" not in installer
    assert "dist\\TikTokAffiliateReport.exe" not in installer + build + readme
    assert "Get-FileHash -Algorithm SHA256 $setupExe" in build
    assert "Get-FileHash -Algorithm SHA256 $appExe, $setupExe" not in build
    assert "$staleMetadata = @($checksumFile, (Join-Path $outputDir 'stable.json'), (Join-Path $outputDir 'stable.json.sig'))" in build
    assert "Remove-Item -LiteralPath $staleMetadata" in build


def test_app_ships_as_onedir_so_first_launch_never_unpacks_to_temp():
    """Bản onefile giải nén runtime ra %TEMP% mỗi lần chạy; ngay sau khi cài, antivirus quét đống
    file vừa rơi xuống và làm hỏng bước nạp python3xx.dll. onedir bỏ hẳn bước giải nén đó."""
    batch = Path("BUILD_EXE.bat").read_text(encoding="utf-8")
    installer = Path("packaging/TikTokAffiliateReport.iss").read_text(encoding="utf-8")
    updater = Path("tiktok_affiliate_report/updater.py").read_text(encoding="utf-8")

    assert "--onedir" in batch
    assert "--onefile" not in batch
    # onedir xuất ra một THƯ MỤC. Cổng riêng tư phải trỏ vào thư mục đó, không phải file .exe —
    # đổi --onedir mà quên dòng này thì build đỏ ngay ở bước cuối, đúng như đã xảy ra ở v1.3.2.
    assert '-Path "%APP_STAGE%\\TikTokAffiliateReport"' in batch
    assert '-Path "%APP_STAGE%\\TikTokAffiliateReport.exe"' not in batch
    # Installer phải chép cả thư mục, và dọn runtime cũ để không sót .dll lệch phiên bản.
    assert 'Source: "..\\build\\installer-app\\TikTokAffiliateReport\\*"' in installer
    assert "recursesubdirs" in installer
    assert 'Type: filesandordirs; Name: "{app}\\_internal"' in installer
    # Dữ liệu người dùng không bao giờ nằm trong diện dọn dẹp.
    assert '{app}\\data' not in installer.split("[InstallDelete]")[1].split("[Files]")[0]
    # Mở lần hai khi lần đầu chưa phản hồi chính là thứ sinh ra hộp thoại "Failed to load Python
    # DLL": hai tiến trình cùng giải nén tranh nhau đĩa và antivirus.
    assert "retrying launch once" not in updater


def test_v124_installer_and_release_workflow_support_verified_auto_update():
    batch = Path("BUILD_EXE.bat").read_text(encoding="utf-8")
    installer = Path("packaging/TikTokAffiliateReport.iss").read_text(encoding="utf-8")
    build = Path("packaging/build_installer.ps1").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    # Phiên bản chỉ được khai ở version.py; mọi nơi khác phải bám theo nó, kể cả README —
    # người dùng đối chiếu tên file setup trong README với file tải về.
    assert f"[string]$AppVersion = '{APP_VERSION}'" in build
    assert f'#define MyAppVersion "{APP_VERSION}"' in installer
    readme = Path("README.md").read_text(encoding="utf-8")
    assert f"TikTokAffiliateReportSetup-v{APP_VERSION}.exe" in readme
    stale = {
        line.strip()
        for line in readme.splitlines()
        if "TikTokAffiliateReportSetup-v" in line and f"v{APP_VERSION}.exe" not in line
    }
    assert not stale, f"README còn nhắc phiên bản cũ: {stale}"
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "pnpm/action-setup@v6" in workflow
    assert "actions/setup-node@v7" in workflow
    assert "--hidden-import tiktok_affiliate_report.updater" in batch
    assert "--hidden-import tiktok_affiliate_report.version" in batch
    assert "--hidden-import pystray._win32" in batch
    assert '--add-data "%CD%\\packaging\\app.ico;packaging"' in batch
    assert 'pystray==0.19.5; sys_platform == "win32"' in Path("requirements-api.txt").read_text(encoding="utf-8")
    assert "TikTokAffiliateReport.SingleInstance" in Path("desktop_launcher.py").read_text(encoding="utf-8")
    assert 'pystray.MenuItem("Thoát ứng dụng"' in Path("desktop_launcher.py").read_text(encoding="utf-8")
    assert "Flags: nowait postinstall skipifsilent" in installer
    assert 'tags:\n      - "v*.*.*"' in workflow
    assert "permissions:\n  actions: read\n  contents: read" in workflow
    assert "windows-installer:\n    needs: verify" in workflow
    assert "windows-installer:\n    needs: verify\n    runs-on: windows-latest\n    permissions:\n      contents: write" in workflow
    assert "POSTGRES_TEST_URL" in workflow
    assert '"artifacts\\installer\\SHA256SUMS.txt"' in workflow
    assert "UPDATE_SIGNING_KEY_B64" in workflow
    assert "UPDATE_FEED_TOKEN" in workflow
    assert "-m scripts.sign_update_feed" in workflow
    assert "anhtahaylove/tiktok-affiliate-report-updates" in workflow
    assert "stable.json.sig" in workflow
    assert "Downloaded release checksum mismatch" in workflow
    assert "gh release create $tag @assets --repo $repo --draft --latest=false" in workflow
    assert "gh release edit $tag --repo $repo --draft=false --prerelease" in workflow
    assert '$public.isDraft -or !$public.isPrerelease -or $public.tagName -ne $tag' in workflow
    assert "gh release edit $tag --repo $repo --prerelease=false --latest" in workflow
    assert "verify_update_manifest_bytes" in workflow
    assert "Public mirror checksum mismatch" in workflow
    assert "Private release $tag is already published" in workflow
    assert "Public release $tag is already published" in workflow
    assert "gh release delete $tag --yes" in workflow
    assert "gh release delete $tag --repo $repo --yes" in workflow
    assert "Anonymous public release assets did not become available or match the build" in workflow
    assert "Live raw feed does not match signed build artifacts" in workflow
    assert 'gh release list --repo $repo --limit 100 --json tagName,isDraft,isLatest,isPrerelease' in workflow
    assert '$env:GH_TOKEN = ""' in workflow
    assert "git revert --no-edit $stableCommit" in workflow
    assert "gh release edit $tag --repo $repo --draft=true" in workflow
    assert workflow.index("gh release create $tag @assets --repo $repo --draft --latest=false") < workflow.index("Promote public stable feed and releases")
    promote = workflow.index("Promote public stable feed and releases")
    anonymous_publish = workflow.index("gh release edit $tag --repo $repo --draft=false", promote)
    anonymous_download = workflow.index('Invoke-WebRequest -UseBasicParsing "https://github.com/$repo/releases/download/$tag/$asset"', promote)
    feed_push = workflow.index("git push", promote)
    raw_download = workflow.index('Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/$repo/main/stable.json?', promote)
    private_publish = workflow.index("gh release edit $tag --draft=false", promote)
    latest = workflow.index("gh release edit $tag --repo $repo --prerelease=false --latest", promote)
    assert anonymous_publish < anonymous_download < feed_push < raw_download < private_publish < latest


def test_all_workflows_have_no_node20_action_versions():
    workflows = "\n".join(path.read_text(encoding="utf-8") for path in Path(".github/workflows").glob("*.yml"))
    for old_action in (
        "actions/checkout@v4",
        "actions/setup-node@v4",
        "actions/setup-python@v5",
        "pnpm/action-setup@v4",
    ):
        assert old_action not in workflows


def test_windows_installer_smoke_is_version_parameterized():
    workflow = Path(".github/workflows/windows-installer-smoke.yml").read_text(encoding="utf-8")
    smoke = Path("scripts/ci/windows_installer_smoke.ps1").read_text(encoding="utf-8")
    combined = workflow + smoke

    for old_token in ("V120", "V111", "fresh-install-v120", "upgrade-v111-to-v120"):
        assert old_token not in combined
    assert "'1.2.0' =" not in smoke
    assert "'1.1.1' =" not in smoke

    for parameter in (
        "CurrentInstaller",
        "CurrentVersion",
        "CurrentChecksumFile",
        "PreviousInstaller",
        "PreviousVersion",
        "PreviousChecksumFile",
    ):
        assert f"[string]${parameter}" in smoke

    assert "Assert-Installer $CurrentInstaller $CurrentVersion $CurrentChecksumFile" in smoke
    assert "Assert-Installer $PreviousInstaller $PreviousVersion $PreviousChecksumFile" in smoke
    assert 'TikTokAffiliateReportSetup-v$Version.exe' in smoke
    assert "Get-Content -LiteralPath $ChecksumFile" in smoke
    assert "Get-FileHash -LiteralPath $Path -Algorithm SHA256" in smoke
    assert "'/settings/preferences'" in smoke
    assert "Assert-Routes $baseUrl -IncludePreferences" in smoke
    assert "'/settings/data'" in smoke
    assert "PreviousVersion must be lower than CurrentVersion" in smoke

    assert "workflow_dispatch:" in workflow
    assert "current_version:" in workflow
    assert f'default: "{APP_VERSION}"' in workflow
    assert "previous_version:" in workflow
    assert APP_VERSION == "2.0.6"
    assert 'default: "2.0.5"' in workflow
    assert "fresh-install:" in workflow
    assert "upgrade-install:" in workflow
    assert "if: github.event_name == 'workflow_dispatch'" in workflow
    assert "TikTokAffiliateReportSetup-v$currentVersion.exe" in workflow
    assert "TikTokAffiliateReportSetup-v$previousVersion.exe" in workflow
    assert "SHA256SUMS-current.txt" in workflow
    assert "SHA256SUMS-previous.txt" in workflow
    assert "-CurrentVersion $currentVersion" in workflow
    assert "-PreviousVersion $previousVersion" in workflow
    assert "Invalid current_version" in workflow
    assert "Invalid previous_version" in workflow
    assert "previous_version must be lower than current_version" in workflow
    assert "CURRENT_VERSION: ${{ inputs.current_version }}" in workflow
    assert "PREVIOUS_VERSION: ${{ inputs.previous_version }}" in workflow
    assert '$currentVersion = $env:CURRENT_VERSION' in workflow
    assert '$previousVersion = $env:PREVIOUS_VERSION' in workflow
    assert '"${{ inputs.current_version }}"' not in workflow
    assert '"${{ inputs.previous_version }}"' not in workflow
    assert "python -m pip install pytest" in workflow
    assert "python -m pip install -r requirements.txt" not in workflow
    assert "Smoke account was not preserved during upgrade." in smoke
    assert "daily_target_commission" in smoke
    assert "@{ target_commission = $Value }" not in smoke
    assert "v$PreviousVersion legacy account is missing" not in smoke


def test_v206_release_candidate_and_public_updater_ui_workflows_are_fail_closed():
    candidate = Path(".github/workflows/windows-installer-smoke.yml").read_text(encoding="utf-8")
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    updater_ui = Path(".github/workflows/windows-updater-ui-smoke.yml").read_text(encoding="utf-8")
    updater_smoke = Path("scripts/ci/windows_updater_ui_smoke.ps1").read_text(encoding="utf-8")
    browser_smoke = Path("web/scripts/windows-updater-ui-smoke.mjs").read_text(encoding="utf-8")

    assert "pull_request:" in candidate
    assert "push:" in candidate
    assert "branches: [main]" in candidate
    for runtime_path in (
        '"tiktok_affiliate_report/**"',
        '"web/**"',
        '"packaging/**"',
        '"scripts/**"',
        '"requirements*.txt"',
        '"web/pnpm-lock.yaml"',
        '"BUILD_EXE.bat"',
        '"CHANGELOG.md"',
    ):
        assert runtime_path in candidate
    assert "github.event.pull_request.head.repo.full_name" in candidate
    assert "Fork pull requests cannot run installer candidates" in candidate
    assert "pull_request_target" not in candidate
    assert "workflow_run" not in candidate
    assert "UPDATE_SIGNING_KEY_B64" not in candidate
    assert "UPDATE_FEED_TOKEN" not in candidate
    assert "EXPECTED_SHA: ${{ github.sha }}" in candidate
    assert "$actualSha = git rev-parse HEAD" in candidate
    assert "Candidate checkout does not match PR merge SHA" in candidate
    assert "actions/upload-artifact@v7" in candidate
    assert "actions/download-artifact@v8" in candidate
    assert "retention-days: 3" in candidate
    assert "candidate-release-gate:" in candidate
    assert "github.event_name == 'push'" in candidate
    assert candidate.count("if: always() && needs.candidate-build.result == 'success'") == 2
    assert "scripts\\ci\\windows_installer_smoke.ps1 -Mode Fresh" in candidate
    assert "scripts\\ci\\windows_installer_smoke.ps1 -Mode Upgrade" in candidate
    assert '"- Upgrade $previousVersion -> ${currentVersion}: PASS"' in candidate
    assert "$currentVersion: PASS" not in candidate
    assert "Run exact-head Windows updater helper runtime tests" in candidate
    assert "tests/test_updater.py tests/test_updater_diagnostics.py" in candidate
    assert "TikTokAffiliateReportSetup-v*.exe" in candidate
    assert "SHA256SUMS.txt" in candidate
    assert "stable.json" not in candidate
    assert ".db" not in candidate

    assert "actions: read" in release
    assert "Require successful installer smoke for this exact main commit" in release
    assert "head_sha=$RELEASE_SHA&event=push&status=completed" in release
    assert 'select(.head_branch == "main" and .conclusion == "success")' in release
    assert "has no successful post-merge Windows installer smoke on main" in release

    assert "workflow_dispatch:" in updater_ui
    assert "pull_request:" not in updater_ui
    assert "permissions:\n  contents: read" in updater_ui
    assert 'default: "2.0.6"' in updater_ui
    assert 'default: "2.0.5"' in updater_ui
    assert "UPDATE_SIGNING_KEY_B64" not in updater_ui
    assert "UPDATE_FEED_TOKEN" not in updater_ui
    assert "actions/upload-artifact@v7" in updater_ui
    assert "pnpm --dir web exec playwright install chromium" in updater_ui
    assert "windows_updater_ui_smoke.ps1" in updater_ui

    assert "This destructive updater UI smoke only runs on an ephemeral GitHub Actions runner." in updater_smoke
    assert "Assert-Installer $CurrentInstaller $CurrentVersion $CurrentChecksumFile" in updater_smoke
    assert "Install-App $PreviousInstaller" in updater_smoke
    assert "Install-App $CurrentInstaller" not in updater_smoke
    assert "UPDATER_SMOKE" in updater_smoke
    assert "pnpm --dir web exec node scripts/windows-updater-ui-smoke.mjs" in updater_smoke
    assert "Export-ScrubbedUpdaterDiagnostics" in updater_smoke
    assert "update-status.json" in updater_smoke
    assert "updater-bootstrap.log" in updater_smoke
    assert "installer.log" in updater_smoke
    assert "[install dir]" in updater_smoke
    assert "[workspace]" in updater_smoke
    assert "[user profile]" in updater_smoke

    assert 'getByRole("button", { name: "Kiểm tra lại" })' in browser_smoke
    assert 'getByRole("button", { name: `Cài bản ${currentVersion}` })' in browser_smoke
    assert 'getByRole("button", { name: "Cài bản cập nhật" })' in browser_smoke
    assert 'phase !== "installed"' in browser_smoke
    assert "observeUpdaterTransition" in browser_smoke
    assert 'progress.phase === "failed"' in browser_smoke
    assert "Updater never produced an observable application disconnect." in browser_smoke
    assert "disconnect_observed: true" in browser_smoke
    assert "disconnected_at" in browser_smoke
    assert "recovered_at" in browser_smoke
    assert "UPDATER_SMOKE" in browser_smoke
    assert "screenshot" in browser_smoke


def test_settings_data_page_is_not_ignored():
    ignored = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/data/" in ignored
    assert "data/" not in ignored
    assert Path("web/src/app/settings/data/page.tsx").is_file()
