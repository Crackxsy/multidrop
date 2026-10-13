<p align="center"><img src="docs/banner.png" alt="MultiDrop" width="100%"></p>

<p align="center">
  <b>AirDrop, Quick Share, LocalSend and AirPlay for Linux and Windows.</b><br>
  Share files, your screen and audio with phones, Macs and TVs nearby.
</p>

<p align="center">
  <a href="../../releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/digitaldanis/multidrop"></a>
  <a href="../../actions/workflows/build.yml"><img alt="Build" src="https://github.com/digitaldanis/multidrop/actions/workflows/build.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: GPL-3.0" src="https://img.shields.io/badge/license-GPL--3.0-blue"></a>
</p>

## Features

| | Linux | Windows | Works with |
|---|:---:|:---:|---|
| **Quick Share** – send & receive, QR code | ✅ | ✅ | Android, Samsung (no app) |
| **LocalSend** – send & receive | ✅ | ✅ | iPhone, Android, PC with LocalSend |
| **Browser download** – QR code + PIN | ✅ | ✅ | any phone, no app |
| **AirDrop** – send & receive | ✅* | – | iPhone, iPad, Mac |
| **AirPlay** – mirror your screen | ✅ | – | Apple TV, Mac, AirPlay TVs |
| **AirPlay** – play audio | ✅ | – | Apple TV, HomePod, Sonos, Mac |

\* needs a supported Wi-Fi card, see [AirDrop setup](#airdrop-setup-linux).

## Install

### Windows

Download **MultiDrop.exe** from [Releases](../../releases/latest) and run it.
MultiDrop sits in the notification area and opens in your browser. Allow
*Private networks* when Windows Firewall asks.

### Linux

```bash
git clone https://github.com/digitaldanis/multidrop.git ~/multidrop
~/multidrop/tools/install-desktop.sh --pin
```

Ubuntu/Debian, Fedora, Arch, openSUSE and others (Python ≥ 3.11, GTK 4,
libadwaita). The installer needs no root and tells you if a system package is
missing. Uninstall with `tools/install-desktop.sh --remove`.

## Using it

- **Top bar menu** – nearby devices, AirDrop on/off, *Mirror screen*, *Play audio on*.
- **Window** – drop files on a device bubble, or click it. Samsung phones that
  don't show up: use the **QR code** tile.
- **File manager** – right-click → *Send with MultiDrop*, or drop files on the dock icon.
- **Receiving** – just send from your phone; MultiDrop asks before accepting.
  Files land in `~/Downloads/multidrop`.

On GNOME the top bar icon needs the *AppIndicator and KStatusNotifierItem
Support* extension (preinstalled on Ubuntu).

## AirDrop setup (Linux)

AirDrop uses [omdrop-owl](https://github.com/t4t5/omdrop-owl), which recreates
Apple's AWDL radio link in software (tested with MediaTek MT7925; Intel cards in
exclusive mode). Install it once, then turn AirDrop on in the app:

```bash
tools/build-omdrop-owl.sh
sudo apt install ./build/airdrop/omdrop-owl_0.1.0-1_amd64.deb
```

If your Wi-Fi isn't on channel 6, 44 or 149, MultiDrop temporarily switches to
the same network on one of those channels and switches back afterwards – no
router changes needed. Details: [docs/INSTALL-ROOT.md](docs/INSTALL-ROOT.md).

## Command line

```bash
multidrop devices                          # find devices
multidrop send photo.jpg --to "Galaxy S24" # send (protocol chosen automatically)
multidrop send photo.jpg --qr              # send via Quick Share QR code
multidrop receive                          # receive, confirm each transfer
multidrop share photos/                    # browser download with QR code + PIN
```

`multidropd` is the background service behind the apps (systemd unit in
`data/systemd/`). Config: `~/.config/multidrop/config.toml`.

## Status

Tested: AirDrop Linux → Mac, Quick Share and LocalSend against other
implementations and the official LocalSend app, the Linux desktop app, the
Windows build in CI. Not fully verified yet on real devices: Quick Share with
Android/Samsung phones, AirPlay mirroring and audio, Windows on real hardware.
Bug reports welcome.

## Project layout

```
src/multidrop/     service, protocols, Linux desktop app, Windows tray app
tests/             unit, loopback and interop tests
tools/             install-desktop.sh, fetch-doubletake.sh, build-omdrop-owl.sh, dev/
data/              icons, systemd unit
packaging/         Windows build entry point, release notes
docs/              architecture, protocol research, root setup
```

Development: `python3 -m venv .venv && .venv/bin/pip install -e ".[test]" && .venv/bin/pytest -q`.
Design notes: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/RESEARCH.md](docs/RESEARCH.md).

## Credits & license

Built on the work of [NearDrop](https://github.com/grishka/NearDrop),
[rquickshare](https://github.com/Martichou/rquickshare),
[LocalSend](https://github.com/localsend/localsend),
[omdrop-owl](https://github.com/t4t5/omdrop-owl), [OWL](https://github.com/seemoo-lab/owl),
[OpenDrop](https://github.com/seemoo-lab/opendrop),
[omdrop-plugin](https://github.com/brentkearney/omdrop-plugin),
[doubletake](https://github.com/omarroth/doubletake) and
[UxPlay](https://github.com/FDH2/UxPlay) – see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

MultiDrop is licensed under [GPL-3.0-or-later](LICENSE). Not affiliated with
Apple, Google or Samsung; AirDrop, AirPlay and Quick Share are their trademarks.
