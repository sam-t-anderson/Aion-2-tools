# Pet Tracker integration

How Aion 2 Calc works with [Pet Tracker](https://github.com/0Fox2Give/PetTracker), 0Fox2Give's separate
Windows program, used with its author's permission. This is the reference for contributors and for Pet
Tracker's author; players want [the app guide](app.md#pet-tracker).

## The parts

Pet Tracker is two programs:

* `PetTracker.Capture.exe`, the **worker**: it reads the game's traffic (through Npcap), keeps your collection
  in its data folder (`%LOCALAPPDATA%\PetTracker`, or the folder given with `--data`) and answers on a named pipe.
* `PetTracker.exe`, its **window**: its overlay, Find a pet, maps, merchant list and settings. It asks the worker
  for its state once a second, and starts the worker when it is not running.

Aion 2 Calc is a third client of the same worker, beside Pet Tracker's window:

```
PetTracker.Capture.exe ──pipe──┬── PetTracker.exe (Pet Tracker's window)
   (one per data folder)       └── Aion 2 Calc: aion2calc/app/pettracker.py ── local HTTP API ──┬── its Pet Tracker window (pet-overlay.html)
                                                                                                └── its Pet Tracker page (app.js)
```

Nothing of Pet Tracker is bundled, linked or changed. `aion2calc/app/pettracker.py` speaks the worker's protocol
and ports the rules Pet Tracker's overlay lists its pets by (`Activity.Select`, `Activity.ObservationNotice`,
`Activity.EmptyText`, `PetNames`, `PetStages`, `KnownRank`, `SoulsRemaining`, `FarmingGoals`), so both overlays
show the same pets. Both programs are GPL-3.0.

## The worker's pipe, as Aion 2 Calc uses it

**Name.** `PetTracker-` followed by the first 20 hex digits, in capitals, of SHA-256 over the UTF-8 bytes of
the user name (`Environment.UserName`: the account part of `GetUserNameExW(NameSamCompatible)`) followed by the
data folder's full path in capitals (`GetFullPath`, trailing separator trimmed, `ToUpperInvariant`). The data
folder is `LocalApplicationData\PetTracker` from the known folder, which can differ from the `LOCALAPPDATA`
variable, so the app tries both, the one that answered last first (`pipe_name`, `Client`).

**One command per connection.** Connect to `\\.\pipe\<name>`, write one JSON object on one line, read one line
back: the worker's view, or `{"Error": "..."}` when it refused the command. The worker serves one client at a
time, makes a fresh pipe after each answer, and closes as soon as its answer is written; the pipe only opens for
the user who started the worker. Aion 2 Calc gives a request 4 seconds, waits on a busy pipe within that time,
and takes a pipe still missing after 0.4 seconds to mean that no worker runs. It reads at most 8 MiB.

**Commands**, with Pet Tracker's own (case-sensitive) property names:

