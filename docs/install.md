# Installing aion2calc

## For players: the desktop app

Download the file for your computer from the
[Releases page](https://github.com/sam-t-anderson/Aion-calc/releases/latest), or from the
**Download the app** page of a log server (`https://<log server>/download`):

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

**Unsigned builds.** The builds are not code-signed, so the first launch may need one extra click:

* Windows SmartScreen ("Windows protected your PC"): **More info → Run anyway**.
* macOS ("cannot be opened" or "Apple could not verify"): open **System Settings → Privacy &
  Security**, scroll down to the message about aion2calc and choose **Open Anyway**.

**Using it.** The first page has three steps: import your character, get gear advice, add your
fights. **Settings** holds the theme, the data folder (with buttons to open it), the log server
for sharing fights, the game-database update and the version. Closing the app window stops the
app (in a browser tab, it stops a few minutes after the last tab closes); **Quit** in the top bar
stops it at once. Starting it again while it runs brings the window back instead of starting a
second copy.

**Updating.** When the app's log server offers a newer version, a gold **Version … available** chip
appears in the top bar and links to the download page. Install the new version over the old one. Your data
is kept.

**Your data** stays on your computer, in `%LOCALAPPDATA%\aion2calc` on Windows and
`~/.aion2calc` on macOS and Linux (details in [app.md](app.md#where-your-data-is-saved)). If the
app fails to start, the reason is in `aion2calc.log` in that folder.

**Uninstalling.** Windows: **Settings → Apps → Installed apps → aion2calc → Uninstall** (or
delete the portable folder). Other systems: delete the app. Uninstalling keeps your data folder;
delete it too to remove everything.

## From source (developers)

```bash
git clone https://github.com/sam-t-anderson/Aion-calc && cd Aion-calc
python -m pip install -e ".[dev]"
python -m aion2calc app          # the same app in your browser; the CLI is in the README
python -m pytest -q
```

## Builds and releases (maintainers)

### Continuous integration

`.github/workflows/ci.yml` runs on every pull request and every push to `main`:

1. **Tests and lint**: pyflakes, the pytest suite, and a parse check of the app's JavaScript.
2. **Build** on Windows, macOS and Linux: PyInstaller builds the app, then
   `aion2calc --smoke-test` starts it, checks that the pages and API answer and the bundled
   optimizations are found, and solves a small integer program with the bundled solver. On
   Windows, Inno Setup then builds the installer and the portable zip. The files are attached to
   the run as artifacts (open the run in the **Actions** tab → **Artifacts**).
3. **Release**: on a push to `main` whose version has no release yet, or on a `v*` tag, the
   artifacts are published as GitHub release `v<version>` with
   [`packaging/RELEASE_NOTES.md`](../packaging/RELEASE_NOTES.md) as its notes.

### Publishing a new version

1. Raise the version in **both** `aion2calc/__init__.py` (`__version__`) and `pyproject.toml`.
2. Merge to `main`. CI builds, tests and publishes release `v<version>`. A merge that keeps the
   version builds and tests but publishes nothing.

To publish without changing `main`, push a tag instead: `git tag v0.2.1 && git push origin v0.2.1`.

### Getting the app to players

GitHub shows a **private** repository's releases only to people with access to the repository.
Two ways to reach everyone else:

* **Serve the files from your log server.** Copy the release files into its `downloads` folder.
  They are listed on `https://<log server>/download`, and the newest version is offered to app
  users in the top bar:

  ```bash
  sudo install -d -o a2logs -g a2logs /var/lib/aion2calc-logs/downloads
  sudo cp aion2calc-setup-0.2.0.exe aion2calc-0.2.0-*.zip aion2calc-0.2.0-linux.tar.gz \
    /var/lib/aion2calc-logs/downloads/
  ```

  File names must keep the version (`0.2.0`); the page reads the platform and version from them.
  Remove old versions when you no longer want to offer them.
* **Make the repository public** (**Settings → General → Danger Zone**). The Releases page then
  works for anyone.

### Presetting the log server

Set the repository variable `A2LOGS_PUBLIC_URL` (**Settings → Secrets and variables → Actions →
Variables**) to your log server's address, for example `https://logs.example.com`. Every build
then ships a `client.json`, and new users start with that server selected for sharing fights and
update checks. A `client.json` placed next to `aion2calc.exe` does the same for one copy:

```json
{"logserver_url": "https://logs.example.com", "visibility": "unlisted"}
```

`"key": "a2l_..."` may be added for people you trust to upload. The preset is used only when the
user has not chosen a server yet.

### Building locally

```bash
python -m pip install . pyinstaller
pyinstaller packaging/aion2calc.spec --noconfirm     # -> dist/aion2calc/ (and dist/aion2calc.app on macOS)
dist/aion2calc/aion2calc --smoke-test                # prints each check, exit code 0 when all pass
```

The Windows installer needs [Inno Setup 6](https://jrsoftware.org/isdl.php):

```bat
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DAppVersion=0.2.0 packaging\windows\aion2calc.iss
```

The installed app also takes `--port` (default 8765), `--no-browser` and `--no-sync` (skip the
launch-time database update).

PuLP's bundled CBC solver runs on Windows and Linux. On macOS, PuLP ships only an Intel CBC, so the
app uses HiGHS instead (the `highspy` package, installed automatically on macOS).
