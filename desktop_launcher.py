from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    run_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else bundle_dir
    data_dir = run_dir / "data"
    database = data_dir / "tiktok_affiliate_report.db"
    data_dir.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):
        log = (data_dir / "launcher.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    os.chdir(run_dir)
    os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_SERVER_SHOW_EMAIL_PROMPT"] = "false"
    from streamlit.web import cli as streamlit_cli

    sys.argv = [
        "streamlit",
        "run",
        str(bundle_dir / "streamlit_app.py"),
        "--server.address=127.0.0.1",
        "--server.port=8501",
        "--server.headless=false",
        "--server.showEmailPrompt=false",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    raise SystemExit(streamlit_cli.main())


if __name__ == "__main__":
    main()
