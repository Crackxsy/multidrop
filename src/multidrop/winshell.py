"""Windows shell integration, per user (no admin rights): start with Windows
and an entry in Explorer's "Send to" menu.

The names match packaging/windows/multidrop.iss, so the installer and the
tray menu switch the same entries.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "MultiDrop"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launcher() -> tuple[str, list[str]]:
    """Program and arguments that start the tray app: the .exe when frozen,
    else pythonw (no console window) with the module."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else exe), ["-m", "multidrop.windows"]


def _icon() -> str:
    """The .exe's own icon; in a source checkout the repository's .ico (a
    PyInstaller temp dir would be gone after exit)."""
    if getattr(sys, "frozen", False):
        return f"{sys.executable},0"
    return f"{Path(__file__).resolve().parents[2] / 'data' / 'icons' / 'multidrop.ico'},0"


def _command(*extra: str) -> str:
    program, args = launcher()
    return subprocess.list2cmdline([program, *args, *extra])


# -- start with Windows ------------------------------------------------------

def autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command("--no-browser"))
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# -- Explorer "Send to" --------------------------------------------------------

def sendto_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "SendTo"


def sendto_link() -> Path:
    return sendto_dir() / f"{APP_NAME}.lnk"


def sendto_enabled() -> bool:
    return sendto_link().exists()


def set_sendto(on: bool) -> None:
    link = sendto_link()
    if not on:
        link.unlink(missing_ok=True)
        return
    program, args = launcher()
    create_shortcut(link, program, subprocess.list2cmdline(args), _icon())


def create_shortcut(link: Path, target: str, arguments: str, icon: str) -> None:
    """Write a .lnk with WScript.Shell; values go through the environment, so
    paths are never parsed as PowerShell code."""
    link.parent.mkdir(parents=True, exist_ok=True)
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:MD_LINK); "
              "$s.TargetPath = $env:MD_TARGET; $s.Arguments = $env:MD_ARGS; "
              "$s.IconLocation = $env:MD_ICON; $s.Description = 'Send with MultiDrop'; "
              "$s.Save()")
    env = {**os.environ, "MD_LINK": str(link), "MD_TARGET": target,
           "MD_ARGS": arguments, "MD_ICON": icon}
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=env, check=True, capture_output=True, timeout=30,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
