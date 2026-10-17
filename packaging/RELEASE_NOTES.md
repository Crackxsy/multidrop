## MultiDrop

Share files, your screen and audio with devices nearby – Linux and Windows.

### New in 0.2.0

- **Windows installer** – `MultiDrop-Setup.exe` installs just for you, no admin
  rights, with Start menu entry, *Send to* and *Start with Windows*.
- **Windows app window** – MultiDrop opens in its own window, explains on first
  start how phones send to it and keeps receiving in the notification area.
- **Explorer "Send to"** – right-click files → *Send to* → *MultiDrop*, then
  click a device.
- **AirPlay audio on Windows** – play the PC's sound on AirPlay speakers.
- **Command line on Windows** – `multidrop send/devices/receive/share` talk to
  the running app; the test suite now runs on Windows in CI.
- Fixes: AirPlay calls that time out are cancelled cleanly; the browser
  download stops reliably after it expires or after too many wrong PINs.

**Windows:** run `MultiDrop-Setup.exe` (per-user install, no admin rights) or
the portable `MultiDrop.exe` (Quick Share, LocalSend, browser download,
Explorer "Send to", AirPlay audio to speakers). MultiDrop opens in its own
window and keeps receiving in the notification area when you close it. On
first start allow Windows Firewall for private networks.

**Ubuntu/Debian:** `sudo apt install multidrop` after adding the APT repository
(see README), or `sudo apt install ./multidrop_*_all.deb`.

**Other Linux:** unpack `MultiDrop-linux-*.tar.gz` (or clone the repository) and run
`tools/install-desktop.sh --pin` – desktop app with Quick Share, LocalSend,
AirDrop (supported Wi-Fi card + omdrop-owl), AirPlay mirroring and audio.
The Python package (`.whl`/`.tar.gz`) contains the CLI and the background service.

Test status and limitations: see the README.
