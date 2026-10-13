"""Browser download: PC -> any phone without an app (LocalSend v2.2 section 5,
"Download API").

Runs only while the user explicitly shares something and stops by itself
after `minutes`. Plain HTTP on its own port, because browsers reject the
self-signed certificate of the LocalSend server. Protection, beyond the spec:

* a random key in the URL (`?k=`); every route needs it, so the port alone
  reveals nothing, and the key travels via QR code or by reading it off;
* a PIN (default: random 4 digits) asked for on the page, or `?pin=` on
  prepare-download as in the spec;
* after 5 wrong PINs an address gets 429, after 30 in total the share stops;
* sessions are random 128-bit ids handed out after the PIN.

Routes (all need ?k=KEY):
  GET  /                                 page: PIN form or file list
  POST /unlock                           form: pin -> redirect to /?s=SESSION
  POST /api/localsend/v2/prepare-download  spec: ?pin= &sessionId= -> JSON
  GET  /api/localsend/v2/download        spec: ?sessionId= &fileId=
  GET  /zip                              all files as one ZIP (?s=SESSION)
"""

from __future__ import annotations

import asyncio
import errno
import html
import logging
import mimetypes
import secrets
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from multidrop.core import EventHandler, _noop_event, collect_files

log = logging.getLogger(__name__)

DEFAULT_PORT = 53320
MAX_FAILS_PER_IP = 5
MAX_FAILS_TOTAL = 30


@dataclass
class SharedFile:
    id: str
    path: Path
    name: str          # relative name, "dir/file.jpg" for folders
    size: int
    mime: str


