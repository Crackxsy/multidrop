"""Click test of the Windows app, entirely on 127.0.0.1.

Starts the real tray app (python -m multidrop.windows) in a throw-away profile
(own APPDATA, runtime dir, config; discovery on loopback only, no browser
window) and a simulated "phone" (multidrop receive). Then:

  1. Explorer's "Send to": a second start with a file hands it over
  2. web UI (headless Chromium): the file is listed, a click on the phone sends it
  3. tray menu: "Show in "Send to" menu" on and off (shortcut in the temp profile)
  4. tray menu: "Play audio on" opens the AirPlay speaker list
  5. tray menu: "Quit" ends the app

The tray menu is opened with the message Explorer sends on a right-click on
the icon, the entries are clicked through UI Automation (the mouse is not
moved). Prints one line per step; screenshots and the app log go to OUT_DIR.

  pip install playwright pywinauto
  python -m playwright install chromium-headless-shell
  python tools/dev/win_click_test.py [OUT_DIR]
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WM_NOTIFY = 0x400 + 11      # pystray's tray callback message
WM_RBUTTONUP = 0x0205


def free_port(kind=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(pred, what: str, timeout: float = 20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = pred()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError(f"timed out: {what}")


def step(text: str) -> None:
    print(f"ok  {text}", flush=True)


def process_tree(pid: int) -> list[int]:
    """pid and its children: a venv's python.exe starts the real interpreter
    as a child process."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}').ProcessId"],
                         capture_output=True, text=True, timeout=30).stdout
    return [pid, *map(int, out.split())]


def tray_menu_item(pid: int, name: str):
    """Open the tray icon's menu and return its entry `name`."""
    import ctypes

    from pywinauto import Desktop, findwindows
    hwnds = [h for p in process_tree(pid)
             for h in findwindows.find_windows(process=p, visible_only=False,
                                               class_name_re=r"MultiDrop\d+SystemTrayIcon")]
    assert hwnds, "no tray icon window"
    for hwnd in hwnds:
        ctypes.windll.user32.PostMessageW(hwnd, WM_NOTIFY, 0, WM_RBUTTONUP)
    menu = Desktop(backend="uia").window(class_name="#32768", control_type="Menu")
    menu.wait("visible", timeout=10)
    return menu.child_window(title=name, control_type="MenuItem")


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="multidrop-click-"))
    mc, pc_ls, pc_qs = free_port(socket.SOCK_DGRAM), free_port(), free_port()
    phone_ls, phone_qs = free_port(), free_port()
    cfg = root / "pc.toml"
    cfg.write_text(f'''alias = "pc"
download_dir = "{(root / 'pc-in').as_posix()}"
state_dir = "{(root / 'pc-state').as_posix()}"
[localsend]
port = {pc_ls}
bind = "127.0.0.1"
multicast_port = {mc}
multicast_interface = "127.0.0.1"
share_port = 0
share_bind = "127.0.0.1"
[quickshare]
port = {pc_qs}
bind = "127.0.0.1"
mdns_addresses = ["127.0.0.1"]
ble = false
[daemon]
web_port = 0
''')
    py = sys.executable
    # A no-op "browser": the app must not open windows on the desktop.
    env = {**os.environ, "MULTIDROP_CONFIG": str(cfg), "XDG_RUNTIME_DIR": str(root / "rt"),
           "XDG_DATA_HOME": str(root / "data"), "APPDATA": str(root / "appdata"),
           "BROWSER": f"{Path(py).as_posix()} -c pass"}
    phone_env = {**env, "MULTIDROP_CONFIG": str(root / "none.toml"),
                 "XDG_RUNTIME_DIR": str(root / "rt-phone"),
                 "XDG_DATA_HOME": str(root / "phone-data")}
    inbox = root / "phone-in"
    phone = subprocess.Popen(
        [py, "-m", "multidrop", "--alias", "phone", "--port", str(phone_ls),
         "--multicast-port", str(mc), "--multicast-interface", "127.0.0.1",
         "--qs-port", str(phone_qs), "--mdns-address", "127.0.0.1", "--no-ble",
         "receive", "--accept", "all", "--dir", str(inbox)],
        env=phone_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    app = subprocess.Popen([py, "-m", "multidrop.windows", "--no-browser"], env=env)
    url_file = root / "rt" / "multidrop" / "url"
    try:
        url = wait(lambda: url_file.exists() and url_file.read_text().strip(), "app start")
        step("tray app started")

        photo = root / "Foto.jpg"
        photo.write_bytes(os.urandom(200_000))
        second = subprocess.run([py, "-m", "multidrop.windows", str(photo)], env=env, timeout=60)
        assert second.returncode == 0, f"second start: exit {second.returncode}"
        step("Send to: second start handed the file over")

        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.wait_for_selector("#selection-section:not([hidden]) li:text('Foto.jpg')")
            page.screenshot(path=str(out / "1-selection.png"))
            step("UI lists the handed-over file")
            page.click("#refresh")
            card = page.locator("#devices .card", has=page.locator(".name:text-is('phone')"))
            card.wait_for(timeout=20_000)
            card.locator(".name").click()
            wait(lambda: (inbox / "Foto.jpg").exists()
                 and (inbox / "Foto.jpg").read_bytes() == photo.read_bytes(),
                 "file at the phone", 30)
            page.wait_for_selector("#selection-section", state="hidden")
            page.screenshot(path=str(out / "2-sent.png"))
            browser.close()
            assert not errors, errors
        step("click on the phone sent the file")

        link = root / "appdata" / "Microsoft" / "Windows" / "SendTo" / "MultiDrop.lnk"
        tray_menu_item(app.pid, 'Show in "Send to" menu').invoke()
        wait(link.exists, "Send to shortcut")
        tray_menu_item(app.pid, 'Show in "Send to" menu').invoke()
        wait(lambda: not link.exists(), "Send to shortcut removed")
        step('tray: "Send to" entry switched on and off')

        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys
        tray_menu_item(app.pid, "Play audio on").expand()
        wait(lambda: any(w.descendants(title="This computer")
                         for w in Desktop(backend="uia").windows(class_name="#32768")),
             "AirPlay speaker submenu", 10)
        send_keys("{ESC}{ESC}")
        step('tray: "Play audio on" lists the speakers')

        tray_menu_item(app.pid, "Quit").invoke()
        assert app.wait(20) == 0, f"exit code {app.returncode}"
        step("tray: Quit ended the app")
        print("PASS", flush=True)
        return 0
    except Exception as e:
        print(f"FAIL {type(e).__name__}: {e}", flush=True)
        return 1
    finally:
        for p in (app, phone):
            if p.poll() is None:
                p.kill()
        log = root / "rt" / "multidrop.log"
        if log.exists():
            (out / "multidrop.log").write_bytes(log.read_bytes())


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1
                  else Path(tempfile.gettempdir()) / "multidrop-click"))
