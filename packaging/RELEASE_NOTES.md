## MultiDrop

Share files, your screen and audio with devices nearby – Linux and Windows.

**Windows:** run `MultiDrop-Setup.exe` (per-user install, no admin rights) or
the portable `MultiDrop.exe` (Quick Share, LocalSend, browser download,
Explorer "Send to"). On first start allow Windows Firewall for private networks.

**Ubuntu/Debian:** `sudo apt install multidrop` after adding the APT repository
(see README), or `sudo apt install ./multidrop_*_all.deb`.

**Other Linux:** unpack `MultiDrop-linux-*.tar.gz` (or clone the repository) and run
`tools/install-desktop.sh --pin` – desktop app with Quick Share, LocalSend,
AirDrop (supported Wi-Fi card + omdrop-owl), AirPlay mirroring and audio.
The Python package (`.whl`/`.tar.gz`) contains the CLI and the background service.

Test status and limitations: see the README.
