"""Windows code paths that can run on Linux."""

import socket

import pytest

from multidrop import config, daemon


def test_runtime_dir_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WINDOWS", True)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.runtime_dir() == tmp_path / "multidrop" / "run"
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "xdg"))
    assert config.runtime_dir() == tmp_path / "xdg" / "multidrop"


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

    monkeypatch.delattr(socket_mod, "AF_UNIX", raising=False)
    from multidrop.daemon import api
    req = type("R", (), {"transport": type("T", (), {"get_extra_info": lambda self, k: object()})()})()
    assert api._via_unix_socket(req) is False


async def test_cli_client_over_tcp(monkeypatch, make_config, tmp_path):
    """On Windows the CLI reaches multidropd over 127.0.0.1 with the token."""
    import asyncio

    from multidrop.daemon import client, run, socket_path
    monkeypatch.setattr(client, "WINDOWS", True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "rt"))
    cfg = make_config("winpc")
    cfg.daemon.web_port = 0
    assert await client.DaemonClient.connect(socket_path(cfg)) is None
    started = asyncio.get_running_loop().create_future()
    stop = asyncio.Event()
    task = asyncio.ensure_future(run(cfg, notifications=False, started=started, stop=stop))
    try:
        await asyncio.wait_for(asyncio.shield(started), 10)
        async with await client.DaemonClient.connect(socket_path(cfg)) as c:
            assert (await c.get("/api/status"))["alias"] == "winpc"
    finally:
        stop.set()
        await asyncio.wait_for(task, 10)


def test_cli_output_is_utf8(monkeypatch):
    """The terminal QR code must not crash on a cp1252 pipe."""
    import io
    import sys

    from multidrop import cli
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    cli._utf8_output()
    print("\u2580\u2584\u2588", end="")
    out.flush()
    assert out.buffer.getvalue() == "\u2580\u2584\u2588".encode()
