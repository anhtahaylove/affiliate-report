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


def test_v124_installer_and_release_workflow_support_verified_auto_update():
    batch = Path("BUILD_EXE.bat").read_text(encoding="utf-8")
    installer = Path("packaging/TikTokAffiliateReport.iss").read_text(encoding="utf-8")
    build = Path("packaging/build_installer.ps1").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert APP_VERSION == "1.2.13"
    assert "[string]$AppVersion = '1.2.13'" in build
    assert '#define MyAppVersion "1.2.13"' in installer
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
    assert "permissions:\n  contents: read" in workflow
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
    assert "'/settings/data'" in smoke
    assert "PreviousVersion must be lower than CurrentVersion" in smoke

    assert "workflow_dispatch:" in workflow
    assert "current_version:" in workflow
    assert 'default: "1.2.13"' in workflow
    assert "previous_version:" in workflow
    assert 'default: "1.2.12"' in workflow
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
    assert "v$PreviousVersion legacy account is missing" not in smoke


def test_settings_data_page_is_not_ignored():
    ignored = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/data/" in ignored
    assert "data/" not in ignored
    assert Path("web/src/app/settings/data/page.tsx").is_file()
