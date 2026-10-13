import socket

import pytest

from multidrop.config import Config


def free_port(kind=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def make_config(tmp_path):
    """Config for one isolated instance: own dirs, own port, discovery on lo."""
    mc_port = free_port(socket.SOCK_DGRAM)

    def make(alias: str, https: bool = True, pin: str | None = None) -> Config:
        cfg = Config()
        cfg.alias = alias
        cfg.download_dir = tmp_path / alias / "downloads"
        cfg.state_dir = tmp_path / alias / "state"
        cfg.localsend.port = free_port()
        cfg.localsend.bind = "127.0.0.1"
        cfg.localsend.https = https
        cfg.localsend.pin = pin
        cfg.localsend.multicast_port = mc_port
        cfg.localsend.multicast_interface = "127.0.0.1"
        # Never touch the real network or Bluetooth from tests.
        cfg.quickshare.mdns_addresses = ["127.0.0.1"]
        cfg.quickshare.ble = False
        cfg.airdrop.ble = False
        cfg.quickshare.port = 0
        cfg.localsend.share_port = 0
        cfg.localsend.share_bind = "127.0.0.1"
        cfg.daemon.history_file = str(tmp_path / alias / "history.jsonl")
        return cfg

    return make
