# Aion 2 Calc

[![CI](https://github.com/sam-t-anderson/Aion-2-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/sam-t-anderson/Aion-2-tools/actions/workflows/ci.yml)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/9y6zkUyvBv)
[![Signed with Azure Artifact Signing](https://img.shields.io/badge/signed%20with-Azure%20Artifact%20Signing-0078D4)](docs/code-signing.md)

A desktop companion and community website for **AION 2**: optimize your build, review combat, and plan encounters.

[Download the app](https://github.com/sam-t-anderson/Aion-2-tools/releases/latest) · [Open the website](https://sam-t-anderson.github.io/Aion-2-tools/) · [Release notes](https://github.com/sam-t-anderson/Aion-2-tools/releases) · [Discord](https://discord.gg/9y6zkUyvBv)

## Install

Download the Windows installer or a portable Windows, macOS or Linux build from **Releases**. On Windows, run `aion2calc-setup-<version>.exe`, then open **Aion 2 Calc** from the Start menu. No Python or command line is needed.

Live capture requires **Npcap on Windows** or **libpcap on macOS/Linux**. Setup and the app offer dependency guidance; Npcap is downloaded separately from its official source. Windows requests administrator approval when installing the driver.

See [installation and updates](docs/install.md) for platform instructions, permissions and troubleshooting.

## Verify your download

Before you run a download, check that it is the file this repository's release built: its SHA-256 must
match the one below exactly.

<!-- checksums:start -->
Latest release: **[v0.2.359](https://github.com/sam-t-anderson/Aion-2-tools/releases/tag/v0.2.359)** · [SHA256SUMS.txt](https://github.com/sam-t-anderson/Aion-2-tools/releases/download/v0.2.359/SHA256SUMS.txt)

| File | SHA-256 |
|---|---|
| `aion2calc-setup-0.2.359.exe` | `b2085c0460ccd2bad9319ed2891c1c5f0c01a3abf583849658f2fddaae24defb` |
| `aion2calc-0.2.359-windows-portable.zip` | `a64dda18b303022c435ff1ae0347e4e58290b3705d026b92aa741ef3f83c273c` |
| `aion2calc-0.2.359-macos.zip` | `9ccf7c0d7a64d142c88f54d88f991ef05e6c66dbc4093afada4026607d4d3cf1` |
| `aion2calc-0.2.359-linux.tar.gz` | `077af480f6bba5fa22ff3ef91e3c7de24691a11706e248a78135e0e57f214c3b` |
<!-- checksums:end -->

| Your computer | Command |
|---|---|
| Windows (PowerShell) | `Get-FileHash .\aion2calc-setup-<version>.exe` |
| macOS (Terminal) | `shasum -a 256 aion2calc-<version>-macos.zip` |
| Linux | `sha256sum aion2calc-<version>-linux.tar.gz` |

`Get-FileHash` prints the hash in capitals; letter case does not matter. The release page shows each file's
SHA-256 beside it, and from 0.2.348 each release also lists them in its notes and in `SHA256SUMS.txt`
(`sha256sum -c SHA256SUMS.txt` checks every file at once). On Windows, the
signature is the stronger check: right-click the installer or `aion2calc.exe` → **Properties → Digital
Signatures** shows the publisher, signed with Azure Artifact Signing and timestamped by Microsoft
([code signing](docs/code-signing.md)).

## What you can do

- **Optimize builds:** import your character, allocate available Skill, Stigma and Daevanion points, review specialties, hotbar and macro guidance, and save results for later. Gear & Advice ranks modeled upgrades.
- **Review combat:** use Live Meter and its overlay, or open saved logs. Inspect damage, healing, deaths and per-player skills using tables, graphs, timelines and events; group linked pets with their owners.
- **Share and compare:** upload logs as Public, Unlisted or Private, manage your uploads, browse community logs and compare eligible recordings and personal records.
- **Plan encounters:** create and share raid plans, edit your published plans, and replay recorded positions when the log contains supported movement data.
- **Track gathering and dungeon drops:** the Live Meter records what each gather gives (its grade, how many, or a failure) and what each dungeon reward cube holds, and the Gathering page sets them beside everyone's drop rates, the crafting materials of each dungeon included. Sharing your records for those rates is on by default and can be turned off in Settings.
- **Track pets (optional, Windows):** with [Pet Tracker](https://github.com/0Fox2Give/PetTracker) by 0Fox2Give, see your pet ranks and the souls you still need in an overlay window of their own and on the Pet Tracker page. The installer or Settings installs it on request.

Enter your actual available point totals; imported profiles may omit unspent points. PvP optimization is experimental. Missing telemetry stays unavailable, and community rankings depend on comparable, eligible public recordings. The [user guide](docs/user-guide.md) explains these limits and privacy controls.

## Guides

| Guide | Contents |
|---|---|
| [App guide](docs/app.md) | Desktop controls, capture, overlay and troubleshooting |
| [User guide](docs/user-guide.md) | Saved results, log review, uploads, privacy and comparisons |
| [Planner](docs/planner.md) | Build planning and advice |
| [Methodology](docs/methodology.md) | Simulation formulas, data sources and assumptions |
| [Roadmap](docs/COMBAT_ROADMAP.md) | Remaining work and current limitations |
| [Accessibility](docs/accessibility.md) | Accessibility statement, current state and known gaps |

Feature history and version-specific fixes are kept in [Releases](https://github.com/sam-t-anderson/Aion-2-tools/releases).

## For developers

See [CLI and development](docs/cli.md) for running from source, architecture, packaging and contributing. This repository contains the client and GitHub Pages website; server operation belongs in the [server repository](https://github.com/sam-t-anderson/Aion-2-tools-server).

## Community

- [Contributing guide](CONTRIBUTING.md) — how to report bugs, request features, and submit changes.
- [Code of Conduct](CODE_OF_CONDUCT.md) — our community standards.
- [Security policy](SECURITY.md) — how to report a vulnerability privately.
- [Accessibility statement](docs/accessibility.md) — current state and how to give feedback.

## Author

**Spirited - Zikel : Asmodian | Legion: WhaleWatch**

## License

GPL-3.0 (see [LICENSE](LICENSE)). Game data belongs to NCSOFT; community data belongs to its respective sites. This project is fan-made and not affiliated with NCSOFT.

Pet Tracker is 0Fox2Give's separate program (GPL-3.0), used with its author's permission. Aion 2 Calc installs it only when asked, never bundles it, and ports the rules its overlay lists pets by so both show the same; see [Pet Tracker integration](docs/pettracker-integration.md).
