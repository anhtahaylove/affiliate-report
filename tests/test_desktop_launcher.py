from __future__ import annotations

import os

import pytest

import desktop_launcher


def test_instance_state_accepts_only_loopback_url_and_reopens_it(tmp_path, monkeypatch):
    state = tmp_path / "instance.json"
    desktop_launcher._write_instance_state(state, "http://127.0.0.1:43120")

    opened = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(desktop_launcher, "urlopen", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(desktop_launcher.webbrowser, "open", lambda url, new=0: opened.append((url, new)))

    assert desktop_launcher._read_instance_url(state) == "http://127.0.0.1:43120"
    assert desktop_launcher._open_existing_instance(state) is True
    assert opened == [("http://127.0.0.1:43120", 2)]

    state.write_text('{"url":"https://example.com"}', encoding="utf-8")
    assert desktop_launcher._read_instance_url(state) is None


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutex")
def test_windows_mutex_allows_only_one_instance(monkeypatch):
    monkeypatch.setattr(desktop_launcher, "MUTEX_NAME", f"Local\\TikTokAffiliateReport.Tests.{os.getpid()}")
    first, first_is_primary = desktop_launcher._acquire_single_instance()
    second = None
    try:
        second, second_is_primary = desktop_launcher._acquire_single_instance()
        assert first_is_primary is True
        assert second_is_primary is False
        assert second is None
    finally:
        desktop_launcher._release_single_instance(second)
        desktop_launcher._release_single_instance(first)
