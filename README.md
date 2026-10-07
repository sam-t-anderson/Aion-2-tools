# Aion 2 Calc

[![CI](https://github.com/sam-t-anderson/Aion-2-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/sam-t-anderson/Aion-2-tools/actions/workflows/ci.yml)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/9y6zkUyvBv)

A desktop companion and community website for **AION 2**: optimize your build, review combat, and plan encounters.

[Download the app](https://github.com/sam-t-anderson/Aion-2-tools/releases/latest) · [Open the website](https://sam-t-anderson.github.io/Aion-2-tools/) · [Release notes](https://github.com/sam-t-anderson/Aion-2-tools/releases) · [Discord](https://discord.gg/9y6zkUyvBv)

## Install

Download the Windows installer or a portable Windows, macOS or Linux build from **Releases**. On Windows, run `aion2calc-setup-<version>.exe`, then open **Aion 2 Calc** from the Start menu. No Python or command line is needed.

Live capture requires **Npcap on Windows** or **libpcap on macOS/Linux**. Setup and the app offer dependency guidance; Npcap is downloaded separately from its official source. Windows requests administrator approval when installing the driver.

See [installation and updates](docs/install.md) for platform instructions, permissions and troubleshooting.

## What you can do

- **Optimize builds:** import your character, allocate available Skill, Stigma and Daevanion points, review specialties, hotbar and macro guidance, and save results for later. Gear & Advice ranks modeled upgrades.
- **Review combat:** use Live Meter and its overlay, or open saved logs. Inspect damage, healing, deaths and per-player skills using tables, graphs, timelines and events; group linked pets with their owners.
- **Share and compare:** upload logs as Public, Unlisted or Private, manage your uploads, browse community logs and compare eligible recordings and personal records.
- **Plan encounters:** create and share raid plans, edit your published plans, and replay recorded positions when the log contains supported movement data.

Enter your actual available point totals; imported profiles may omit unspent points. PvP optimization is experimental. Missing telemetry stays unavailable, and community rankings depend on comparable, eligible public recordings. The [user guide](docs/user-guide.md) explains these limits and privacy controls.

## Guides

| Guide | Contents |
|---|---|
| [App guide](docs/app.md) | Desktop controls, capture, overlay and troubleshooting |
| [User guide](docs/user-guide.md) | Saved results, log review, uploads, privacy and comparisons |
| [Planner](docs/planner.md) | Build planning and advice |
| [Methodology](docs/methodology.md) | Simulation formulas, data sources and assumptions |
| [Roadmap](docs/COMBAT_ROADMAP.md) | Remaining work and current limitations |

Feature history and version-specific fixes are kept in [Releases](https://github.com/sam-t-anderson/Aion-2-tools/releases).

## For developers

See [CLI and development](docs/cli.md) for running from source, architecture, packaging and contributing. This repository contains the client and GitHub Pages website; server operation belongs in the [server repository](https://github.com/sam-t-anderson/Aion-2-tools-server).

## Author

**Spirited - Zikel : Asmodian | Legion: WhaleWatch**

## License

GPL-3.0 (see [LICENSE](LICENSE)). Game data belongs to NCSOFT; community data belongs to its respective sites. This project is fan-made and not affiliated with NCSOFT.
