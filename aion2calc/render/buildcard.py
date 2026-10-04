"""Planner-style build page rendered to PNG (skills, specs, stigmas, rotation, macro, stats)."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.offsetbox import AnnotationBbox, OffsetImage  # noqa: E402
from PIL import Image  # noqa: E402

from ..scrape.http import fetch_bytes  # noqa: E402

BG, PANEL, TEXT, MUTED, GOLD, CYAN = "#11161d", "#1b2230", "#efe7d6", "#8590a6", "#f0c75e", "#58d0f0"
ICON_URL = "https://metabot.gg/web/aion2/skills/{}.webp"
SPEC_ICON_URL = "https://metabot.gg/web/aion2/stigma/{}.webp"


def _icon(url: str, size: int = 64):
    data = fetch_bytes(url)
    if not data:
        return None
    try:
        im = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size))
        return im
    except Exception:
        return None


def _place(ax, im, x, y, zoom=0.42):
    if im is None:
        return
    ab = AnnotationBbox(OffsetImage(im, zoom=zoom), (x, y), frameon=False, xycoords="axes fraction",
                        box_alignment=(0.5, 0.5))
    ax.add_artist(ab)


def _panel(fig, rect, title):
    ax = fig.add_axes(rect)
    ax.set_facecolor(PANEL)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2c3648")
    ax.text(0.015, 0.985, title, transform=ax.transAxes, va="top", color=GOLD, fontsize=12, fontweight="bold")
    return ax


def render_build_card(path: str, *, title: str, subtitle: str, skills: list[dict], passives: list[dict],
                      stigmas: list[dict], priority: list[dict], macro: dict, stat_lines: list[str],
                      weights: list[dict], shares: list[tuple], gear: list[str], links: list[str]):
    fig = plt.figure(figsize=(17, 23), dpi=150, facecolor=BG)
    fig.text(0.02, 0.985, title, color=TEXT, fontsize=22, fontweight="bold", va="top")
    fig.text(0.02, 0.967, subtitle, color=MUTED, fontsize=11, va="top")

    # --- active skills
    ax = _panel(fig, [0.02, 0.57, 0.56, 0.385], "Active skills  (trained + Daevanion + gear = effective)  ·  specializations")
    y = 0.93
    dy = 0.0745
    for s in skills:
        _place(ax, _icon(ICON_URL.format(s["id"])), 0.035, y, zoom=0.5)
        ax.text(0.075, y + 0.012, s["name"], transform=ax.transAxes, color=TEXT, fontsize=11, fontweight="bold", va="center")
        ax.text(0.075, y - 0.02, f"Lv {s['eff']}  =  {s['sp']} SP + {s['daev']} Daev + {s['gear']} gear",
                transform=ax.transAxes, color=CYAN if s['eff'] >= 12 else MUTED, fontsize=9, va="center")
        x = 0.36
        n = len(s["specs"])
        for i, sp in enumerate(s["specs"]):          # one spec per line, stacked inside the row
            yy = y + (n - 1) * 0.0165 - i * 0.033
            _place(ax, _icon(SPEC_ICON_URL.format(sp["id"]), 48), x, yy, zoom=0.32)
            ax.text(x + 0.022, yy, sp["text"], transform=ax.transAxes, color=TEXT, fontsize=8.2, va="center")
        if not s["specs"]:
            ax.text(x, y, "—", transform=ax.transAxes, color=MUTED, fontsize=9, va="center")
        y -= dy

    # --- passives + stigmas
    ax = _panel(fig, [0.02, 0.36, 0.27, 0.2], "Passives")
    y = 0.88
    for p in passives:
        _place(ax, _icon(ICON_URL.format(p["id"]), 48), 0.06, y, zoom=0.36)
        ax.text(0.12, y, f"{p['name']}", transform=ax.transAxes, color=TEXT, fontsize=9, va="center")
        ax.text(0.97, y, f"Lv {p['eff']} ({p['sp']}+{p['daev']})", transform=ax.transAxes, color=CYAN,
                fontsize=8.5, va="center", ha="right")
        y -= 0.085
    ax = _panel(fig, [0.31, 0.36, 0.27, 0.2], "Stigmas (4 slots)")
    y = 0.86
    for st in stigmas:
        _place(ax, _icon(ICON_URL.format(st["id"]), 56), 0.07, y, zoom=0.45)
        ax.text(0.14, y + 0.025, f"{st['name']}  ·  Lv {st['level']}", transform=ax.transAxes, color=TEXT,
                fontsize=10, fontweight="bold", va="center")
        ax.text(0.14, y - 0.03, "; ".join(st["specs"]) or "no specialization yet", transform=ax.transAxes,
                color=MUTED, fontsize=7.6, va="center", wrap=True)
        y -= 0.2

    # --- priority & macro
    ax = _panel(fig, [0.60, 0.57, 0.38, 0.385], "Rotation priority (top = highest)")
    y = 0.93
    for i, p in enumerate(priority, 1):
        _place(ax, _icon(ICON_URL.format(p["id"]), 48), 0.07, y, zoom=0.38)
        ax.text(0.015, y, f"{i}", transform=ax.transAxes, color=GOLD, fontsize=10, va="center")
        ax.text(0.12, y, p["label"], transform=ax.transAxes, color=TEXT, fontsize=9.6, va="center")
        if p.get("note"):
            ax.text(0.98, y, p["note"], transform=ax.transAxes, color=MUTED, fontsize=8, va="center", ha="right")
        y -= 0.063

    ax = _panel(fig, [0.60, 0.36, 0.38, 0.2],
                "In-game Skill Macro (hold key)" + (" + manual keys" if macro["manual"] else ""))
    y = 0.86
    ax.text(0.03, y, "Macro steps (in order, 10 ms delay, Skill Queue ON):", transform=ax.transAxes,
            color=CYAN, fontsize=9.5)
    y -= 0.075
    steps = macro["steps"]
    rows = (len(steps) + 1) // 2 if len(steps) > 7 else len(steps)
    for i, st in enumerate(steps):
        col, row = divmod(i, rows)
        ax.text(0.05 + 0.47 * col, y - 0.062 * row, f"{i + 1}. {st}", transform=ax.transAxes, color=TEXT,
                fontsize=9.3)
    y -= 0.062 * rows + 0.02
    if macro["manual"]:
        ax.text(0.03, y, "Press manually on cooldown:", transform=ax.transAxes, color=CYAN, fontsize=9.5)
        y -= 0.075
        ax.text(0.05, y, ", ".join(macro["manual"]), transform=ax.transAxes, color=TEXT, fontsize=9.2, wrap=True)
        y -= 0.08
    ax.text(0.03, max(y, 0.03), macro.get("note", ""), transform=ax.transAxes, color=MUTED, fontsize=8.3, wrap=True)

    # --- stats and weights
    ax = _panel(fig, [0.02, 0.155, 0.27, 0.195], "Combat stats (simulated)")
    y = 0.88
    for ln in stat_lines:
        ax.text(0.04, y, ln, transform=ax.transAxes, color=TEXT, fontsize=9.2)
        y -= 0.068

    ax = fig.add_axes([0.42, 0.165, 0.16, 0.175])
    ax.set_facecolor(PANEL)
    top = weights[:10][::-1]
    ax.barh([w["label"] for w in top], [w["pct"] for w in top], color=GOLD)
    ax.tick_params(colors=TEXT, labelsize=8)
    for s in ax.spines.values():
        s.set_color("#2c3648")
    ax.set_title("Stat value (% DPS per step)", color=GOLD, fontsize=11, loc="left")
    ax.set_xlabel("% DPS", color=MUTED, fontsize=8)

    ax = _panel(fig, [0.60, 0.155, 0.38, 0.195], "Damage share (180 s simulation)")
    y = 0.86
    for name, frac in shares[:11]:
        ax.add_patch(plt.Rectangle((0.42, y - 0.02), 0.5 * frac / max(shares[0][1], 1e-9), 0.04,
                                   transform=ax.transAxes, color=CYAN, alpha=0.8))
        ax.text(0.03, y, name, transform=ax.transAxes, color=TEXT, fontsize=8.8, va="center")
        ax.text(0.40, y, f"{100 * frac:4.1f}%", transform=ax.transAxes, color=TEXT, fontsize=8.8, va="center",
                ha="right")
        y -= 0.075

    ax = _panel(fig, [0.02, 0.012, 0.96, 0.135], "Gear, titles & links")
    y = 0.84
    for ln in gear[:7]:
        ax.text(0.015, y, ln, transform=ax.transAxes, color=TEXT, fontsize=8.8)
        y -= 0.115
    y2 = 0.84
    for ln in links[:6]:
        ax.text(0.52, y2, ln, transform=ax.transAxes, color=CYAN, fontsize=7.4)
        y2 -= 0.13
    from . import save_png
    save_png(fig, path, BG, dither=True)
    plt.close(fig)
    return path
