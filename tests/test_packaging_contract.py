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


def test_v121_installer_and_release_workflow_support_verified_auto_update():
    batch = Path("BUILD_EXE.bat").read_text(encoding="utf-8")
    installer = Path("packaging/TikTokAffiliateReport.iss").read_text(encoding="utf-8")
    build = Path("packaging/build_installer.ps1").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert APP_VERSION == "1.2.1"
    assert "[string]$AppVersion = '1.2.1'" in build
    assert '#define MyAppVersion "1.2.1"' in installer
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "pnpm/action-setup@v6" in workflow
    assert "actions/setup-node@v7" in workflow
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
    assert "fresh-install-v120" in workflows
    assert "upgrade-v111-to-v120" in workflows
