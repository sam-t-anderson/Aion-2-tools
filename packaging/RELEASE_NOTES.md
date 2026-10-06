## Changes in 0.2.15

- Retain live combat history independently of the protocol engine's idle and zone resets. Nearby pulls within a configurable gap (default 10 seconds) form one combat segment. Choose Latest combat, an earlier combat, or Whole session; history remains through Stop/Start until Clear session or application exit. Export/upload preserves all retained combat segments, rather than only the currently selected enemy. History is bounded to 400,000 decoded records and 200 displayed/exported segments.
- Default to Self + Party filtering, with explicit Self only and All observed players options. Party membership comes from decoded rosters, not merely proximity. If identity is unavailable, preserve the captured records and display a warning rather than treat strangers as party members.
- Bind an explicitly entered character name to a unique observed identity, case-insensitively, and remember the input locally. This resolves the attached capture's `spirited` actor without guessing from highest damage.
- Read NPC spawn and HP metadata inside compressed packets and merge partial updates so known creature database IDs/names are not erased by a later partial record. Unknown types retain their entity ID instead of a guessed creature name.
- Separate Players and Enemies in Live Meter; select an enemy to see per-player damage against it. Keep the selected player stable as damage ranks change.
- Populate Accuracy with decoded crit, back/front, double, perfect, multi and parry rates. Populate Defense with incoming damage, hits, parries and attacker breakdowns. Accept NPC attack skill IDs directed at verified players. Hit chance, dodge and mitigation percentages remain unavailable when attempted attacks or pre-mitigation values are absent.
- Reuse loaded skill-image nodes during polling and use a fixed-size fallback when an icon is unavailable. Unchanged snapshots no longer rebuild the meter graph.
- Automatically save opted-in TCP diagnostics to a ZIP when capture stops, including capture errors, before another Start replaces the buffer and on normal Quit. Show the last saved file path and download link; repeated Stop calls reuse the saved archive. Earlier versions kept each recording in memory until Export, so recordings replaced by another Start cannot be recovered from that buffer.

Enter your character name in Live Meter before Start if you attach after login or a zone load. Stop and export before Clear session or quitting if you want to retain a file. The latest attached solo sample confirms self filtering and incoming NPC damage; a separate party sample is still needed to confirm roster decoding for that run.

## Changes in 0.2.14

- Choose Public, Unlisted or Private next to **Publish plan** in the website and desktop Raid Planner. Public plans appear in Browse plans; unlisted plans are accessible by link; private plans require the secret link. The choice is saved with each local plan. Publishing creates a new shared copy; existing links retain their original visibility.
- Connect desktop plan publishing and browsing to the share server configured in Settings, including its upload key.
- Replace Live Meter's separate Start/Stop controls with one button: yellow Start, red Stop while running.
- Make TCP diagnostics prominent, display the number of recorded payloads, and keep export results visible during polling. Export offers a direct ZIP download as well as the saved file path.
- Exclude Ethernet padding from TCP payloads so padding on ACK packets cannot advance reassembly or corrupt framed messages. Resume game-flow detection after an idle/disconnected socket, including a FIN/RST in the opposite direction. A stopped user capture produced 24 combat events in offline analysis after excluding its padding; live game capture still needs confirmation with this release.

Shared-link timeline playback is provided by Aion-2-tools-server 0.2.4. Update the server to get Play/Pause, Rewind, speed selection, the scrub bar and timed buff highlighting on existing `/p/<id>` links.

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
