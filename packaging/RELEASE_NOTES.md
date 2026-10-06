## Download

| Your computer | File |
|---|---|
| **Windows** (recommended) | `aion2calc-setup-<version>.exe`: run it, then start **aion2calc** from the Start menu |
| Windows, no install | `aion2calc-<version>-windows-portable.zip`: unzip anywhere, run `aion2calc.exe` |
| macOS | `aion2calc-<version>-macos.zip`: unzip and open `aion2calc.app` (see below the first time) |
| Linux | `aion2calc-<version>-linux.tar.gz`: unpack, run `aion2calc/aion2calc` |

## Live Meter capture setup

The built-in A2Tools Live Meter captures the game's network traffic and needs the operating
system's packet-capture support. On Windows, the installer offers an unchecked **Download and
install Npcap for Live Capture** choice. Selecting it fetches the newest official Npcap installer
from `npcap.com`; select **WinPcap API-compatible Mode** during Npcap setup. The Live Meter also
asks before downloading Npcap if it is still missing.

macOS already includes its packet-capture framework. Linux uses the distribution's `libpcap`
package; install it with your package manager and grant the account permission to capture packets
before using Live Capture. The desktop app explains the missing capture prerequisite instead of
silently attempting a privileged installation.

The compact overlay is a single transparent, always-on-top window. It follows the Aion 2 game
window when it is running, closes with aion2calc, and its opacity slider no longer moves the overlay.

The app opens in its own window (Edge or Chrome app mode, or your browser) and follows your system's
light or dark mode. It needs no Python and no command line. Your data stays on your computer, in
`%LOCALAPPDATA%\aion2calc` on Windows (`~/.aion2calc` on macOS and Linux). Updating or uninstalling
the app keeps it.

The builds are not code-signed, so the first launch may need one extra click. Windows SmartScreen
("Windows protected your PC"): choose **More info → Run anyway**. macOS ("cannot be opened"): open
**System Settings → Privacy & Security** and choose **Open Anyway** next to the aion2calc message.

[Code signing policy](https://github.com/sam-t-anderson/Aion-2-tools/blob/main/docs/code-signing.md). Installing and updating:
[docs/install.md](https://github.com/sam-t-anderson/Aion-2-tools/blob/main/docs/install.md).
