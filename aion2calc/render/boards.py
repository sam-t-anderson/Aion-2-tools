"""Render Daevanion boards (selected nodes highlighted) to PNG with matplotlib."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, RegularPolygon  # noqa: E402

GRADE_COLORS = {"Common": "#c9ced6", "Rare": "#4aa3ff", "Legend": "#b06cff", "Epic": "#b06cff",
                "Unique": "#f3c04f", "Start": "#7ee0c3"}
BG = "#12161e"
PANEL = "#1b2230"
TEXT = "#e8e2d2"
MUTED = "#6c7891"

SHORT = {"Critical Hit": "Crit", "Critical Hit Resist": "CritRes", "Attack Bonus": "Atk",
         "Defense Bonus": "Def", "Combat Speed": "CSpd", "Cooldown Reduction": "CDR",
         "Damage Boost": "DmgB", "Damage Tolerance": "DmgTol", "Critical Damage Boost": "CritDmg",
         "Critical Damage Tolerance": "CDTol", "Multi-hit Chance": "Multi", "Multi-hit Resist": "MultiR"}


_ABBR: dict[str, str] = {}


def _short_skill(name: str) -> str:
    if name in _ABBR:
        return _ABBR[name]
    words = name.replace("of ", "").split()
    return "".join(w[0] for w in words) if len(name) > 11 else name


def _set_abbreviations(boards) -> dict[str, str]:
    """Unique short names for long skill names; clashes spell out two letters of
    the first word that differs (Revitalization Contract / Robe of Cold -> ReC / RoC)."""
    _ABBR.clear()
    names = sorted({n.get("skillName") or "" for b in boards for n in b["nodes"] if n["type"] == "SkillLevel"})
    base = {nm: _short_skill(nm) for nm in names}
    out = dict(base)
    for short in set(base.values()):
        group = [nm for nm in names if base[nm] == short and nm != short]
        if len(group) < 2:
            continue
        words = {nm: nm.replace("of ", "").split() for nm in group}
        pos = next((i for i in range(len(short)) if len({words[nm][i][:2] for nm in group}) > 1), None)
        for nm in group:
            if pos is not None:
                out[nm] = "".join(w[:2] if i == pos else w[0] for i, w in enumerate(words[nm]))
    _ABBR.update(out)
    return out


def _label(node) -> str:
    if node["type"] == "SkillLevel":
        return f"{_short_skill(node.get('skillName') or '')}\n+1"
    lab = node.get("label", "")
    for k, v in SHORT.items():
        if lab.startswith(k + " "):
            return lab.replace(k, v).replace(" +", "\n+")
    return lab.replace(" +", "\n+")[:14]


def render_board(ax, board, selected: set, title_extra: str = ""):
    nodes = board["nodes"]
    rows = [n["row"] for n in nodes]
    cols = [n["col"] for n in nodes]
    pos = {(n["row"], n["col"]): n for n in nodes}
    ax.set_facecolor(PANEL)
    # connections between taken (or start) neighbours
    for n in nodes:
        on = n["id"] in selected or n["type"] == "Start"
        if not on:
            continue
        for dr, dc in ((1, 0), (0, 1)):
            m = pos.get((n["row"] + dr, n["col"] + dc))
            if m and (m["id"] in selected or m["type"] == "Start"):
                ax.plot([n["col"], m["col"]], [n["row"], m["row"]], color="#e9d27a", lw=2.2,
                        alpha=0.85, zorder=1, solid_capstyle="round")
    for n in nodes:
        x, y = n["col"], n["row"]
        grade = "Start" if n["type"] == "Start" else n.get("grade", "Common")
        col = GRADE_COLORS.get(grade, "#999")
        on = n["id"] in selected or n["type"] == "Start"
        alpha = 1.0 if on else 0.22
        edge = "#fff6d0" if on else "#3a4558"
        if n["type"] == "Start":
            p = RegularPolygon((x, y), 6, radius=0.48, facecolor=col, edgecolor=edge, lw=2, zorder=3)
        elif n["type"] == "SkillLevel":
            p = Circle((x, y), 0.40, facecolor=col, edgecolor=edge, lw=1.8 if on else 0.8,
                       alpha=alpha, zorder=3)
        else:
            s = 0.74 if grade != "Unique" else 0.86
            p = FancyBboxPatch((x - s / 2, y - s / 2), s, s, boxstyle="round,pad=0.02,rounding_size=0.12",
                               facecolor=col, edgecolor=edge, lw=1.8 if on else 0.8, alpha=alpha, zorder=3)
        ax.add_patch(p)
        if n["type"] != "Start":
            ax.text(x, y, _label(n), ha="center", va="center", fontsize=4.6 if n["type"] == "SkillLevel" else 4.4,
                    color="#10141b" if on else "#aab3c5", alpha=1.0 if on else 0.5, zorder=4,
                    fontweight="bold" if on else "normal", linespacing=0.95)
    spent = sum(n["cost"] for n in nodes if n["id"] in selected)
    total = sum(n["cost"] for n in nodes)
    ax.set_title(f"{board['name']}  ·  {spent}/{total} pts  ·  {len(selected & {n['id'] for n in nodes})} nodes"
                 + (f"\n{title_extra}" if title_extra else ""), color=TEXT, fontsize=9, pad=6)
    ax.set_xlim(min(cols) - 0.8, max(cols) + 0.8)
    ax.set_ylim(max(rows) + 0.8, min(rows) - 0.8)
    ax.set_aspect("equal")
    ax.axis("off")


def render_boards(cd, selected: set, path: str, title: str, boards=("Nezekan", "Zikel", "Vaizel", "Triniel"),
                  summary_lines: list[str] | None = None, budget: int | None = None):
    bl = [b for b in cd.boards if b["name"] in boards]
    _set_abbreviations(bl)
    fig = plt.figure(figsize=(16, 13.5), dpi=170, facecolor=BG)
    fig.suptitle(title, color=TEXT, fontsize=15, fontweight="bold", y=0.985)
    gs = fig.add_gridspec(2, 3, width_ratios=[1, 1, 0.62], hspace=0.08, wspace=0.04,
                          left=0.01, right=0.99, top=0.95, bottom=0.02)
    spots = [gs[0, 0], gs[0, 1], gs[1, 0], gs[1, 1]]
    for b, sp in zip(bl, spots):
        render_board(fig.add_subplot(sp), b, selected)
    ax = fig.add_subplot(gs[:, 2])
    ax.set_facecolor(PANEL)
    ax.axis("off")
    total = sum(cd.node_index[n][1]["cost"] for n in selected if n in cd.node_index)
    lines = [f"Points used: {total}" + (f" / {budget}" if budget else "")]
    lines += summary_lines or []
    abbr = sorted((short, full) for full, short in _ABBR.items() if short != full)
    abbr_rows = (len(abbr) + 1) // 2
    heads = sum(1 for ln in lines if ln.startswith("## "))
    need = 0.026 * len(lines) + 0.012 * heads + 0.17 + (0.035 + 0.022 * abbr_rows if abbr else 0)
    k = min(1.0, 0.96 / need)          # shrink spacing (and a little the fonts) to fit the panel
    f = max(0.78, k)
    y = 0.98
    for ln in lines:
        style = {"fontsize": 9.5 * f, "color": TEXT}
        if ln.startswith("## "):
            ln = ln[3:]
            style = {"fontsize": 11 * f, "color": "#f3c04f", "fontweight": "bold"}
            y -= 0.012 * k
        ax.text(0.04, y, ln, transform=ax.transAxes, va="top", family="DejaVu Sans", **style)
        y -= 0.026 * k
    # legend
    y -= 0.02 * k
    for g in ["Common", "Rare", "Legend", "Unique"]:
        ax.add_patch(FancyBboxPatch((0.05, y - 0.012 * k), 0.04, 0.02 * k, transform=ax.transAxes,
                                    boxstyle="round,pad=0.002", facecolor=GRADE_COLORS[g], edgecolor="none"))
        cost = {"Common": 1, "Rare": 2, "Legend": 3, "Unique": 4}[g]
        ax.text(0.12, y, f"{g if g != 'Legend' else 'Epic'} node · {cost} pt", transform=ax.transAxes,
                va="center", color=TEXT, fontsize=8.5 * f)
        y -= 0.03 * k
    ax.text(0.05, y, "squares = stats, circles = +1 skill level", transform=ax.transAxes, color=MUTED,
            fontsize=8 * f)
    if abbr:
        y -= 0.035 * k
        ax.text(0.05, y, "Skill abbreviations", transform=ax.transAxes, color=MUTED, fontsize=8.5 * f,
                fontweight="bold")
        for i, (short, full) in enumerate(abbr):
            col, row = divmod(i, abbr_rows)
            ax.text(0.05 + 0.48 * col, y - 0.022 * k * (row + 1), f"{short} = {full}", transform=ax.transAxes,
                    color=MUTED, fontsize=7.4 * f)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path
