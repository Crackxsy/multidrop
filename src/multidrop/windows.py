"""MultiDrop for Windows: background service, tray icon, UI in the browser.

Quick Share and LocalSend work as on Linux. AirDrop needs Apple's AWDL radio
link, which Windows Wi-Fi drivers cannot provide, and AirPlay mirroring uses
Linux screen capture, so neither is part of the Windows build.

Built into MultiDrop.exe by packaging/windows/multidrop.spec (GitHub Actions).
`MultiDrop.exe --selftest` starts the service, checks its API and exits.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from multidrop import daemon
from multidrop.config import Config, runtime_dir

APP_NAME = "MultiDrop"
log = logging.getLogger("multidrop.windows")


def _resource(name: str) -> Path:
    """Bundled file (PyInstaller unpacks to sys._MEIPASS) or the source tree."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / name


class Service:
    """multidropd's run() on its own event loop thread."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.loop = asyncio.new_event_loop()
        self.stop_event: asyncio.Event | None = None
        self.url = ""
        self.error: BaseException | None = None
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name="multidropd", daemon=True)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)

        async def main():
            self.stop_event = asyncio.Event()
            started = self.loop.create_future()
            started.add_done_callback(lambda f: self._started(f))
            await daemon.run(self.cfg, started=started, stop=self.stop_event,
                             notifications=False)
        try:
            self.loop.run_until_complete(main())
        except BaseException as e:      # reported to the user by start()
            self.error = e
        finally:
            self._ready.set()

    def _started(self, fut: asyncio.Future) -> None:
        if not fut.cancelled():
            self.url = fut.result()
        self._ready.set()

    def start(self, timeout: float = 30) -> str:
        self.thread.start()
        self._ready.wait(timeout)
        if self.error is not None:
            raise self.error
        if not self.url:
            raise TimeoutError("MultiDrop service did not start")
        return self.url

    def stop(self) -> None:
        if self.stop_event is not None:
            self.loop.call_soon_threadsafe(self.stop_event.set)
        self.thread.join(10)

    def api(self, path: str):
        base, _, token = self.url.partition("/#t=")
        req = urllib.request.Request(base.rstrip("/") + path,
                                     headers={"X-Multidrop-Token": token})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())


def _watch_offers(service: Service, notify) -> None:
    """Incoming offers: Windows notification and the UI in the browser (the
    D-Bus notifications with Accept/Decline exist only on Linux)."""
    seen: set[str] = set()
    while True:
        try:
            for offer in service.api("/api/offers"):
                if offer["id"] in seen:
                    continue
                seen.add(offer["id"])
                count = len(offer.get("files") or [])
                notify(f"{offer.get('from', 'A device')} wants to send {count} item(s)",
                       APP_NAME)
                webbrowser.open(service.url)
        except Exception as e:          # service restarting or stopping
            log.debug("offer poll: %s", e)
        time.sleep(2)


def _selftest(service: Service) -> int:
    status = service.api("/api/status")
    if sys.stdout is not None:          # the windowed .exe has no console
        print(json.dumps(status, indent=2))
    ok = "quickshare" in status["protocols"] or "localsend" in status["protocols"]
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="MultiDrop", description=__doc__.splitlines()[0])
    p.add_argument("--config", help="config file")
    p.add_argument("--no-browser", action="store_true", help="don't open the UI at start")
    p.add_argument("--selftest", action="store_true", help="start, check the API, exit")
    args = p.parse_args(argv)

    log_dir = runtime_dir().parent
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=None if args.selftest else str(log_dir / "multidrop.log"),
                        level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cfg = Config.load(Path(args.config) if args.config else None)
    service = Service(cfg)
    try:
        url = service.start()
    except daemon.AlreadyRunning:
        # Second start (e.g. from the Start menu): show the running one.
        try:
            webbrowser.open((runtime_dir() / "url").read_text().strip())
        except OSError:
            pass
        return 0
    if args.selftest:
        try:
            return _selftest(service)
        finally:
            service.stop()
    if not args.no_browser:
        webbrowser.open(url)

    try:
        import pystray
        from PIL import Image
    except ImportError:                 # source checkout without the tray extras
        print(f"{APP_NAME} is running: {url}  (Ctrl+C quits)")
        try:
            while service.thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        service.stop()
        return 0

    def open_ui(icon=None, item=None):
        webbrowser.open(service.url)

    def open_downloads(icon=None, item=None):
        cfg.download_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(cfg.download_dir)) if os.name == "nt" else webbrowser.open(
            cfg.download_dir.as_uri())

    def quit_app(icon, item=None):
        icon.stop()

    icon = pystray.Icon(APP_NAME, Image.open(_resource("multidrop.png")), APP_NAME,
                        menu=pystray.Menu(
                            pystray.MenuItem(f"Open {APP_NAME}", open_ui, default=True),
                            pystray.MenuItem("Received files", open_downloads),
                            pystray.Menu.SEPARATOR,
                            pystray.MenuItem("Quit", quit_app)))
    threading.Thread(target=_watch_offers, args=(service, icon.notify), daemon=True).start()
    icon.run()
    service.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
