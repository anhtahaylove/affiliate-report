from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_updater_diagnostic_scrubber_removes_paths_and_complete_credentials(tmp_path):
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    scrubber = Path("scripts/ci/updater_diagnostics.ps1").resolve()
    source = tmp_path / "diagnostic.txt"
    secret_values = ["TOP-SECRET-VALUE", "JSON AUTH SECRET !", "TOKEN-SECRET", "PLAIN SECRET !"]
    source.write_text(
        "\n".join(
            [
                r"c:\users\RUNNER\appdata\local\tiktokaffiliatereport\data\updater.log",
                f"Authorization: Bearer {secret_values[0]}",
                f'{{"authorization":"Bearer {secret_values[1]}"}}',
                f"UPDATE_FEED_TOKEN={secret_values[2]}",
                f'{{"client_secret":"{secret_values[3]}"}}',
            ]
        ),
        encoding="utf-8",
    )
    probe = tmp_path / "scrub.ps1"
    probe.write_text(
        r'''
param([string]$Scrubber, [string]$Source)
. $Scrubber
$text = [System.IO.File]::ReadAllText($Source)
$paths = @{ 'C:\Users\runner\AppData\Local\TikTokAffiliateReport' = '[install dir]' }
Write-Output (ConvertTo-ScrubbedUpdaterText -Text $text -PathReplacements $paths)
''',
        encoding="utf-8-sig",
    )

    completed = subprocess.run(
        [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe), str(scrubber), str(source)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "[install dir]" in completed.stdout
    assert r"c:\users\RUNNER" not in completed.stdout
    assert completed.stdout.count("[redacted]") == 4
    for secret in secret_values:
        assert secret not in completed.stdout
