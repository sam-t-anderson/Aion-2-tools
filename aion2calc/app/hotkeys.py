"""Global (system-wide) hotkeys for the overlay and meter.

The parsing and validation here are platform-independent and fully tested; the
actual key registration is Windows-only (``RegisterHotKey`` on a dedicated
message-loop thread) and a no-op elsewhere, so a bound key works even while the
game has focus. Dispatch runs in-process: the launcher hands this module a map
of ``action -> callable`` so a hotkey calls the same code the UI does, with no
network hop.

Default is no bindings, so nothing changes until the user assigns keys in
Settings, but for the Hidden Cube radar's two learn steps: Ctrl+1 and Ctrl+2
while the radar is on (``RADAR_DEFAULTS``). Only the actions in ``ACTIONS`` can
be bound, and every combo is validated, so a settings file can never register an
arbitrary or unparseable key.
"""
from __future__ import annotations

import logging
import sys
import threading

_LOG = logging.getLogger(__name__)

# Bindable actions -> the human label shown in Settings. Keep in sync with the
# dispatch map the launcher builds and the Settings UI in app.js.
ACTIONS: dict[str, str] = {
    "toggle_overlay": "Show / hide the overlay",
    "toggle_meter": "Start / stop the meter",
    "clear_meter": "Clear the meter (battle reset)",
    "toggle_click_through": "Toggle click-through",
    "toggle_party_overlay": "Show / hide the Party-DPS overlay",
    "open_app": "Open the app window",
    "open_settings": "Open the Settings page",
    "toggle_events": "Show / hide overlay event notifications",
    "toggle_field_bosses": "Show / hide field-boss timers on the overlay",
    "toggle_combat_assist": "Show / hide combat assist (skill cooldowns, break gauge)",
    "toggle_cube_radar": "Turn the Hidden Cube radar on / off",
    "radar_learn_background": "Hidden Cube radar: learn the background (step 1)",
    "radar_learn_cube": "Hidden Cube radar: learn the cube's sound (step 2)",
    "screenshot_lock": "Screenshot lock (freeze the overlay)",
    "quit": "Exit Aion 2 Calc",
}

#: The radar's learn steps, pressed in the game beside a cube: bound to these while the radar is on and
#: never while it is off, so the keys reach the game then. Settings can rebind them or clear them ("").
RADAR_DEFAULTS = {"radar_learn_background": "Ctrl+1", "radar_learn_cube": "Ctrl+2"}

#: The overlay's combat-assist parts, shown and hidden together by ``toggle_combat_assist``.
COMBAT_ASSIST = ("overlay_show_cooldowns", "overlay_show_break_gauge")


def combat_assist_changes(ui: dict, hidden: list) -> dict:
    """The settings ``toggle_combat_assist`` writes: every combat-assist part off when any is on
    (``hidden`` remembers which were on), else the parts it last hid back on, or all of them when it
    has hidden none since the app started."""
    shown = [key for key in COMBAT_ASSIST if ui.get(key)]
    if shown:
        hidden[:] = shown
        return {key: False for key in COMBAT_ASSIST}
    return {key: True for key in (hidden or COMBAT_ASSIST)}


# Modifier name -> RegisterHotKey MOD_* flag.
_MODS = {"ctrl": 0x0002, "control": 0x0002, "alt": 0x0001, "shift": 0x0004,
         "win": 0x0008, "super": 0x0008, "cmd": 0x0008, "meta": 0x0008}
_MOD_NOREPEAT = 0x4000

# A few named keys beyond the letters/digits/function keys computed below.
_NAMED_VK = {"space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B,
             "escape": 0x1B, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
             "insert": 0x2D, "ins": 0x2D, "home": 0x24, "end": 0x23,
             "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28,
             "left": 0x25, "right": 0x27, "`": 0xC0, "-": 0xBD, "=": 0xBB,
             "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE,
             "/": 0xBF, "\\": 0xDC}


def _key_vk(token: str) -> int | None:
    """The Windows virtual-key code for a single key token, or None if unknown."""
    t = token.strip().lower()
    if not t:
        return None
    if len(t) == 1 and "a" <= t <= "z":
        return ord(t.upper())
    if len(t) == 1 and "0" <= t <= "9":
        return ord(t)
    if t[0] == "f" and t[1:].isdigit():
        n = int(t[1:])
        if 1 <= n <= 24:
            return 0x70 + (n - 1)
    return _NAMED_VK.get(t)


