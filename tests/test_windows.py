"""Windows code paths that can run on Linux."""

import socket

import pytest

from multidrop import config, daemon


def test_runtime_dir_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.runtime_dir() == tmp_path / "multidrop" / "run"


def test_single_instance_by_web_port(tmp_path):
    url_file = tmp_path / "url"
    daemon._check_not_running_tcp(url_file)            # no file: fine
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        url_file.write_text(f"http://127.0.0.1:{port}/#t=abc\n")
        with pytest.raises(daemon.AlreadyRunning):
            daemon._check_not_running_tcp(url_file)
    daemon._check_not_running_tcp(url_file)            # port closed: stale file
    assert not url_file.exists()


def test_windows_entry_selftest(tmp_path, monkeypatch, make_config):
    """The .exe's --selftest path: service thread, API over HTTP with token."""
    from multidrop import windows
    cfg = make_config("winpc")
    cfg.daemon.web_port = 0
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "rt"))
    (tmp_path / "rt").mkdir(mode=0o700)
    service = windows.Service(cfg)
    url = service.start()
    try:
        assert url.startswith("http://127.0.0.1:")
        assert windows._selftest(service) == 0
    finally:
        service.stop()


async def test_api_without_af_unix(monkeypatch, make_config, tmp_path):
    """Windows' socket module has no AF_UNIX (seen in CI: HTTP 500)."""
    import socket as socket_mod

    monkeypatch.delattr(socket_mod, "AF_UNIX")
    from multidrop.daemon import api
    req = type("R", (), {"transport": type("T", (), {"get_extra_info": lambda self, k: object()})()})()
    assert api._via_unix_socket(req) is False
