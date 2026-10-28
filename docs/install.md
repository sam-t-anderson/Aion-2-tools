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

**Optional: Pet Tracker.** The Windows installer offers *Download and install Pet Tracker by 0Fox2Give*,
unticked by default. [Pet Tracker](https://github.com/0Fox2Give/PetTracker) is a separate program that shows
your pet ranks and the souls you still need. Tick it and the installer downloads Pet Tracker's official
installer, checks it against the release its publisher signed, runs it, and turns Pet Tracker on in Aion 2 Calc.
It is skipped during silent updates, and greyed out when Pet Tracker is installed already. **Settings → Pet
Tracker** installs it later instead. See [Pet Tracker](app.md#pet-tracker).

**Signed builds.** The Windows installer and the app are code-signed ([code signing](code-signing.md)),
so Windows names their publisher. To check a download before you run it, compare its SHA-256 with the
values in the README ([verify your download](../README.md#verify-your-download)). The macOS build is not signed: if macOS says it "cannot be opened"
or "Apple could not verify" it, open **System Settings → Privacy & Security**, scroll down to the
message about aion2calc and choose **Open Anyway**.

### "Failed to load Python DLL"

If starting aion2calc shows **"Failed to load Python DLL ... `_internal\python312.dll`. LoadLibrary:
The specified module could not be found."**, the copy in `%LOCALAPPDATA%\Programs\aion2calc` has lost
its Python runtime. Either an update run with an installer older than 0.2.326 did not finish (it was
cancelled, an error was answered with Cancel, or the computer turned off) after it had deleted the old
runtime, or an antivirus removed the file. Download `aion2calc-setup-<version>.exe` from the
[Releases page](https://github.com/sam-t-anderson/Aion-2-tools/releases/latest) and run it. It installs
over the broken copy, and your data in `%LOCALAPPDATA%\aion2calc` is kept. If the message comes back,
look for files from that folder in your antivirus's quarantine (**Windows Security → Virus & threat
protection → Protection history**).

From 0.2.326 on, an update that does not finish puts back the copy it was replacing, so the app you had
still starts. Setup also writes a log of each run to `%TEMP%` (`Setup Log <date> #<n>.txt`), which says
what went wrong.

### Settings says "could not check for updates"

If the version line in **Settings** reads **could not check for updates (URLError: … CERTIFICATE_VERIFY_FAILED
… unable to get issuer certificate)**, your copy is older than 0.2.345 and cannot see new releases, so it
will not update itself. Download `aion2calc-setup-<version>.exe` from the
[Releases page](https://github.com/sam-t-anderson/Aion-2-tools/releases/latest) and run it once: it
installs over your copy and keeps your data in `%LOCALAPPDATA%\aion2calc`.

Versions before 0.2.345 checked GitHub's certificate against their own copy of the certificates stored in
Windows. Windows downloads some root certificates only the first time it needs them, so on some computers
that copy was missing the one the check led to, although the browser opened GitHub fine. From 0.2.345 the
app asks Windows to check each certificate, as the browser does, with Mozilla's root certificates as a
second check, so the update check and the rest of the app (uploads, the log server, character imports and
game data) work wherever the browser does.

**Using it.** The first page has three steps: import your character, get gear advice, add your
fights. **Settings** holds the theme, the data folder (with buttons to open it), the log server
for sharing fights, the game-database update and the version. Closing the app window stops the
app (in a browser tab, it stops a few minutes after the last tab closes); **Quit** in the top bar
stops it at once. Starting it again while it runs brings the window back instead of starting a
second copy.

**Updating.** When a newer release is out, the app downloads it quietly in the background (0.2.353;
before, it asked in a popup). A small bar at the bottom left shows the download's progress, then
**Update ready: version …** with **Update now**, which closes the app and opens the installer, and
**Update when the app closes**, ticked unless you untick it: closing the app then installs the update
quietly, and the app opens on the new version next time. A release that comes out while the app is
open replaces the waiting one, so the newest release always installs, however many versions behind
you are, and the versions in between are never installed one by one. The app checks the Releases
page when it starts or a window opens, then hourly; a check that fails (no network yet right after
Windows starts, say) is retried within a couple of minutes. **Settings → App & data → Updates** turns
the background download and the install on close on or off, and **Settings → Version** shows what the
last check found, with **Check now** and **Update now**. Installing puts the new version over the old
one. Your data is kept.

**Your data** stays on your computer, in `%LOCALAPPDATA%\aion2calc` on Windows and
`~/.aion2calc` on macOS and Linux (details in [app.md](app.md#where-your-data-is-saved)). If the
app fails to start, the reason is in `aion2calc.log` in that folder. When Windows instead says it
failed to load the Python DLL, see [above](#failed-to-load-python-dll).

**Uninstalling.** Windows: **Settings → Apps → Installed apps → aion2calc → Uninstall** (or
delete the portable folder). Other systems: delete the app. Uninstalling keeps your data folder;
delete it too to remove everything.

## Developers and maintainers

Running from source, the command-line interface, building the installer, CI, releasing, code
signing and presetting the log server are in [`cli.md`](cli.md).
