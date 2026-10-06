## Changes in 0.2.13

- Close the desktop's dedicated Chromium profile even when its launcher handed the window to an existing browser process. Explicit Quit/update exits the packaged process after server/capture cleanup so solver exit hooks cannot block the installer. Update helper logs now record readiness immediately.
- Keep the two most recent update packages, including the staged installer; retain helper scripts and logs for troubleshooting.
- Disable and uncheck the Npcap install task when its Windows service already exists, and skip launching its installer if detected at the final install step.
- Remove color-key hit-test transparency from the overlay. The compact dark host uses window alpha, so tabs, dragging and the opacity slider remain interactive.
- Add optional bounded TCP diagnostic recording before game-port selection and an **Export capture diagnostics** button. ZIPs are saved under the data folder's `diagnostics` directory. Nothing is uploaded automatically. Use this to investigate TCP packets arriving without recognized combat events.

To collect a packet sample: in Live Meter enable **Record TCP payloads for diagnostics** before Start, fight briefly, press Stop, then **Export capture diagnostics**. The newest 4 MiB / 4096 records are retained. Raw payloads may include names, IP addresses and other captured traffic; review before attaching. Existing application logs do not contain TCP payloads.

## Changes in 0.2.12

- Live Capture monitors all available adapters in Auto mode and detects the game port from combat traffic. Adapter names and packet/event counters explain whether traffic is reaching the decoder. A fixed port can still be selected by turning off detection.
- Custom decoders are imported from a trusted `.py` file. Combat variant IDs now map to base skill icons, with graceful display when an asset is unavailable.
- The overlay keeps its tabs and opacity controls stable, fits its content without scrollbars, clears the native Windows host background and hides its taskbar entry. It follows the AION 2 executable specifically and preserves your dragged position. Opening it again reuses the existing overlay.
- Stop cancels capture and replay; Quit closes the app and overlay. Windows updates acknowledge the detached helper before closing, wait for the app to exit, and verify downloaded installer size/digest when provided. Helper failure details are saved under the data folder's `updates` directory.
- Skills hotbar and Macro & rotation now share named skills, icons and key bindings. Charged skills stay manual in both macro layouts; estimates assume you hold their own key to charge. The optimizer spends remaining skill points on reachable legal levels, including utility skills.
- Optimized character allocations and rotation are submitted anonymously to the configured server. It recomputes DPS against the current Planner and stored preset using the same level-45 median gear and budgets (203 skill / 30 stigma / 360 Daevanion), stores only improvements, and discards other submissions. Character names, loadout paths, gear and claimed scores are excluded. New launches refresh class presets while retaining an offline cache.
- The desktop opens maximized with roomier content, uses **Aion 2 Calc** branding and prompts for available updates on launch. Windows Npcap setup is selected by default.

Validation includes unit/integration tests and packaged startup checks in CI. Actual game capture and visual transparency still need confirmation on a machine running AION 2; this development environment could not render a minimal WebView2 test window.

## Download

| Your computer | File |
|---|---|
| **Windows** (recommended) | `aion2calc-setup-<version>.exe`: run it, then start **Aion 2 Calc** from the Start menu |
| Windows, no install | `aion2calc-<version>-windows-portable.zip`: unzip anywhere, run `aion2calc.exe` |
| macOS | `aion2calc-<version>-macos.zip`: unzip and open `aion2calc.app` (see below the first time) |
| Linux | `aion2calc-<version>-linux.tar.gz`: unpack, run `aion2calc/aion2calc` |

## Live Meter capture setup

The built-in A2Tools Live Meter captures the game's network traffic and needs the operating
system's packet-capture support. On Windows, the installer offers a preselected **Download and
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
