"""Platform-specific prerequisite checks for Live Capture."""
from __future__ import annotations

import ctypes.util
import shutil
import subprocess
import sys


def _linux_command() -> list[str] | None:
    if shutil.which("apt-get"):
        return ["sudo", "apt-get", "update", "&&", "sudo", "apt-get", "install", "-y", "libpcap0.8"]
    if shutil.which("dnf"):
        return ["sudo", "dnf", "install", "-y", "libpcap"]
    if shutil.which("pacman"):
        return ["sudo", "pacman", "-S", "--needed", "libpcap"]
    return None


def status() -> dict:
    """Describe the packet-capture prerequisite for the current platform."""
    if sys.platform == "win32":
        from . import npcap
        state = npcap.status()
        return {**state, "kind": "Npcap", "prompt": "Live Capture needs Npcap. Download and open its current official installer now?"}
    pcap = bool(ctypes.util.find_library("pcap"))
    if sys.platform == "darwin":
        return {"supported": True, "installed": pcap, "kind": "macOS packet capture",
                "prompt": "Live Capture needs macOS packet-capture support. Open the install command now?"}
    if sys.platform.startswith("linux"):
        return {"supported": True, "installed": pcap, "kind": "libpcap",
                "prompt": "Live Capture needs libpcap. Open a terminal with the install command now?"}
    return {"supported": False, "installed": False, "kind": "packet capture",
            "prompt": "Packet capture setup is not available on this platform."}


def begin_install() -> dict:
    """Start only an explicitly approved platform setup action."""
    if sys.platform == "win32":
        from . import npcap
        return npcap.begin_install()
    command = (["brew", "install", "libpcap"] if sys.platform == "darwin" else _linux_command())
    if not command:
        return {**status(), "error": "Install libpcap with your distribution's package manager, then try again."}
    shell_command = " ".join(command)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{shell_command}"'])
        else:
            terminal = next((name for name in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm")
                             if shutil.which(name)), None)
            if not terminal:
                return {**status(), "error": f"Run: {shell_command}"}
            if terminal == "gnome-terminal":
                args = [terminal, "--", "bash", "-lc", shell_command]
            elif terminal == "konsole":
                args = [terminal, "-e", "bash", "-lc", shell_command]
            else:
                args = [terminal, "-e", "bash", "-lc", shell_command]
            subprocess.Popen(args)
        return {**status(), "status": "installer-opened"}
    except OSError as exc:
        return {**status(), "error": f"{type(exc).__name__}: {exc}; run: {shell_command}"}
