# Security Policy

Thank you for helping keep Aion 2 Calc and its users safe.

## Supported versions

Aion 2 Calc ships frequently, and only the **latest release** is supported with
security fixes. Always update to the newest version from
[Releases](https://github.com/sam-t-anderson/Aion-2-tools/releases) before
reporting; the desktop app can also apply updates automatically.

| Version | Supported |
| ------- | --------- |
| Latest release | ✅ |
| Older releases | ❌ |

## Reporting a vulnerability

**Please do not open a public issue, pull request, or Discord message for
security vulnerabilities.** Public disclosure before a fix is available puts
users at risk.

Instead, report privately through GitHub Security Advisories:

> **[Report a vulnerability »](https://github.com/sam-t-anderson/Aion-2-tools/security/advisories/new)**

This opens a private channel visible only to you and the maintainers. If you
cannot use GitHub advisories, contact the maintainer privately via the
[Discord server](https://discord.gg/9y6zkUyvBv).

When reporting, please include:

- A description of the issue and its potential impact.
- Steps to reproduce, or a proof of concept.
- The affected component (desktop app, bundled website, build/update pipeline)
  and the version.
- Any suggested remediation, if you have one.

Please **do not include** real credentials, private upload tokens, or other
secrets in your report — describe where they live rather than pasting them.

## What to expect

This is a small, community-maintained project, so responses are best-effort:

- We aim to acknowledge a report within **7 days**.
- We will work with you on a fix and keep you updated on progress.
- Once a fix is released, we are happy to credit you in the advisory and release
  notes (or keep you anonymous if you prefer).
- We ask that you give us a reasonable chance to release a fix before any public
  disclosure (coordinated disclosure).

## Scope

In scope:

- The desktop client (packet capture, parsing, optimizer, overlay, updater,
  installer/packaging) in this repository.
- The GitHub Pages website bundled from this repository.

Out of scope / handled elsewhere:

- The log-sharing **server** lives in a separate repository
  ([Aion-2-tools-server](https://github.com/sam-t-anderson/Aion-2-tools-server));
  report server-side issues there, or via the private channels above if you are
  unsure.
- Vulnerabilities in third-party dependencies, the game client, Npcap/libpcap,
  or external data sources should be reported to their respective maintainers.
  If such an issue affects Aion 2 Calc users directly, let us know so we can
  update or mitigate.

## A note on how this app works

Aion 2 Calc reads network packets locally to analyze your own combat, similar to
other community combat meters. It does not modify the game, inject into the game
process, or automate play. Captured data stays on your machine unless you choose
to upload a log, and uploads follow the privacy controls described in the
[user guide](docs/user-guide.md). Please keep these boundaries in mind when
assessing and reporting security concerns.
