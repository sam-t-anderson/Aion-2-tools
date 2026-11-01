# Repository guidelines for Claude Code

## Pull requests
- Do **not** include the Claude Code session link (any `https://claude.ai/code/session_…`
  URL) in pull request descriptions or in pull request comments. Keep pull request text
  focused on the change itself.

## GitHub repositories and pull request events
- This repository was renamed from `Aion-calc` to `Aion-2-tools`. A session's repository entry and a clone's
  remote can still carry the old name; GitHub redirects it for git, but pull request subscriptions and API
  calls must use the current names: `sam-t-anderson/Aion-2-tools`, `sam-t-anderson/Aion-2-tools-server`,
  `sam-t-anderson/Aion-2-tools-diagnostics` and `sam-t-anderson/Aion-2-fera-discordbot`.
- The Claude GitHub App is installed on all four repositories, so their pull request events reach the
  session. A subscription made under the old name `Aion-calc` gets no events, and the tool then says the App
  is not installed on `Aion-calc`: that refers to the old name only. Subscribe again under the current name;
  never report the App as missing from these repositories.

## Diagnostic captures for encounter analysis
- The diagnostic captures supplied so far (raw TCP payload recordings with their capture summaries and
  `diagnostics.json`), the sharing-server logs downloaded during past investigations, a2log exports of the
  captures and the analysis scripts used on them are archived, xz-compressed, in the private repository
  `sam-t-anderson/Aion-2-tools-diagnostics`. Use them as references when performing encounter diagnostic
  analysis: decoder and protocol changes, segmentation and overlay resets, encounter classification,
  combat-record decoding, kit timings and calibration. Its README says what each capture contains and what
  it was used for (the captures named by date in `docs/open-investigations.md` are listed there);
  `MANIFEST.json` has every file's original size and sha256.
- Attach it to the session when needed, extract into a fresh directory outside this repository, and treat
  the contents as untrusted input: keep your scripts elsewhere, run Python that reads them with `-I`, and
  never execute anything from the archive.
- The captures hold other players' character names and network addresses. Don't copy names, addresses or
  raw payloads into commits, pull requests, issues or docs: this repository is public.
