<!-- Thanks for contributing to Aion 2 Calc. Keep PRs focused; a small,
     reviewable change merges faster than a large one. -->

## Summary

<!-- What does this change do, and why? Link any related issue: Fixes #123 -->

## Type of change

- [ ] Bug fix (no behavior change beyond fixing the bug)
- [ ] New feature / enhancement
- [ ] Documentation only
- [ ] Build / packaging / CI
- [ ] Refactor (no functional change)

## Data integrity

<!-- This project never invents game data. If your change touches combat
     parsing, the optimizer, catalogs, timers, boss roles or any displayed
     number, confirm the following. Delete this section only for pure
     docs/CI/refactor changes. -->

- [ ] Every displayed value is sourced from real packets, recorded telemetry or a cited source — nothing is fabricated or guessed.
- [ ] Missing or unverified data stays `unavailable`/blank rather than being filled with an assumption.
- [ ] Any new game-mechanics claim (timers, coefficients, roles, difficulty) is backed by verifiable evidence referenced in the PR or an existing data file.

## Checklist

- [ ] `python -m pytest` passes locally.
- [ ] `python -m pyflakes aion2calc tools tests` is clean.
- [ ] JavaScript changes pass `node --check` on the edited files.
- [ ] Docs / release notes updated if user-facing behavior changed.
- [ ] No secrets, tokens, credentials or personal data in the diff.

## Testing

<!-- How did you verify this? Commands run, captures replayed, manual steps,
     screenshots for UI changes. -->
