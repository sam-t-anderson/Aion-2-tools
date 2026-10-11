# Contributing to Aion 2 Calc

Thanks for your interest in improving Aion 2 Calc. This project is a desktop
companion and community website for **AION 2** — a build optimizer, combat-log
analyzer, live meter with overlay, and encounter planner. Contributions of all
kinds are welcome: bug reports, fixes, features, docs, and verified game data.

By participating you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## The one rule that matters most: never invent game data

Everything this project displays must be **sourced from real evidence** — live
packets, recorded telemetry, or a citable data source. We do **not** guess,
fabricate, or "fill in" values:

- Damage, healing, DPS, HP, deaths and contribution come from captured packets.
- Timers, coefficients, boss roles, difficulty labels and rankings require
  verifiable sources, and stay **blank / `unavailable`** until one exists.
- Missing telemetry is shown as missing, never as a confident number.

If a change would require an unverified assumption to display something, the
answer is usually to leave it unavailable and open an issue describing the
evidence we'd need. See [`docs/methodology.md`](docs/methodology.md) and the
[roadmap](docs/COMBAT_ROADMAP.md) for how this principle is applied, including
which features are intentionally gated on data we don't yet have.

## Ways to contribute

- **Report a bug** or **request a feature** using the issue templates. For
  meter/parsing issues, a diagnostic capture with known ground truth
  (your character/server, the boss, the outcome) is the single most valuable
  thing you can provide — it lets us reproduce and verify a fix without
  guessing.
- **Improve docs** in `docs/`.
- **Contribute code** following the setup and checks below.
- **Supply verified game data** (boss roles, timers, coefficients) with a source
  we can check.

## Development setup

This repository contains the **client** and the **GitHub Pages website**. The
log-sharing server lives in a
[separate repository](https://github.com/sam-t-anderson/Aion-2-tools-server).

Requirements: Python 3.12+, and Node.js for the quick JavaScript syntax check.

```bash
# From a clone of the repo:
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -e .
```

Live packet capture additionally needs **Npcap** (Windows) or **libpcap**
(macOS/Linux); it is not required to run the tests or work on most features.
See [`docs/cli.md`](docs/cli.md) for running from source, the architecture
overview, and packaging details, and [`docs/install.md`](docs/install.md) for
platform specifics.

## Before you open a pull request

Run the same checks CI runs:

```bash
python -m pytest                              # full test suite
python -m pyflakes aion2calc tools tests      # lint
node --check path/to/edited_file.js           # for any JavaScript you changed
```

Please also:

- Keep the change **focused** — one logical change per PR reviews far faster.
- **Add or update tests** for behavior changes.
- Update **docs and release notes** (`packaging/RELEASE_NOTES.md`) when behavior
  changes that users would notice.
- Match the surrounding **code style** (naming, comment density, idioms). There
  is no separate formatter step beyond pyflakes; mirror the existing code.
- Make sure the diff contains **no secrets** — tokens, credentials, private
  upload keys or personal data.

The pull request template walks through this checklist, including the data
integrity confirmation.

## Branches, commits and releases

- Base your work on `main` and open the PR against `main`.
- Write clear, descriptive commit messages explaining the *why*, not just the
  *what*.
- Releases are cut by bumping the version in `pyproject.toml` and
  `aion2calc/__init__.py` and adding a `packaging/RELEASE_NOTES.md` entry; the
  release pipeline tags and builds on merge to `main`. Maintainers handle the
  version bump for external contributions if you don't.

## Accessibility

The desktop app and website aim to be usable with a keyboard and assistive
technology (semantic roles, ARIA labels and live regions, visible focus).
When adding or changing UI, preserve those patterns — label controls, keep focus
visible, provide text alternatives for meaningful images, and don't rely on
color alone to convey information. See
[`docs/accessibility.md`](docs/accessibility.md) for the current state and known
gaps.

## License

Aion 2 Calc is licensed under the **GPL-3.0**. By contributing, you agree that
your contributions will be licensed under the same license. See
[`LICENSE`](LICENSE).

## Questions

Ask in the [Discord server](https://discord.gg/9y6zkUyvBv) or open a
discussion/issue. Thanks for contributing!