| Command | What it does |
|---|---|
| `{"Action": "status"}` | the view, nothing changed |
| `{"Action": "patch", "Patch": {"TrackerMode": "Nearby"}}` | change Pet Tracker settings by name; Aion 2 Calc sets `TrackerMode`, `HideMaxed` and `Visible` |
| `{"Action": "pin", "PetId": 1003}` / `"unpin"` | pin a pet to the top of the overlay, or unpin it (the worker answers *Pin limit reached…* past its limit) |
| `{"Action": "farming-goal", "PetId": 1004, "TargetRank": 3}` | a farming goal, rank 1 to 3; `null` clears it |
| `{"Action": "reset-farming"}` | start a new farming session |
| `{"Action": "exit"}` | save and stop (only a worker Aion 2 Calc started, when Pet Tracker's window is not running) |

**The view** is protocol 3; any other `Protocol` is refused with *This Pet Tracker speaks protocol N…*, since
the fields may have changed. Aion 2 Calc reads `Ready`, `CollectionSynced`, `Status`, `Detail`, `Character` or
`DetectedCharacter`, `Devices`, `Received`, `Dropped`, `Profile.Pets` (`Id`, `CatalogName`, `DisplayName`,
`Category`, `Level`, `LevelVerified`, `LevelDerivedFromSouls`, `Souls`, `Goal`, `CounterVerified`,
`EstimatedSouls`, `ProgressNeedsSync`, `TargetRank`, `CollectionImportedUtc`), `Recent` and `Nearby` (`PetId`,
`CreatureName`, `SeenUtc`, `IsNearby`), `Increase`, `Farming` (`StartedUtc`, `Incomplete`, `Pets`) and these
`Settings`: `TrackerMode`, `PinnedPetIds` (or the older `PinnedPetId`), `RowLimit`, `PinLimit`, `InactiveSeconds`,
`ExpireInactive`, `Sort`, `NearbyStaleSeconds`, `HideMaxed`, `Visible`, `Portraits`, `ProgressBars`, `Compact`,
`Accent`.

## Lifecycle

* **Start.** With *Use Pet Tracker* on, the app starts the worker (`PetTracker.Capture.exe --data <folder>`, no
  window) at launch and when the setting turns on, unless one runs, and at most once every 15 seconds. It starts
  none while Pet Tracker's own window runs (that window owns the worker: it starts it, and stops it to install an
  update), while Pet Tracker's updater runs (Velopack's `Update.exe` beside its installed versions, found by its
  path), or for 20 seconds after the window was last seen (since 0.2.338). If Windows refuses the start, the status
  says why; if the worker gives up at startup, the reason it wrote to `startup-error.json` in its data folder is
  shown.
* **Polling.** The view is fetched at most once every 0.8 seconds, shared by the overlay window (every second
  while connected) and the page; a failure is shared for as long, so a missing worker is not asked twice.
* **Stop.** When the app quits, or *Use Pet Tracker* turns off, a worker the app started is sent `exit`, unless
  Pet Tracker's window runs. A worker someone else started is left alone.
* **One overlay.** While Aion 2 Calc's Pet Tracker window is open, a running Pet Tracker's own overlay is hidden
  (`Visible: false`), and shown again when that window closes, Pet Tracker is turned off in the app, or the app
  quits. With the *Pet Tracker's own window* style the app shows it instead, launching `PetTracker.exe` when it
  is not running, and never a second copy (Pet Tracker allows one). A normal launch of Pet Tracker shows its
  overlay again by itself; one started `--minimized` keeps it hidden until it is shown from its tray icon.

## Pet Tracker's updates