class WebShare:
    def __init__(self, paths: list[Path], *, alias: str, pin: str | None = "",
                 minutes: float = 15, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 public_address: str | None = None, on_event: EventHandler = _noop_event):
        """pin: "" = generate 4 digits, None = no PIN."""
        self.files: dict[str, SharedFile] = {}
        for path, name in collect_files(paths):
            fid = secrets.token_hex(8)
            self.files[fid] = SharedFile(fid, path, name, path.stat().st_size,
                                         mimetypes.guess_type(name)[0]
                                         or "application/octet-stream")
        self.alias = alias
        self.pin = f"{secrets.randbelow(10000):04d}" if pin == "" else pin
        self.key = secrets.token_urlsafe(9)
        self.minutes = minutes
        self.host, self.port = host, port
        self.public_address = public_address
        self.on_event = on_event
        self.sessions: dict[str, str] = {}        # session id -> client address
        self.fails: dict[str, int] = {}
        self.downloads = 0
        self.expires = 0.0
        self.stopped = asyncio.Event()
        self._runner: web.AppRunner | None = None
        self._timer: asyncio.TimerHandle | None = None

    # -- lifecycle --------------------------------------------------------

    @property
    def url(self) -> str:
        return f"http://{self.public_address or self.host}:{self.port}/?k={self.key}"

    async def start(self) -> None:
        app = web.Application(middlewares=[self._guard])
        app.add_routes([
            web.get("/", self._page),
            web.post("/unlock", self._unlock),
            web.post("/api/localsend/v2/prepare-download", self._prepare),
            web.get("/api/localsend/v2/download", self._download),
            web.get("/zip", self._zip),
        ])
        self._runner = web.AppRunner(app, handle_signals=False, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        try:
            await site.start()
        except OSError as e:
            if e.errno != errno.EADDRINUSE or not self.port:
                await self._runner.cleanup()
                raise
            site = web.TCPSite(self._runner, self.host, 0)
            await site.start()
            log.warning("share port %d is in use, using a random port", self.port)
        self.port = next(a[1] for a in self._runner.addresses)
        if self.public_address is None:
            from multidrop.backends.quickshare.mdns import default_address
            self.public_address = default_address() if self.host == "0.0.0.0" else self.host
        self.expires = time.time() + self.minutes * 60
        self._timer = asyncio.get_running_loop().call_later(
            self.minutes * 60, lambda: asyncio.ensure_future(self.stop("expired")))
        self.on_event("share_started", self.status())

    async def stop(self, reason: str = "stopped") -> None:
        if self._runner is None:
            return
        runner, self._runner = self._runner, None
        if self._timer:
            self._timer.cancel()
        await runner.cleanup()
        self.stopped.set()
        self.on_event("share_stopped", {"reason": reason, "downloads": self.downloads})

    def status(self) -> dict:
        return {"url": self.url, "pin": self.pin, "expires": self.expires,
                "files": [f.name for f in self.files.values()],
                "size": sum(f.size for f in self.files.values()),
                "downloads": self.downloads, "running": self._runner is not None}

    # -- access control ---------------------------------------------------

    @web.middleware
    async def _guard(self, request: web.Request, handler):
        if not secrets.compare_digest(request.query.get("k", ""), self.key):
            return web.Response(status=404, text="Not found")
        resp = await handler(request)
        resp.headers.setdefault("Cache-Control", "no-store")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        return resp

    def _client(self, request: web.Request) -> str:
        return request.remote or "?"

    def _check_pin(self, request: web.Request, pin: str | None) -> web.Response | None:
        ip = self._client(request)
        if self.fails.get(ip, 0) >= MAX_FAILS_PER_IP:
            return web.Response(status=429, text="Too many requests")
        if self.pin is None or (pin is not None and secrets.compare_digest(pin, self.pin)):
            return None
        if pin is not None:
            self.fails[ip] = self.fails.get(ip, 0) + 1
            self.on_event("share_wrong_pin", {"from": ip})
            if sum(self.fails.values()) >= MAX_FAILS_TOTAL:
                asyncio.ensure_future(self.stop("too many wrong PINs"))
        return web.Response(status=401, text="PIN required" if pin is None else "Invalid PIN")

    def _new_session(self, request: web.Request) -> str:
        sid = secrets.token_urlsafe(16)
        self.sessions[sid] = self._client(request)
        self.on_event("share_visit", {"from": self._client(request)})
        return sid

    def _session_ok(self, sid: str | None) -> bool:
        return bool(sid) and sid in self.sessions

    # -- spec API ---------------------------------------------------------

    async def _prepare(self, request: web.Request) -> web.Response:
        sid = request.query.get("sessionId")
        if not self._session_ok(sid):
            denied = self._check_pin(request, request.query.get("pin"))
            if denied:
                return denied
            sid = self._new_session(request)
        return web.json_response({
            "info": {"alias": self.alias, "version": "2.1", "deviceModel": "Linux",
                     "deviceType": "desktop", "fingerprint": "", "download": True},
            "sessionId": sid,
            "files": {f.id: {"id": f.id, "fileName": f.name, "size": f.size,
                             "fileType": f.mime, "sha256": None, "preview": None}
                      for f in self.files.values()}})

    async def _download(self, request: web.Request) -> web.StreamResponse:
        if not self._session_ok(request.query.get("sessionId")):
            return web.Response(status=403, text="Rejected")
        f = self.files.get(request.query.get("fileId", ""))
        if f is None:
            return web.Response(status=404, text="Not found")
        if not request.headers.get("Range"):
            self.downloads += 1
            self.on_event("share_download", {"from": self._client(request), "file": f.name})
        resp = web.FileResponse(f.path, headers={
            "Content-Type": f.mime,
            "Content-Disposition": _attachment(f.name.rsplit("/", 1)[-1])})
        return resp

    # -- browser page -----------------------------------------------------

    async def _unlock(self, request: web.Request) -> web.Response:
        form = await request.post()
        denied = self._check_pin(request, str(form.get("pin", "")).strip())
        if denied is not None:
            if denied.status == 429:
                return denied
            return _html(self._pin_page(error=True), 401)
        raise web.HTTPSeeOther(f"/?k={self.key}&s={self._new_session(request)}")

    async def _page(self, request: web.Request) -> web.Response:
        sid = request.query.get("s")
        if not self._session_ok(sid):
            if self.pin is not None:
                return _html(self._pin_page())
            sid = self._new_session(request)
        rows = []
        for f in self.files.values():
            href = (f"/api/localsend/v2/download?k={self.key}&sessionId={quote(sid)}"
                    f"&fileId={f.id}")
            rows.append(f'<li><a href="{html.escape(href)}" download="'
                        f'{html.escape(f.name.rsplit("/", 1)[-1])}">'
                        f'{html.escape(f.name)}</a> <small>{_human(f.size)}</small></li>')
        zip_link = (f'<p><a class="btn" href="/zip?k={self.key}&amp;s={quote(sid)}">'
                    f'Download all as ZIP</a></p>' if len(self.files) > 1 else "")
        return _html(_PAGE.format(
            title=html.escape(f"Files from {self.alias}"),
            body=f'<ul>{"".join(rows)}</ul>{zip_link}'))

    def _pin_page(self, error: bool = False) -> str:
        msg = '<p class="err">Wrong PIN.</p>' if error else ""
        return _PAGE.format(title=html.escape(f"Files from {self.alias}"), body=(
            f'{msg}<form method="post" action="/unlock?k={self.key}">'
            '<label>PIN (shown on the computer)<br><input name="pin" inputmode="numeric" '
            'autocomplete="off" autofocus required></label> '
            '<button>Open</button></form>'))

    async def _zip(self, request: web.Request) -> web.StreamResponse:
        if not self._session_ok(request.query.get("s")):
            return web.Response(status=403, text="Rejected")
        resp = web.StreamResponse(headers={
            "Content-Type": "application/zip",
            "Content-Disposition": _attachment(f"{self.alias}.zip")})
        await resp.prepare(request)
        self.downloads += 1
        self.on_event("share_download", {"from": self._client(request), "file": "(ZIP)"})
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=8)
        cancelled = threading.Event()
        files = list(self.files.values())

        class Pipe:      # unseekable sink: zipfile then writes data descriptors
            def write(self, b):
                if cancelled.is_set():
                    raise OSError("client gone")
                asyncio.run_coroutine_threadsafe(queue.put(bytes(b)), loop).result()
                return len(b)

            def flush(self):
                pass

        def produce():
            try:
                with zipfile.ZipFile(Pipe(), "w", zipfile.ZIP_STORED) as zf:
                    for f in files:
                        zf.write(f.path, f.name)
            except OSError:
                pass
            finally:
                if not cancelled.is_set():
                    asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

        producer = loop.run_in_executor(None, produce)
        try:
            while (chunk := await queue.get()) is not None:
                await resp.write(chunk)
        finally:
            cancelled.set()
            while not queue.empty():        # unblock a waiting producer
                queue.get_nowait()
            await producer
        return resp


def _attachment(name: str) -> str:
    ascii_name = name.encode("ascii", "replace").decode().replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return str(n)


def _html(text: str, status: int = 200) -> web.Response:
    return web.Response(text=text, status=status, content_type="text/html", headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                   "form-action 'self'; frame-ancestors 'none'"})


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><title>{title}</title>
<style>body{{font:17px/1.5 system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem}}
li{{margin:.6rem 0}} a{{color:#1f6feb}} small{{color:#777}} .err{{color:#c62828}}
input,button{{font:inherit;padding:.4rem .7rem}} .btn{{display:inline-block;padding:.5rem 1rem;
background:#1f6feb;color:#fff;border-radius:6px;text-decoration:none}}</style></head>
<body><h1>{title}</h1>{body}<p><small>MultiDrop · LocalSend download</small></p></body></html>"""
