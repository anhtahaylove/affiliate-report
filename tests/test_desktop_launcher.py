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


def test_next_launch_reuses_the_previous_port_so_an_open_tab_reconnects(tmp_path):
    """Cổng ngẫu nhiên mỗi lần chạy chính là lý do sau cập nhật phải mở tab mới: tab cũ trỏ vào
    cổng đã chết. Giữ nguyên cổng thì tab đó tự kết nối lại."""
    state = tmp_path / "instance.json"
    port = desktop_launcher._free_port()
    desktop_launcher._write_instance_state(state, f"http://127.0.0.1:{port}")

    assert desktop_launcher._preferred_port(state) == (port, True)

    # Cổng bị tiến trình khác chiếm thì phải lùi về cổng trống khác, không được chết cứng.
    import socket

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", port))
        fallback, reused = desktop_launcher._preferred_port(state)
    assert reused is False
    assert fallback != port

    # Chưa từng chạy lần nào thì không có gì để dùng lại.
    assert desktop_launcher._preferred_port(tmp_path / "missing.json")[1] is False


def test_exit_keeps_the_last_url_but_drops_the_pid(tmp_path):
    """Xoá hẳn file thì lần chạy sau không biết cổng nào để dùng lại. Giữ URL, bỏ pid — mọi nơi
    đọc file này đều gọi /health trước khi tin nên không ai bị đánh lừa."""
    state = tmp_path / "instance.json"
    desktop_launcher._write_instance_state(state, "http://127.0.0.1:43120")

    desktop_launcher._clear_instance_state(state, "http://127.0.0.1:43120")

    import json

    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["pid"] is None
    assert desktop_launcher._read_instance_url(state) == "http://127.0.0.1:43120"


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
