<p align="center"><img src="docs/banner.png" alt="MultiDrop" width="100%"></p>

# MultiDrop

Share files, your screen and audio with devices nearby – on Linux and Windows,
using the protocols phones and Macs already have built in:

| | Linux | Windows | Other side |
|---|:---:|:---:|---|
| **Quick Share** (send/receive, also via QR code) | ✅ | ✅ | Android, Samsung – no app needed |
| **LocalSend** (send/receive) | ✅ | ✅ | iPhone, Android, PC with the LocalSend app |
| **Browser download** (QR code + PIN) | ✅ | ✅ | any phone, including iPhone, no app |
| **AirDrop** (send/receive) | ✅¹ | – | iPhone, iPad, Mac |
| **AirPlay screen mirroring** | ✅² | – | Apple TV, Mac, AirPlay TVs |
| **AirPlay audio** | ✅³ | – | Apple TV, HomePod, Sonos, AirPort, Mac |

¹ needs a supported Wi-Fi card and [omdrop-owl](https://github.com/t4t5/omdrop-owl), see below ·
² via [doubletake](https://github.com/omarroth/doubletake) ·
³ via PipeWire (`raop-discover`)

AirDrop needs Apple's own radio link (AWDL), which can only be recreated on
Linux with a suitable Wi-Fi card; Windows Wi-Fi drivers cannot do it.

> **Test status:** AirDrop Linux → Mac, Quick Share/LocalSend against other
> implementations and the official LocalSend app, and the Linux desktop app are
> tested. Quick Share with real Android/Samsung phones, AirPlay mirroring and
> audio on real devices, and the Windows build on real hardware are not fully
> verified yet. Samsung phones ignore the Bluetooth wake-up; use the QR code to
> send to Samsung.

## Windows

Download [**MultiDrop.exe** from Releases](../../releases/latest) and run it.
MultiDrop lives in the notification area (bottom right) and opens its interface
in your browser. Incoming files show a notification and open the interface.
On first start Windows Firewall asks – allow "Private networks", otherwise
phones cannot find the PC.

Received files go to `Downloads\multidrop`. From source:
`pip install ".[windows]"` and `multidrop-windows`.

## Linux

```bash
git clone https://github.com/digitaldanis/multidrop.git ~/multidrop
cd ~/multidrop
tools/install-desktop.sh --pin     # venv, launcher, icons, autostart, file manager action
```

Works on Ubuntu/Debian, Fedora, Arch/Manjaro, openSUSE and others (Python ≥ 3.11,
GTK ≥ 4.6, libadwaita ≥ 1.1). The script lists missing system packages with the
right command for your distribution; it never needs root itself.
`tools/install-desktop.sh --remove` removes everything again.

**The desktop app** sits in the top bar like on a Mac (KDE, XFCE, Cinnamon, MATE,
Budgie; GNOME with the "AppIndicator and KStatusNotifierItem Support" extension,
preinstalled on Ubuntu):

- **Window:** nearby devices as bubbles – drop files on one or click it. The
  **"Samsung/Android via QR code"** tile works even when a phone does not show
  up in the search.
- **Top bar menu:** devices, AirDrop on/off, mirror screen, play audio on …
- **File manager:** right-click → "Send with MultiDrop" (Nautilus, Nemo,
  Dolphin, Caja), or drop files on the dock icon.
- **Mirror screen (AirPlay):** the "Mirror" button. First pairing: enter the code
  shown on the TV. The installer downloads doubletake v0.5.0 (SHA-256 checked)
  to `~/.local/lib/multidrop`. Receivers without a screen (speakers) are hidden
  based on their own AirPlay announcement.
- **AirPlay audio:** the "Audio" button – the chosen speaker becomes the default
  output, so every app plays there; "This computer" switches back.

### AirDrop on Linux

AirDrop uses the original radio helper from
[omdrop-owl](https://github.com/t4t5/omdrop-owl) (OWL, AWDL in software), tested
with MediaTek MT7925; Intel cards run there in "exclusive" mode. Once (root,
Debian/Ubuntu):

```bash
tools/build-omdrop-owl.sh                                   # no root, pinned upstream
sudo apt install ./build/airdrop/omdrop-owl_0.1.0-1_amd64.deb
```

Then **"Turn AirDrop on"** in the app (10/30/60 minutes, password prompt) or
`multidrop airdrop run --minutes 10 --switch-channel`.

AirDrop shares the channel with your Wi-Fi and needs channel 6, 44 or 149. If
your Wi-Fi runs elsewhere (e.g. 6 GHz), MultiDrop asks and then moves to the
**same network** on a suitable channel for the session (temporary NetworkManager
profile) and back afterwards – a systemd timer restores it even after a crash.
Nothing needs to change on the router, as long as it also broadcasts the same
network on one of those channels. More: [INSTALL-ROOT.md](INSTALL-ROOT.md).

### Command line and background service

```bash
multidrop devices                                  # find devices
multidrop send photo.jpg folder/ --to "Galaxy S24" # protocol chosen automatically
multidrop send photo.jpg --qr                      # Quick Share via QR code
multidrop receive                                  # receive, confirm each transfer
multidrop share photos/                            # browser download (QR + PIN)
multidrop ui --open                                # web interface
```

`multidropd` is the background service (the desktop app starts it; as a
systemd user service: `contrib/systemd/multidropd.service`). It offers a local
API (Unix socket `$XDG_RUNTIME_DIR/multidrop/multidropd.sock`, endpoints in
`src/multidrop/daemon/api.py`) and a web interface on `127.0.0.1` only.
Configuration: `~/.config/multidrop/config.toml` (keys in
`src/multidrop/config.py`).

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/pytest -q
```

Design: [ARCHITECTURE.md](ARCHITECTURE.md), protocol notes:
[docs/RESEARCH.md](docs/RESEARCH.md). GitHub Actions
(`.github/workflows/build.yml`) runs the tests on Linux, builds `MultiDrop.exe`
with PyInstaller on Windows including a self-test, and publishes a release for
tags `v*`.

## Thanks

[NearDrop](https://github.com/grishka/NearDrop) (Quick Share protocol),
[rquickshare](https://github.com/Martichou/rquickshare),
[LocalSend](https://github.com/localsend/localsend),
[omdrop-owl](https://github.com/t4t5/omdrop-owl) and
[OWL](https://github.com/seemoo-lab/owl) (AWDL),
[OpenDrop](https://github.com/seemoo-lab/opendrop) (AirDrop protocol),
[doubletake](https://github.com/omarroth/doubletake) (AirPlay mirroring),
[UxPlay](https://github.com/FDH2/UxPlay).

Not affiliated with Apple, Google or Samsung. AirDrop, AirPlay and Quick Share
are trademarks of their respective owners.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
