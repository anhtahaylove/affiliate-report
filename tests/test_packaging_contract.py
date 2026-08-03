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


def test_v120_installer_and_release_workflow_support_verified_auto_update():
    batch = Path("BUILD_EXE.bat").read_text(encoding="utf-8")
    installer = Path("packaging/TikTokAffiliateReport.iss").read_text(encoding="utf-8")
    build = Path("packaging/build_installer.ps1").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert APP_VERSION == "1.2.0"
    assert "[string]$AppVersion = '1.2.0'" in build
    assert '#define MyAppVersion "1.2.0"' in installer
    assert "--hidden-import tiktok_affiliate_report.updater" in batch
    assert "--hidden-import tiktok_affiliate_report.version" in batch
    assert "Flags: nowait postinstall skipifsilent" in installer
    assert 'tags:\n      - "v*.*.*"' in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "windows-installer:\n    needs: verify" in workflow
    assert "windows-installer:\n    needs: verify\n    runs-on: windows-latest\n    permissions:\n      contents: write" in workflow
    assert "POSTGRES_TEST_URL" in workflow
    assert '"artifacts\\installer\\SHA256SUMS.txt"' in workflow
    assert "UPDATE_SIGNING_KEY_B64" in workflow
    assert "UPDATE_FEED_TOKEN" in workflow
    assert r"scripts\sign_update_feed.py" in workflow or r"scripts\\sign_update_feed.py" in workflow
    assert "anhtahaylove/tiktok-affiliate-report-updates" in workflow
    assert "stable.json.sig" in workflow
    assert "Downloaded release checksum mismatch" in workflow
    assert "gh release create $tag @assets --repo $repo --draft --latest=false" in workflow
    assert "verify_update_manifest_bytes" in workflow
    assert "Public mirror checksum mismatch" in workflow
    assert "gh release delete $tag --yes" in workflow
    assert "gh release delete $tag --repo $repo --yes" in workflow
    assert "Live raw feed does not match release feed assets" in workflow
    assert "git revert --no-edit HEAD" in workflow
    assert workflow.index("gh release create $tag @assets --repo $repo --draft --latest=false") < workflow.index("Promote public stable feed and releases")
    assert workflow.index("Invoke-WebRequest -UseBasicParsing") < workflow.index("gh release edit $tag --repo $repo --draft=false --latest")
    assert workflow.index("gh release edit $tag --draft=false") > workflow.index("Invoke-WebRequest -UseBasicParsing")
