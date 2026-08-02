from streamlit.testing.v1 import AppTest


def test_upload_account_has_no_unsafe_default(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'app.db').as_posix()}")

    app = AppTest.from_file("streamlit_app.py").run(timeout=30)

    account = next(widget for widget in app.selectbox if widget.label.startswith("Chọn affiliate account"))
    assert account.value is None
    assert account.options == ["CHIISTORE", "EMLINHNOIY", "THAOBRA"]
    assert not app.exception
