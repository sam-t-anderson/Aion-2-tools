# Accessibility statement

_Last updated: 2026-10-11 · applies to Aion 2 Calc 0.2.201 and the current
GitHub Pages website._

Aion 2 Calc aims to be usable by as many people as possible, including people
who rely on keyboards and assistive technologies. This statement describes what
is in place today, the known limitations, and what is planned. It is written to
be honest about the current state rather than to claim a certification we have
not earned — the same principle the project applies to game data.

## Scope

This statement covers:

- The **desktop application** (build optimizer, combat review, Live Meter and
  its transparent overlay, planner), whose interface is rendered as local web
  pages.
- The **community website** published from this repository to GitHub Pages
  (logs, leaderboards, builds, crafting, plans).

It does not cover the AION 2 game client itself, or third-party sites and
provider map viewers embedded or linked from the app.

## Conformance

We target the **W3C Web Content Accessibility Guidelines (WCAG) 2.1 Level AA**
as a goal. The app and website are **partially conformant**: most of the
interface follows these guidelines, but the project has **not** undergone a
formal third-party audit or systematic assistive-technology testing, so some
content may not yet fully meet every criterion.

## What is in place today

- **Semantic structure and labels.** Pages declare their language (`lang="en"`)
  and use semantic landmarks and ARIA roles — tab lists and tab panels, groups,
  lists, images, buttons, alerts and status regions — so screen readers can
  describe the interface.
- **Live regions.** Dynamic areas (capture status, meter updates, connection
  and identity state, save/import results) use `role="status"`/`role="alert"`
  and `aria-live` so updates are announced without stealing focus, with
  `aria-busy` where work is in progress.
- **Named controls.** Interactive controls carry `aria-label`,
  `aria-labelledby`, `aria-pressed`, `aria-selected`, `aria-controls` and
  `aria-expanded` so their purpose and state are exposed, not just implied by
  visuals.
- **Keyboard operation.** The interface is built from native buttons, links and
  form controls that are reachable and operable with the keyboard, and the
  overlay provides visible `:focus-visible` outlines on its controls.
- **Text alternatives.** Meaningful images provide alternative text, and
  decorative elements are hidden from assistive technology with
  `aria-hidden`.
- **Text size.** Since 0.2.323 no text in the app or on the website is smaller
  than 16 px (the page text, tables, labels, notes and code included), and the
  combat logs and their reviews are drawn at 125 %. The overlay keeps its own
  size setting, below.
- **Theming and readable defaults.** The transparent overlay honors the
  operating system's light/dark preference (`prefers-color-scheme`), and the
  overlay now offers user-adjustable **font family, size (80–160%) and weight**,
  **text color pickers**, an opacity control, and adjustable layout (width, row
  height, number of rows) so you can tune legibility to your display.
- **Motion is limited and controllable.** On-screen animation is minimal. The
  long-name scroll is **hover-activated only** (names that fit never move), and
  the live-millisecond DPS interpolation is **off by default** with a user
  refresh-rate control to slow or disable it.
- **Honors "reduce motion".** The app and website now detect the operating
  system's **`prefers-reduced-motion`** setting: when it is on, animations and
  transitions collapse to near-instant and smooth scrolling is disabled across
  every page, so motion-sensitive users get a still interface (in addition to the
  per-feature controls above).
- **Visible keyboard focus.** Every interactive control shows a clear focus
  outline when reached by keyboard (`:focus-visible`), including the form fields
  that previously replaced the outline with only a border change. Pointer clicks
  keep the quiet border style, so the outline appears for keyboard use.
- **Skip to content.** A "Skip to content" link is the first focusable element on
  every page — hidden until a keyboard user tabs to it, then it jumps past the
  navigation to the main content (the desktop app and all website pages).

## Known limitations

We are aware of the following gaps and are working on them:

- **No formal audit.** Conformance has not been independently verified, and we
  have not completed systematic screen-reader testing across platforms.
- **Color contrast.** The game-styled dark theme has not been fully audited for
  WCAG AA contrast ratios across every element; some secondary/muted text and
  chart colors may fall short.
- **Data-dense visuals.** Combat graphs, timelines and the planner board are
  highly visual. Underlying numbers are available in accompanying tables, but
  some graphical views do not yet have a complete non-visual equivalent.
- **Third-party content.** Embedded provider map viewers and externally linked
  pages are outside our control and may not meet the same standard.

These items are tracked alongside the broader quality-of-life work in the
[roadmap](COMBAT_ROADMAP.md); the overlay visual-settings pass there (font,
size, weight, color and background controls) is part of making the interface
adjustable to individual needs.

## Feedback

If you encounter an accessibility barrier, please tell us — your reports
directly shape what we prioritize:

- Open an issue on
  [GitHub](https://github.com/sam-t-anderson/Aion-2-tools/issues) (please
  mention "accessibility"), or
- Reach us on the [Discord server](https://discord.gg/9y6zkUyvBv).

Describe the page or screen, what you were trying to do, the barrier you hit,
and the assistive technology, browser or operating system you were using if
relevant. We will do our best to respond and to offer the information or
function you need in an accessible form.
