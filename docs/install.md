# Installing aion2calc

## For players: the desktop app

Download the file for your computer from the
[Releases page](https://github.com/sam-t-anderson/Aion-2-tools/releases/latest):

| Your computer | File | Then |
|---|---|---|
| **Windows** (recommended) | `aion2calc-setup-<version>.exe` | Run it. It installs for your user only (no admin rights) and adds **aion2calc** to the Start menu, plus an optional desktop shortcut |
| Windows, no install | `aion2calc-<version>-windows-portable.zip` | Unzip anywhere (a USB stick works), run `aion2calc.exe` |
| macOS | `aion2calc-<version>-macos.zip` | Unzip, move `aion2calc.app` to Applications, open it |
| Linux | `aion2calc-<version>-linux.tar.gz` | `tar xzf aion2calc-*-linux.tar.gz && ./aion2calc/aion2calc` |

No Python and no command line are needed. The app opens in its own window (Edge or Chrome in app
mode; without either, your default browser) and follows your computer's light or dark mode. You
can also pick a theme with the ◐ button in the top bar or on the **Settings** page.

![Dark theme](screenshots/app_dark.png)
![Light theme](screenshots/app_light.png)

**Unsigned builds.** The builds are not code-signed yet ([plan](code-signing.md)), so the first
launch may need one extra click:

* Windows SmartScreen ("Windows protected your PC"): **More info → Run anyway**.
* macOS ("cannot be opened" or "Apple could not verify"): open **System Settings → Privacy &
  Security**, scroll down to the message about aion2calc and choose **Open Anyway**.

**Using it.** The first page has three steps: import your character, get gear advice, add your
fights. **Settings** holds the theme, the data folder (with buttons to open it), the log server
for sharing fights, the game-database update and the version. Closing the app window stops the
app (in a browser tab, it stops a few minutes after the last tab closes); **Quit** in the top bar
stops it at once. Starting it again while it runs brings the window back instead of starting a
second copy.

**Updating.** When a newer release is out, a gold **Version … available** chip appears in the top
bar and links to its download page (the app checks the Releases page every few hours). Install the
new version over the old one. Your data is kept.

**Your data** stays on your computer, in `%LOCALAPPDATA%\aion2calc` on Windows and
`~/.aion2calc` on macOS and Linux (details in [app.md](app.md#where-your-data-is-saved)). If the
app fails to start, the reason is in `aion2calc.log` in that folder.

**Uninstalling.** Windows: **Settings → Apps → Installed apps → aion2calc → Uninstall** (or
delete the portable folder). Other systems: delete the app. Uninstalling keeps your data folder;
delete it too to remove everything.

## Developers and maintainers

Running from source, the command-line interface, building the installer, CI, releasing, code
signing and presetting the log server are in [`cli.md`](cli.md).