def parse_combo(combo: str):
    """Parse "Ctrl+Shift+M" into (modifier flags, virtual-key code), or None when
    the string is empty or not a valid single-key-plus-modifiers chord. A chord
    must have exactly one non-modifier key; a bare modifier is rejected so it
    can't swallow a plain Ctrl press."""
    if not isinstance(combo, str):
        return None
    tokens = [p for p in (t.strip() for t in combo.split("+")) if p]
    if not tokens:
        return None
    mods, key_vk = 0, None
    for tok in tokens:
        low = tok.lower()
        if low in _MODS:
            mods |= _MODS[low]
        else:
            if key_vk is not None:
                return None            # two non-modifier keys: not a valid chord
            key_vk = _key_vk(tok)
            if key_vk is None:
                return None
    if key_vk is None:
        return None                    # modifiers only
    return mods, key_vk


def valid_combo(combo: str) -> bool:
    return parse_combo(combo) is not None


def clean_hotkeys(value) -> dict:
    """Validate a {action: combo} mapping: only known actions, each a parseable
    combo. An empty/false combo unbinds the action (dropped). Raises ValueError
    on an unknown shape so a bad settings file is rejected rather than trusted."""
    if not isinstance(value, dict):
        raise ValueError("hotkeys must be a mapping of action to key combo")
    out: dict[str, str] = {}
    for action, combo in value.items():
        if action not in ACTIONS:
            continue                   # unknown action: ignore, don't trust
        if combo in (None, "", False):
            if action in RADAR_DEFAULTS:
                out[action] = ""       # kept: it clears the default binding
            continue                   # explicit unbind
        if not isinstance(combo, str) or not valid_combo(combo):
            raise ValueError(f"hotkey for {action} is not a valid key combo")
        out[action] = combo
    return out


def effective(ui: dict) -> dict:
    """The bindings to register from the settings: the saved ones, and while the Hidden Cube radar is
    on its learn steps on their saved keys or ``RADAR_DEFAULTS`` (a saved "" leaves one unbound, and a
    default another action already uses is skipped)."""
    saved = ui.get("hotkeys") if isinstance(ui.get("hotkeys"), dict) else {}
    out = {action: combo for action, combo in saved.items() if combo and action not in RADAR_DEFAULTS}
    if ui.get("radar_enabled") is True:
        taken = {str(combo).lower() for combo in out.values()}
        for action, default in RADAR_DEFAULTS.items():
            combo = saved.get(action, default)
            if combo and (action in saved or default.lower() not in taken):
                out[action] = combo
                taken.add(combo.lower())
    return out


class HotkeyManager:
    """Registers the configured global hotkeys on Windows and calls the matching
    dispatch callable when one fires. ``get_config`` returns the current
    {action: combo} map (re-read periodically so Settings changes take effect);
    ``dispatch`` maps an action name to a zero-arg callable. A no-op off Windows
    or when the platform calls are unavailable."""

    def __init__(self, get_config, dispatch: dict):
        self._get_config = get_config
        self._dispatch = dispatch
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if sys.platform != "win32" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="global-hotkeys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # --- Windows implementation -------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - requires a real Windows message loop
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        WM_HOTKEY, WM_TIMER = 0x0312, 0x0113
        TIMER_ID = 1
        registered: dict[int, str] = {}          # hotkey id -> action
        current: dict[str, str] = {}

        def reregister():
            nonlocal current
            config = {}
            try:
                config = self._get_config() or {}
            except Exception:
                config = {}
            if config == current:
                return
            for hid in list(registered):
                user32.UnregisterHotKey(None, hid)
            registered.clear()
            hid = 1
            for action, combo in config.items():
                parsed = parse_combo(combo)
                if not parsed or action not in self._dispatch:
                    continue
                mods, vk = parsed
                if user32.RegisterHotKey(None, hid, mods | _MOD_NOREPEAT, vk):
                    registered[hid] = action
                    hid += 1
                else:
                    _LOG.warning("Could not register hotkey %s for %s", combo, action)
            current = dict(config)

        reregister()
        # A periodic timer wakes the GetMessage loop so Settings changes re-register.
        user32.SetTimer(None, TIMER_ID, 1500, None)
        msg = wintypes.MSG()
        while not self._stop.is_set():
            got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if got in (0, -1):                   # WM_QUIT or error
                break
            if msg.message == WM_HOTKEY:
                action = registered.get(int(msg.wParam))
                fn = self._dispatch.get(action) if action else None
                if fn:
                    try:
                        fn()
                    except Exception:
                        _LOG.exception("Hotkey action %s failed", action)
            elif msg.message == WM_TIMER:
                reregister()
        for hid in list(registered):
            user32.UnregisterHotKey(None, hid)
        user32.KillTimer(None, TIMER_ID)