Pet Tracker's own window updates it: it reads the same signed feed 30 seconds after it opens and every 6 hours,
announces an update from its tray icon, and installs it when the player chooses *Restart to update*, after saving
and stopping the worker (it never kills the worker to install). Velopack's updater then force-stops anything still
running from Pet Tracker's folder before it swaps the versions, so a worker another client started in that gap
would be killed without saving: hence the start rules above. Since 0.2.338 the app reads the feed too, while Pet
Tracker is on (at launch, then every 6 hours, an hour after a failed read), verified as for the install below, and
compares its newest version with the installed one: Velopack's `sq.version` beside an installer copy, or, for a copy
without one (from the older offline installer, or in a folder of the player's own), the file version in
`PetTracker.exe`'s Windows file properties, which Pet Tracker's build sets to its release (since 0.2.339).
`GET /api/pettracker` then carries `update`: `available`, `latest`, `installed`, `kind`, `checked` and `error`.
`POST /api/pettracker {"action": "update"}` opens Pet Tracker's window for its own updater (an installer copy),
installs the current release over a copy from the older offline installer, or says to download one for a copy in
a folder of the player's own; its `message` says what to do next.

## Installing Pet Tracker

`aion2calc/app/pettracker_setup.py`, run from Settings, the Pet Tracker page, or the installer's optional task
(`aion2calc.exe --install-pettracker`, never during a silent update):

1. Fetch `releases.win-stable.signed.json` from Pet Tracker's `updates` release (at most 2 MiB).
2. Verify its `Signature` (ECDSA P-256 over SHA-256, the 64-byte r‖s form) over the decoded `Payload` with the
   public key Pet Tracker's updater pins (checked in pure Python; no extra package).
3. Check that the payload names `PetTracker.Desktop` on `win-stable`, was published at most 5 minutes in the
   future, expires no more than 90 days after it was published and has not expired, and carries a 64-digit
   `InstallerSHA256`.
4. Download `PetTracker.Desktop-win-stable-Setup.exe` (at most 512 MiB) to the data folder's
   `downloads\pettracker`, and keep it only if its SHA-256 matches; then start it. It installs per user, needs no
   administrator rights and is deleted once it finishes.

## Aion 2 Calc's local API

The desktop app's local server (`127.0.0.1`), for its own pages; changes are refused from other computers.

`GET /api/pettracker` (add `?collection=1` for every pet) returns:

| Field | |
|---|---|
| `supported`, `enabled`, `installed` (`kind`, `folder`, `version`), `running` (`app`, `worker`, `updating`), `connected`, `problem`, `start`, `setup`, `update`, `source` | how Pet Tracker is doing |
| `status`, `detail`, `character`, `ready`, `synced`, `sync_notice`, `capture` | the worker's state |
| `rows`, `empty` | the overlay's rows, by Pet Tracker's rules, or what it says when it lists none |
| `options` | `mode`, `hide_maxed`, `sort`, `row_limit`, `pin_limit`, `pins`, `portraits`, `progress_bars`, `compact`, `accent`, `own_window_visible` |
| `session`, `summary`, `collection` | the farming session, collection counts, and (with `?collection=1`) every pet |

A row is `id`, `name`, `family`, `level`, `rank`, `rank_text`, `max`, `souls`, `goal`, `estimated`, `progress`,
`ratio`, `paused`, `remaining`, `pinned`, `notice`, `creature`, `goal_rank`, `goal_text` and `portrait`.

`GET /api/pettracker/portrait/<id>.png` serves a portrait from the installed Pet Tracker.

`POST /api/pettracker` takes `{"action": ...}`: `install`, `start`, `open` (Pet Tracker's window), `mode`
(`"value"`: `Recent` or `Nearby`), `hide_maxed` (`"value"`: true or false), `pin` (`"pet"`, `"value"`), `goal`
(`"pet"`, `"rank"`: 1 to 3 or null), `reset_session` or `update` (with a `message`), and returns the same as the
GET. Pet Tracker's refusals come back as `400 {"error": "..."}` in its own words.

Settings (`GET`/`POST /api/ui`): `pettracker_enabled`, `pettracker_overlay` (both off by default),
`pettracker_overlay_style` (`app` or `pettracker`), `pettracker_path` (empty, or a full folder path holding both
programs) and `overlay_pets_pos_x`/`_y`. The window is `/overlay?view=pets`; `POST /api/overlay
{"action": "hide", "view": "pets"}` hides it and turns its setting off.

The packaged app's smoke test (`aion2calc.exe --smoke-test`, run by CI on Windows) checks the pipe client against
pipes made the way the worker makes its own: a round trip, a worker that never answers, a busy pipe and a missing
worker (`pettracker.self_check`). It also reads its own program's path and file version, as the updater check and
the installed version do.

## What would make this sturdier upstream

Suggestions for Pet Tracker, none of them needed today:

* **A documented client contract.** The command and view shapes Aion 2 Calc relies on (above), kept stable within
  a protocol version, would let other tools follow Pet Tracker's releases without reading its source.
* **Showing its overlay from another client.** A `Visible: true` patch cannot show the overlay of a Pet Tracker
  started `--minimized` (its window keeps `StartHidden`); a command or setting that clears it would.
* **A session-only hide.** `Visible` is saved; a hide that lasts until the client that asked for it disconnects
  would need no putting back.
* **Changes pushed to clients.** Every client polls once a second; a long-poll or subscribe command would cut that
  traffic and the delay.
* **The portraits' location in the view.** Aion 2 Calc looks in the data folder and beside the program, where
  Pet Tracker's window looks.
* **A sign that an update is installing.** Other clients hold off starting the worker by watching for Pet Tracker's
  window and its updater's process; a lock file or an answer on the pipe saying an update is under way would
  replace that guess.
* **Opening its windows from another client.** A launch switch (or a pipe command) for Find a pet, Settings and
  its Updates page would let the app's buttons open them directly; today a second launch only shows *Pet Tracker
  is already running*, so the app points players to the tray icon.
