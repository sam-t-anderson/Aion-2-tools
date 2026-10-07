"""A small cross-platform Tk desktop replay meter."""

from __future__ import annotations

import json
import os
import queue
import threading
import ctypes
import time
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .engine import MeterEngine
from .history import LocalStore
from .ping import system_perf_clock
from .replay import parse_timestamp_ms, read_capture


class MeterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("A2Tools DPS Meter — Python")
        self.root.geometry("780x520")
        self.root.minsize(560, 360)
        self.engine = MeterEngine()
        self.store = LocalStore()
        self.queue: queue.Queue = queue.Queue()
        self.replay_generation = 0
        self.capture_generation = 0
        self.expanded = True
        self._drag_origin = None
        self._build()
        self._hotkey_registered = False
        if os.name == "nt":
            self._hotkey_registered = bool(ctypes.windll.user32.RegisterHotKey(None, 0xA2, 0x0002 | 0x0004, 0x7A))
            if self._hotkey_registered:
                self.root.after(100, self._poll_overlay_hotkey)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll)

    def _build(self) -> None:
        bar = self.toolbar = ttk.Frame(self.root, padding=10)
        bar.pack(fill="x")
        ttk.Button(bar, text="Open replay…", command=self.open_replay).pack(side="left")
        ttk.Button(bar, text="Save fight", command=self.save_fight).pack(side="left", padx=8)
        ttk.Button(bar, text="History", command=self.show_history).pack(side="left")
        ttk.Button(bar, text="Start live", command=self.start_capture).pack(side="left", padx=8)
        ttk.Button(bar, text="Stop", command=self.stop_capture).pack(side="left")
        ttk.Button(bar, text="Compact overlay", command=self.toggle_compact).pack(side="left", padx=8)
        capture_bar = self.capture_bar = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        capture_bar.pack(fill="x")
        ttk.Label(capture_bar, text="Game server port").pack(side="left")
        self.capture_port = tk.StringVar(value=str(self.store.setting("serverPort", 50349)))
        ttk.Entry(capture_bar, textvariable=self.capture_port, width=7).pack(side="left", padx=(5, 14))
        ttk.Label(capture_bar, text="Capture interface (optional)").pack(side="left")
        self.capture_interface = tk.StringVar(value=self.store.setting("captureInterface", ""))
        ttk.Entry(capture_bar, textvariable=self.capture_interface, width=22).pack(side="left", padx=5)
        ttk.Label(capture_bar, text="All-target window (sec)").pack(side="left", padx=(12, 4))
        self.all_targets_window = tk.StringVar(value=str(self.store.setting("allTargetsWindowSec", 120)))
        ttk.Entry(capture_bar, textvariable=self.all_targets_window, width=6).pack(side="left")
        self.identity_bar = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        self.identity_bar.pack(fill="x")
        ttk.Label(self.identity_bar, text="Your character (optional)").pack(side="left")
        self.character_name = tk.StringVar(value=self.store.setting("localCharacterName", ""))
        character_entry = ttk.Entry(self.identity_bar, textvariable=self.character_name, width=24)
        character_entry.pack(side="left", padx=6)
        character_entry.bind("<FocusOut>", lambda _event: self._save_character_name())
        character_entry.bind("<Return>", lambda _event: self._save_character_name())
        ttk.Label(bar, text="Theme:").pack(side="left", padx=(10, 4))
        self.theme = tk.StringVar(value=self.store.setting("theme", "dark"))
        theme_box = ttk.Combobox(bar, textvariable=self.theme, state="readonly", width=8,
                                 values=("dark", "light"))
        theme_box.pack(side="left")
        theme_box.bind("<<ComboboxSelected>>", lambda _event: self._apply_theme())
        ttk.Label(bar, text="Target mode:").pack(side="left", padx=(20, 4))
        self.mode = tk.StringVar(value=self.store.setting("targetMode", "bossTargets"))
        mode_box = ttk.Combobox(bar, textvariable=self.mode, state="readonly", width=16,
                                values=("bossTargets", "mostDamage", "mostRecent", "lastHitByMe", "allTargets", "trainTargets"))
        mode_box.pack(side="left")
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self.store.set_setting("targetMode", self.mode.get()))
        self.topmost = tk.BooleanVar(value=self.store.setting("alwaysOnTop", True))
        ttk.Checkbutton(bar, text="Always on top", variable=self.topmost, command=self._set_topmost).pack(side="right")
        self._set_topmost()
        self.opacity = tk.DoubleVar(value=self.store.setting("opacity", 1.0))
        ttk.Label(bar, text="Opacity").pack(side="right", padx=(6, 2))
        ttk.Scale(bar, from_=0.55, to=1.0, variable=self.opacity, command=self._set_opacity, length=70).pack(side="right")
        self.clickthrough = tk.BooleanVar(value=self.store.setting("clickThrough", False))
        ttk.Checkbutton(bar, text="Click-through", variable=self.clickthrough, command=self._set_clickthrough).pack(side="right", padx=5)
        self.status = tk.StringVar(value="Open a packet capture replay to begin")
        self.status_label = ttk.Label(self.root, textvariable=self.status, padding=(10, 0))
        self.status_label.pack(fill="x")
        self.ping_label = ttk.Label(self.root, text="Ping: —", padding=(10, 0))
        self.ping_label.pack(anchor="e")
        self.title_label = ttk.Label(self.root, text="No combat data", font=("Segoe UI", 16, "bold"), padding=10)
        self.title_label.pack(fill="x")
        self.title_label.bind("<ButtonPress-1>", self._drag_start)
        self.title_label.bind("<B1-Motion>", self._drag_move)
        self.chart = tk.Canvas(self.root, height=86, background="#171a20", highlightthickness=0)
        self.chart.pack(fill="x", padx=10)
        self.hp_bar = tk.Canvas(self.root, height=18, background="#242a32", highlightthickness=0)
        self.hp_bar.pack(fill="x", padx=10, pady=(5, 0))
        columns = ("player", "job", "level", "gear", "power", "damage", "dps", "share")
        self.table = ttk.Treeview(self.root, columns=columns, show="headings")
        for key, title, width in (("player", "Player", 180), ("job", "Class", 100),
                                  ("level", "Lvl", 48), ("gear", "Gear", 72), ("power", "Power", 72),
                                  ("damage", "Damage", 110), ("dps", "DPS", 90), ("share", "Share", 70)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor="w" if key in ("player", "job") else "e")
        self.table.pack(fill="both", expand=True, padx=10, pady=10)
        self.table.bind("<<TreeviewSelect>>", self._actor_selected)
        self.skills = tk.Text(self.root, height=7, wrap="none", state="disabled")
        self.skills.pack(fill="x", padx=10, pady=(0, 10))
        self.capture_stop = threading.Event()
        self.capture_thread = None
        self.current_snapshot = None
        self.selected_actor_id = None
        self._set_opacity(self.opacity.get())
        if os.name == "nt" and self.clickthrough.get():
            self._set_clickthrough()
        self._apply_theme()

    def _set_opacity(self, value) -> None:
        alpha = min(1.0, max(0.55, float(value)))
        try:
            self.root.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        self.store.set_setting("opacity", alpha)

    def _apply_theme(self) -> None:
        dark = self.theme.get() == "dark"
        background, foreground = ("#171a20", "#e6eaf0") if dark else ("#f3f5f8", "#17202c")
        chart_bg = "#171a20" if dark else "#e3e8ef"
        self.root.configure(background=background)
        self.chart.configure(background=chart_bg)
        self.hp_bar.configure(background="#242a32" if dark else "#d4dae3")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=background, foreground=foreground,
                        fieldbackground=background, rowheight=25)
        style.configure("Treeview.Heading", background="#27303c" if dark else "#dbe2eb",
                        foreground=foreground)
        self.theme.set("dark" if dark else "light")
        self.store.set_setting("theme", self.theme.get())

    def _set_clickthrough(self) -> None:
        enabled = bool(self.clickthrough.get())
        if os.name != "nt":
            self.clickthrough.set(False)
            messagebox.showinfo("Click-through", "Click-through window mode is currently available on Windows only.")
            return
        try:
            hwnd = self.root.winfo_id()
            user32 = ctypes.windll.user32
            if hasattr(user32, "GetWindowLongPtrW"):
                get_long, set_long = user32.GetWindowLongPtrW, user32.SetWindowLongPtrW
                get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
                get_long.restype = ctypes.c_ssize_t
                set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
                set_long.restype = ctypes.c_ssize_t
            else:
                get_long, set_long = user32.GetWindowLongW, user32.SetWindowLongW
                get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
                get_long.restype = ctypes.c_long
                set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
                set_long.restype = ctypes.c_long
            ex_style = get_long(hwnd, -20)
            transparent, layered = 0x20, 0x80000
            if enabled:
                ex_style |= transparent | layered
            else:
                ex_style &= ~transparent
            set_long(hwnd, -20, ex_style)
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                             ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.SetWindowPos.restype = wintypes.BOOL
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0027)
            self.store.set_setting("clickThrough", enabled)
        except Exception as exc:
            self.clickthrough.set(False)
            messagebox.showerror("Click-through failed", str(exc))

    def _poll_overlay_hotkey(self) -> None:
        if not self._hotkey_registered:
            return
        msg = wintypes.MSG()
        user32 = ctypes.windll.user32
        while user32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 0x0001):
            if msg.wParam == 0xA2:
                self.clickthrough.set(not self.clickthrough.get())
                self._set_clickthrough()
        self.root.after(100, self._poll_overlay_hotkey)

    def _on_close(self) -> None:
        self.capture_stop.set()
        if os.name == "nt" and self._hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(None, 0xA2)
        self.capture_generation += 1
        self.replay_generation += 1
        self.root.destroy()

    def toggle_compact(self) -> None:
        if self.expanded:
            self.toolbar.pack_forget()
            self.capture_bar.pack_forget()
            self.identity_bar.pack_forget()
            self.status_label.pack_forget()
            self.ping_label.pack_forget()
            self.chart.pack_forget()
            self.table.pack_forget()
            self.skills.pack_forget()
            self.root.minsize(300, 70)
            self.root.geometry("380x80")
        else:
            self.toolbar.pack(fill="x", before=self.title_label)
            self.capture_bar.pack(fill="x", after=self.toolbar)
            self.identity_bar.pack(fill="x", after=self.capture_bar)
            self.status_label.pack(fill="x", before=self.title_label)
            self.ping_label.pack(anchor="e", before=self.title_label)
            self.chart.pack(fill="x", padx=10, after=self.title_label)
            self.table.pack(fill="both", expand=True, padx=10, pady=10)
            self.skills.pack(fill="x", padx=10, pady=(0, 10))
            self.root.minsize(560, 360)
            self.root.geometry("780x520")
        self.expanded = not self.expanded

    def _drag_start(self, event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event) -> None:
        if self._drag_origin:
            self.root.geometry(f"+{event.x_root - self._drag_origin[0]}+{event.y_root - self._drag_origin[1]}")

    def _set_topmost(self) -> None:
        self.root.attributes("-topmost", bool(self.topmost.get()))
        self.store.set_setting("alwaysOnTop", bool(self.topmost.get()))

    def open_replay(self) -> None:
        if self.capture_thread and self.capture_thread.is_alive():
            messagebox.showinfo("Replay unavailable", "Stop live capture before opening a replay.")
            return
        path = filedialog.askopenfilename(title="Open A2Tools packet replay", filetypes=(("Packet captures", "*.txt *.log"), ("All files", "*.*")))
        if not path:
            return
        self.replay_generation += 1
        generation = self.replay_generation
        self.engine = self._new_engine()
        self.status.set(f"Reading {path}")
        threading.Thread(target=self._load, args=(path, self.engine, generation), daemon=True).start()

    def _load(self, path: str, engine: MeterEngine, generation: int) -> None:
        try:
            records = 0
            for record in read_capture(path):
                if generation != self.replay_generation:
                    return
                records += 1
                stamp = parse_timestamp_ms(record.timestamp)
                engine.consume(record.payload, stamp, record.stream_key)
                for fight in engine.drain_completed_fights():
                    self.queue.put(("replay_auto_save", generation, fight))
                if records % 250 == 0:
                    self.queue.put(("replay_progress", generation, records))
            if generation == self.replay_generation:
                self.queue.put(("replay_done", generation, records))
        except Exception as exc:
            self.queue.put(("replay_error", generation, str(exc)))

    def _poll(self) -> None:
        changed = False
        try:
            while True:
                item = self.queue.get_nowait()
                kind, value = item[0], item[1] if len(item) > 1 else None
                if kind.startswith("replay_") and value != self.replay_generation:
                    continue
                if kind == "replay_progress":
                    self.status.set(f"Replayed {item[2]:,} capture records…")
                elif kind == "packet":
                    _, generation, stream, payload, stamp = item
                    if generation != self.capture_generation:
                        continue
                    self.engine.consume(payload, stamp, stream)
                    for fight in self.engine.drain_completed_fights():
                        self.store.save_fight(fight)
                        self.status.set(f"Saved completed boss fight: {fight['bossName']}")
                    changed = True
                elif kind == "stream_reset":
                    if value != self.capture_generation:
                        continue
                    self.engine.reset_stream(item[2])
                    self.status.set("Recovered a lossy TCP boundary; earlier capture is incomplete")
                elif kind == "replay_auto_save":
                    fight = item[2]
                    self.store.save_fight(fight)
                    self.status.set(f"Saved completed boss fight: {fight['bossName']}")
                elif kind == "replay_done":
                    self.status.set(f"Replay complete: {value:,} records; {self.engine.damage_events:,} damage records recognized")
                    changed = True
                elif kind == "capture_stopped":
                    if value != self.capture_generation:
                        continue
                    self.status.set(f"Capture stopped; {self.engine.damage_events:,} damage records recognized")
                    changed = True
                elif kind == "error":
                    if value != self.capture_generation:
                        continue
                    messagebox.showerror("Capture failed", item[2] if len(item) > 2 else "Capture failed")
                    self.status.set("Capture failed")
                    self.capture_stop.set()
                elif kind == "replay_error":
                    messagebox.showerror("Replay failed", item[2])
                    self.status.set("Replay failed")
        except queue.Empty:
            pass
        if changed or self.engine.damage_events:
            self._render()
        self.root.after(250, self._poll)

    def _render(self) -> None:
        result = self.engine.snapshot(self.mode.get())
        self.current_snapshot = result
        ping = result.get("pingMs")
        self.ping_label.configure(text=f"Ping: {ping} ms" if ping is not None else "Ping: —")
        self.title_label.configure(text=f"{result['targetName']}   •   {result['totalDamage']:,} damage   •   {result['dps']:,.1f} DPS")
        self.chart.delete("all")
        points = result.get("timelineByActor", {}).get(str(self.selected_actor_id), result.get("timeline", []))
        if points:
            width = max(1, self.chart.winfo_width())
            height = max(1, self.chart.winfo_height())
            values = [point["damage"] for point in points]
            vmax = max(values) or 1
            count = len(points)
            coords = []
            for index, value in enumerate(values):
                x = 8 + index * max(1, width - 16) / max(1, count - 1)
                y = height - 8 - value * (height - 20) / vmax
                coords.extend((x, y))
            if len(coords) >= 4:
                self.chart.create_line(*coords, fill="#67d7b0", width=2, smooth=True)
            label = "Damage per second"
            if self.selected_actor_id is not None:
                actor_row = next((a for a in result["actors"] if a["actorId"] == self.selected_actor_id), None)
                if actor_row:
                    label += f" • {actor_row['nickname']}"
            self.chart.create_text(8, 7, text=label, anchor="nw", fill="#b9c2d0")
        self.hp_bar.delete("all")
        maximum = result.get("targetMaxHp", 0)
        if maximum > 0:
            current = result.get("targetCurrentHp", -1)
            if current < 0:
                current = max(0, maximum - result.get("totalDamage", 0))
            width = max(1, self.hp_bar.winfo_width())
            self.hp_bar.create_rectangle(0, 0, width, 18, fill="#562f39", outline="")
            self.hp_bar.create_rectangle(0, 0, width * min(1, max(0, current / maximum)), 18,
                                         fill="#45b784", outline="")
            self.hp_bar.create_text(width / 2, 9, text=f"{current:,} / {maximum:,} HP",
                                    fill="white", font=("Segoe UI", 8, "bold"))
        self.table.delete(*self.table.get_children())
        for actor in result["actors"]:
            self.table.insert("", "end", iid=str(actor["actorId"]), values=(actor["nickname"], actor["job"],
                                                    actor["level"], f"{actor['gearScore']:,}" if actor["gearScore"] else "",
                                                    f"{actor['combatPower']:,}" if actor["combatPower"] else "",
                                                    f"{actor['damage']:,}",
                                                    f"{actor['dps']:,.1f}", f"{actor['contribution']:.1%}"))
        selected_actor = next((actor for actor in result["actors"] if actor["actorId"] == self.selected_actor_id), None)
        if selected_actor:
            lines = [f"{selected_actor['nickname']} — {selected_actor['job']} — {selected_actor['damage']:,} damage — {selected_actor['healing']:,} healing", "",
                     "Skill                         Damage       Hits   Crit%   Back%       Min       Max"]
            for skill in sorted(selected_actor["skills"], key=lambda item: item["damage"], reverse=True):
                lines.append(f"{skill['name']:<29.29} {skill['damage']:>10,} {skill['hits']:>8}"
                             f" {skill['critRate']:>7.1%} {skill['backRate']:>7.1%}"
                             f" {skill['minDamage']:>9,} {skill['maxDamage']:>9,}")
        else:
            lines = ["Top skills"]
            for actor in result["actors"]:
                for skill in sorted(actor["skills"], key=lambda s: s["damage"], reverse=True)[:5]:
                    lines.append(f"{actor['nickname']:<18} {skill['name']:<34} {skill['damage']:>12,}  ({skill['hits']} hits)")
        if result.get("healers"):
            lines.extend(("", "Healing summary"))
            for healer in result["healers"]:
                lines.append(f"{healer['nickname']:<18} {healer['healing']:>12,} healing  ({healer['regeneration']:,} HoT)")
        self.skills.configure(state="normal")
        self.skills.delete("1.0", "end")
        self.skills.insert("1.0", "\n".join(lines))
        self.skills.configure(state="disabled")

    def _actor_selected(self, _event=None) -> None:
        selected = self.table.selection()
        if not selected or self.current_snapshot is None:
            return
        try:
            self.selected_actor_id = int(selected[0])
        except ValueError:
            return
        self._render()

    def save_fight(self) -> None:
        snapshot = self.engine.snapshot(self.mode.get())
        if not snapshot["totalDamage"]:
            messagebox.showinfo("Fight history", "There is no recognized damage to save yet.")
            return
        self.store.save_fight(snapshot)
        self.status.set("Fight saved to local history")

    def show_history(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Fight history")
        window.geometry("900x540")
        window.minsize(680, 360)
        split = ttk.Panedwindow(window, orient="vertical")
        split.pack(fill="both", expand=True, padx=10, pady=10)
        list_frame = ttk.Frame(split)
        detail_frame = ttk.Frame(split)
        split.add(list_frame, weight=3)
        split.add(detail_frame, weight=2)

        columns = ("saved", "target", "duration", "damage", "dps", "mode")
        table = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        for key, label, width, anchor in (
            ("saved", "Saved", 155, "w"), ("target", "Target", 230, "w"),
            ("duration", "Duration", 90, "e"), ("damage", "Damage", 120, "e"),
            ("dps", "DPS", 100, "e"), ("mode", "Mode", 120, "w"),
        ):
            table.heading(key, text=label)
            table.column(key, width=width, anchor=anchor)
        table.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=table.yview)
        scrollbar.pack(side="right", fill="y")
        table.configure(yscrollcommand=scrollbar.set)

        details = tk.Text(detail_frame, height=10, wrap="none", state="disabled")
        details.pack(fill="both", expand=True)
        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        status = tk.StringVar(value="Double-click a fight to open its full details.")
        ttk.Label(buttons, textvariable=status).pack(side="left", fill="x", expand=True)
        export_button = ttk.Button(buttons, text="Export JSON", state="disabled")
        export_button.pack(side="right", padx=(0, 8))
        delete_button = ttk.Button(buttons, text="Delete selected", state="disabled")
        delete_button.pack(side="right")
        records: dict[str, dict] = {}

        def duration_text(value) -> str:
            seconds = max(0, int(value or 0)) // 1000
            return f"{seconds // 60}:{seconds % 60:02d}"

        def refresh(selected_id: int | None = None) -> None:
            table.delete(*table.get_children())
            records.clear()
            for fight in self.store.fights():
                item_id = str(fight["id"])
                records[item_id] = fight
                saved = time.strftime("%Y-%m-%d %H:%M", time.localtime(fight["savedMs"] / 1000))
                table.insert("", "end", iid=item_id, values=(
                    saved, fight.get("targetName", "Unknown target"),
                    duration_text(fight.get("durationMs")), f"{fight.get('totalDamage', 0):,}",
                    f"{fight.get('dps', 0):,.1f}", fight.get("mode", ""),
                ))
            if selected_id is not None and str(selected_id) in records:
                table.selection_set(str(selected_id))
                table.focus(str(selected_id))
                show_selected()
            elif not records:
                status.set("No saved fights.")
                delete_button.configure(state="disabled")
                details.configure(state="normal")
                details.delete("1.0", "end")
                details.insert("1.0", "No saved fights.")
                details.configure(state="disabled")

        def show_selected(_event=None) -> None:
            selection = table.selection()
            if not selection or selection[0] not in records:
                delete_button.configure(state="disabled")
                export_button.configure(state="disabled")
                return
            fight = records[selection[0]]
            delete_button.configure(state="normal")
            export_button.configure(state="normal")
            status.set(f"Fight #{fight['id']} — {fight.get('targetName', 'Unknown target')}")
            lines = [json.dumps({key: value for key, value in fight.items() if key != "actors"},
                                ensure_ascii=False, indent=2), "", "Players"]
            for actor in fight.get("actors", []):
                lines.append(f"{actor.get('nickname', 'Unknown'):<24} {actor.get('job', ''):<14} "
                             f"{actor.get('damage', 0):>12,}  {actor.get('dps', 0):>9,.1f} DPS")
                skills = sorted(actor.get("skills", []), key=lambda skill: skill.get("damage", 0), reverse=True)
                for skill in skills[:5]:
                    lines.append(f"    {skill.get('name', 'Unknown skill'):<32} "
                                 f"{skill.get('damage', 0):>12,}  {skill.get('hits', 0):>6} hits")
            details.configure(state="normal")
            details.delete("1.0", "end")
            details.insert("1.0", "\n".join(lines))
            details.configure(state="disabled")

        def open_selected(_event=None) -> None:
            show_selected()
            if table.selection():
                fight = records.get(table.selection()[0])
                if fight:
                    self._show_fight_details(fight)

        def delete_selected() -> None:
            selection = table.selection()
            if not selection:
                return
            fight_id = int(selection[0])
            if not messagebox.askyesno("Delete fight", "Delete this saved fight from local history?", parent=window):
                return
            self.store.delete_fight(fight_id)
            refresh()
            status.set("Saved fight deleted.")

        def export_selected() -> None:
            selection = table.selection()
            if not selection:
                return
            fight = records.get(selection[0])
            if not fight:
                return
            target = "".join(ch if ch.isalnum() or ch in " -_" else "_"
                             for ch in fight.get("targetName", "fight")).strip() or "fight"
            path = filedialog.asksaveasfilename(
                parent=window, title="Export saved fight", initialfile=f"{target}.json",
                defaultextension=".json", filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as output:
                    json.dump(fight, output, ensure_ascii=False, indent=2)
                    output.write("\n")
                status.set(f"Exported fight to {path}")
            except OSError as exc:
                messagebox.showerror("Export failed", str(exc), parent=window)

        table.bind("<<TreeviewSelect>>", show_selected)
        table.bind("<Double-1>", open_selected)
        delete_button.configure(command=delete_selected)
        export_button.configure(command=export_selected)
        refresh()

    def _show_fight_details(self, fight: dict) -> None:
        window = tk.Toplevel(self.root)
        window.title(f"Fight details — {fight.get('targetName', 'AION 2')}")
        window.geometry("780x520")
        text = tk.Text(window, wrap="none")
        text.pack(fill="both", expand=True)
        text.insert("1.0", json.dumps(fight, ensure_ascii=False, indent=2))
        text.configure(state="disabled")

    def start_capture(self) -> None:
        if self.capture_thread and self.capture_thread.is_alive():
            return
        try:
            from .capture import capture_packets
        except ImportError as exc:
            messagebox.showerror("Live capture unavailable", f"Install the capture extra first:\n\npython -m pip install -e .[capture]\n\n{exc}")
            return
        try:
            port = int(self.capture_port.get())
        except ValueError:
            messagebox.showerror("Invalid port", "Enter a game server TCP port from 1 to 65535.")
            return
        if not 1 <= port <= 65_535:
            messagebox.showerror("Invalid port", "Enter a game server TCP port from 1 to 65535.")
            return
        try:
            window_seconds = max(10, min(900, int(self.all_targets_window.get())))
        except ValueError:
            messagebox.showerror("Invalid window", "The all-target window must be between 10 and 900 seconds.")
            return
        self.replay_generation += 1
        self.capture_generation += 1
        self.engine = self._new_engine(perf_clock=system_perf_clock)
        self.engine.set_server_port(port)
        self.store.set_setting("serverPort", port)
        self.store.set_setting("captureInterface", self.capture_interface.get().strip())
        self.all_targets_window.set(str(window_seconds))
        self.store.set_setting("allTargetsWindowSec", window_seconds)
        self.engine.set_all_targets_window_ms(window_seconds * 1000)
        self.capture_stop.clear()
        generation = self.capture_generation
        self.status.set("Capturing game traffic; packet capture may require Administrator privileges and Npcap")
        self.capture_thread = threading.Thread(target=capture_packets,
                                               args=(self.capture_stop, self.queue, self.capture_interface.get().strip(), port, generation),
                                               daemon=True)
        self.capture_thread.start()

    def _new_engine(self, *, perf_clock=None) -> MeterEngine:
        engine = MeterEngine(perf_clock=perf_clock)
        character_name = self.character_name.get().strip()
        engine.set_local_character_name(character_name)
        self.store.set_setting("localCharacterName", character_name)
        try:
            window_seconds = max(10, min(900, int(self.all_targets_window.get())))
        except ValueError:
            window_seconds = 120
        engine.set_all_targets_window_ms(window_seconds * 1000)
        return engine

    def _save_character_name(self) -> None:
        character_name = self.character_name.get().strip()
        self.character_name.set(character_name)
        self.store.set_setting("localCharacterName", character_name)
        self.engine.set_local_character_name(character_name)

    def stop_capture(self) -> None:
        self.capture_stop.set()
        self.status.set("Stopping live capture…")


def main() -> None:
    root = tk.Tk()
    MeterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
