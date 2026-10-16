"""Browser download (LocalSend download API) on 127.0.0.1."""

import asyncio
import html
import io
import zipfile

import aiohttp
import pytest

from conftest import WINDOWS
from multidrop.backends.localsend.webshare import MAX_FAILS_PER_IP, WebShare

# Markup in a file name must be escaped; Windows forbids < and > in names.
NAME = "x&y.txt" if WINDOWS else "<i>x&y.txt"


@pytest.fixture
async def share(tmp_path):
    shares = []

    async def make(pin="1234", minutes=5):
        (tmp_path / "Album").mkdir(exist_ok=True)
        (tmp_path / "Album" / "a.jpg").write_bytes(b"A" * 100_000)
        (tmp_path / NAME).write_text("hello")
        events = []
        s = WebShare([tmp_path / "Album", tmp_path / NAME], alias="PC",
                     pin=pin, minutes=minutes, host="127.0.0.1", port=0,
                     on_event=lambda e, d: events.append((e, d)))
        await s.start()
        shares.append(s)
        return s, events, f"http://127.0.0.1:{s.port}"

    yield make
    for s in shares:
        await s.stop()


async def test_key_pin_and_download(share):
    s, events, base = await share()
    assert s.url == f"{base}/?k={s.key}"
    async with aiohttp.ClientSession() as http:
        for path in ("/", "/zip", "/api/localsend/v2/download"):
            async with http.get(base + path) as r:
                assert r.status == 404                    # no key, nothing visible
        async with http.get(s.url) as r:
            page = await r.text()
            assert r.status == 200 and 'name="pin"' in page and "a.jpg" not in page
        async with http.post(f"{base}/unlock?k={s.key}", data={"pin": "0000"}) as r:
            assert r.status == 401 and "Wrong PIN" in await r.text()
        async with http.post(f"{base}/unlock?k={s.key}", data={"pin": "1234"},
                             allow_redirects=False) as r:
            assert r.status == 303
            location = r.headers["Location"]
        async with http.get(base + location) as r:
            page = await r.text()
        assert "Album/a.jpg" in page and html.escape(NAME) in page and "<i>x" not in page
        links = [l.split('"')[0].replace("&amp;", "&") for l in page.split('href="')[1:]]
        file_link = next(l for l in links if "download?" in l)
        async with http.get(base + file_link) as r:
            body = await r.read()
            assert r.headers["Content-Disposition"].startswith("attachment;")
        assert body in (b"A" * 100_000, b"hello")
        zip_link = next(l for l in links if l.startswith("/zip"))
        async with http.get(base + zip_link) as r:
            zf = zipfile.ZipFile(io.BytesIO(await r.read()))
        assert sorted(zf.namelist()) == sorted([NAME, "Album/a.jpg"])
        assert zf.read("Album/a.jpg") == b"A" * 100_000
        # A made-up session gets nothing.
        async with http.get(f"{base}/zip?k={s.key}&s=guess") as r:
            assert r.status == 403
    names = [e for e, _ in events]
    assert names[0] == "share_started" and "share_wrong_pin" in names
    assert names.count("share_download") == 2


async def test_spec_api_and_rate_limit(share):
    s, events, base = await share(pin="987654")
    prep = f"{base}/api/localsend/v2/prepare-download?k={s.key}"
    async with aiohttp.ClientSession() as http:
        async with http.post(prep) as r:
            assert r.status == 401 and await r.text() == "PIN required"
        async with http.post(prep + "&pin=987654") as r:
            data = await r.json()
        assert data["info"]["download"] is True and len(data["files"]) == 2
        sid = data["sessionId"]
        async with http.post(prep + f"&sessionId={sid}") as r:   # page reload
            assert r.status == 200 and (await r.json())["sessionId"] == sid
        fid, meta = next((k, v) for k, v in data["files"].items() if v["fileName"] == "Album/a.jpg")
        async with http.get(f"{base}/api/localsend/v2/download?k={s.key}&sessionId={sid}"
                            f"&fileId={fid}", headers={"Range": "bytes=10-19"}) as r:
            assert r.status == 206 and await r.read() == b"A" * 10      # resumable
        async with http.get(f"{base}/api/localsend/v2/download?k={s.key}&sessionId=nope"
                            f"&fileId={fid}") as r:
            assert r.status == 403
        for _ in range(MAX_FAILS_PER_IP):
            async with http.post(prep + "&pin=111111") as r:
                assert r.status == 401
        async with http.post(prep + "&pin=987654") as r:
            assert r.status == 429                      # locked out, even with the right PIN


async def test_no_pin_and_expiry(share):
    s, events, base = await share(pin=None, minutes=0.01)
    async with aiohttp.ClientSession() as http:
        async with http.get(s.url) as r:
            assert "a.jpg" in await r.text()            # straight to the list
    await asyncio.wait_for(s.stopped.wait(), 5)
    assert events[-1] == ("share_stopped", {"reason": "expired", "downloads": 0})
    async with aiohttp.ClientSession() as http:
        with pytest.raises(aiohttp.ClientConnectionError):
            await http.get(s.url)


async def test_generated_pin(share):
    s, _, _ = await share(pin="")
    assert len(s.pin) == 4 and s.pin.isdigit()
