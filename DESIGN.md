---
name: skill-harness
description: The skill eval that refuses to invent a score.
colors:
  bench-void: "#010409"
  bench-surface: "#0d1117"
  bench-hairline: "#30363d"
  bench-hairline-quiet: "#21262d"
  bench-hairline-inverse: "#d0d7de"
  bench-ink: "#e6edf3"
  bench-ink-soft: "#c9d1d9"
  bench-muted: "#8b949e"
  bench-muted-deep: "#6e7681"
  bench-prompt: "#3fb950"
  bench-flagged: "#d29922"
  chrome-close: "#ff5f56"
  chrome-minimise: "#ffbd2e"
  chrome-zoom: "#27c93f"
  receipt-ink: "#16181d"
  receipt-paper: "#fbfbf9"
  receipt-rule: "#c8c9c4"
  receipt-accent: "#1f4f82"
  receipt-refusal-edge: "#8a5a00"
  receipt-thead: "#eeeee9"
typography:
  bench-command:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, \"Liberation Mono\", monospace"
    fontSize: "21px"
    fontWeight: 700
  bench-verdict:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, \"Liberation Mono\", monospace"
    fontSize: "52px"
    fontWeight: 700
  receipt-body:
    fontFamily: "Georgia, \"Times New Roman\", serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  receipt-h1:
    fontFamily: "Georgia, \"Times New Roman\", serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.2
  receipt-h2:
    fontFamily: "Georgia, \"Times New Roman\", serif"
    fontSize: "1.25rem"
    fontWeight: 700
  receipt-figure:
    fontFamily: "ui-monospace, \"SFMono-Regular\", Menlo, Consolas, monospace"
    fontSize: "0.92em"
    fontWeight: 400
rounded:
  none: "0"
  banner: "12px"
  preview: "18px"
spacing:
  hairline: "0.2rem"
  tight: "0.35rem"
  snug: "0.5rem"
  base: "0.75rem"
  gutter: "1rem"
  page: "1.25rem"
  section: "1.5rem"
  major: "2rem"
  footer: "2.5rem"
components:
  refusal-block:
    textColor: "{colors.receipt-ink}"
    typography: "{receipt-body}"
    padding: "0.25rem 0 0.25rem 0.6rem"
    rounded: "{rounded.none}"
  rule-block:
    textColor: "{colors.receipt-ink}"
    padding: "0.25rem 0 0.25rem 0.85rem"
    rounded: "{rounded.none}"
  data-table:
    backgroundColor: "{colors.receipt-paper}"
    textColor: "{colors.receipt-ink}"
    padding: "0.35rem 0.5rem"
    rounded: "{rounded.none}"
  table-head:
    backgroundColor: "{colors.receipt-thead}"
    textColor: "{colors.receipt-ink}"
    padding: "0.35rem 0.5rem"
  terminal-frame:
    backgroundColor: "{colors.bench-surface}"
    textColor: "{colors.bench-ink}"
    rounded: "{rounded.banner}"
---

# Design System: skill-harness

<!--
EXTRACTED, NOT AUTHORED. Every value in this file was read out of the repository on
2026-08-25. Nothing here was invented to fill a section, and no divergence was harmonised
away. Where two surfaces disagree, this file records the disagreement rather than picking a
winner — see "The Two Systems" below. That choice is deliberate: a design document that
resolves an open question by fiat is worse than one that names it.
-->

## Overview

**Creative North Star: "The Test Bench"**

This is a measurement instrument, and its surfaces are built to look like one. The governing
commitment is legible in the code before it is legible in any brand document: the one
hand-written stylesheet opens by declaring that refusals are *"styled as ordinary primary
content -- never dimmed, collapsed, or pushed into a footnote -- because a refusal is a result
here, not an absence."* That sentence is the design system. Everything below is its
consequence.

The instrument's job is to say what can honestly be said about a difference, and often the
honest answer is that there is not enough to call it. A system whose product is sometimes a
refusal cannot style refusal as failure. So there is no dimmed state, no collapsed empty
state, no grey "no data" placeholder anywhere in this repository. A refusal gets a heavier
left edge than a measured figure gets.

⚠ **This project currently runs two distinct visual systems**, and this document records both
rather than merging them. See the section immediately below. The North Star above is common to
both; the surface treatment is not.

**Key Characteristics:**

- Refusal is primary content, never a degraded state.
- Flat by construction — no shadow token exists anywhere in the repository.
- Monospace carries every figure, token, command and identifier.
- Rules and borders build hierarchy; nothing floats.
- Numbers appear only where a receipt supplies them.

## The Two Systems

⛔ **This section is a finding, not a specification.** It is recorded here because a
`DESIGN.md` that describes only one of two live systems would be false.

| | **Bench surfaces** — `assets/*.svg` | **Receipt surfaces** — `sitegen/style.css` |
|---|---|---|
| Where | `banner-dark.svg`, `banner-light.svg`, `social-preview.svg` | the published site at `mrbinnacle.github.io/skill-harness` |
| Ground | near-black (`#010409` / `#0d1117`) | warm paper (`#fbfbf9`) |
| Body face | monospace only | **Georgia serif** |
| Accent | prompt green `#3fb950` | navy `#1f4f82` |
| Warning / refusal | flagged amber `#d29922` | ochre edge `#8a5a00` |
| Corner | 12–18px radius on the terminal frame | no radius declared anywhere |
| Metaphor | a terminal window | a printed calibration certificate |

**What the two agree on.** Both express the same doctrine, and they arrived at it separately.
Both give refusal its own dedicated visual channel. Both reserve monospace for figures and
tokens. Both build hierarchy from rules rather than shadows. Both are flat. The semantic
*roles* are the same set on each side — ground, ink, hairline, accent, refusal-edge — and only
the *values* differ.

**What they disagree on.** Ground polarity, body typeface, and accent hue. Those are surface
choices, and they are separable from the doctrine both surfaces already implement correctly.

**Status: unresolved, and deliberately left so.** The bench surfaces match the token set used
across the owner's two repositories. The receipt surfaces do not, and were built while the
shared brand document was unread. Which system governs is an owner decision recorded in
`MrBinnacle/skill-harness#216`. This file does not pre-empt it.

## Colors

Two palettes, grouped by the surface each governs. Neither is a subset of the other.

### Primary — bench

- **Prompt Green** (`#3fb950`): the `$` on a command line, and confirmed success. Nothing
  else. It appears exactly twice per banner and once in the social preview's footer URL.
- **Flagged Amber** (`#d29922`): warning-class verdict tokens. Carries `→ CUT` on the social
  preview and `→ UNMEASURED` on the dark banner.

### Primary — receipt

- **Certificate Navy** (`#1f4f82`): every link on the published site. The site's only chromatic
  accent, and it is used for navigation, not emphasis.
- **Refusal Ochre** (`#8a5a00`): the 4px left edge on `.refusal` and `.refused`. This is the
  most semantically loaded colour in the repository — it marks the thing the instrument exists
  to be able to say.

### Neutral — bench

- **Void** (`#010409`): the social preview's outer field, behind the terminal frame.
- **Surface** (`#0d1117`): the terminal window itself.
- **Hairline** (`#30363d`) and **Quiet Hairline** (`#21262d`): the frame stroke and the title-bar
  divider respectively. Two weights of the same idea.
- **Inverse Hairline** (`#d0d7de`): the frame stroke on `banner-light.svg` only. ⭐ The "light"
  banner is not a light-mode banner — its interior is the same `#0d1117` Surface as the dark one.
  Only the outer stroke changes, and the file says why: *"dark interior; light border so it sits
  well on a light README."* The terminal is always dark; the frame adapts to what surrounds it.
- **Ink** (`#e6edf3`), **Soft Ink** (`#c9d1d9`), **Muted** (`#8b949e`), **Deep Muted**
  (`#6e7681`): a four-step text ramp, brightest for the command being run, dimmest for the
  window's own label.

### Neutral — receipt

- **Document Ink** (`#16181d`): body text. Near-black, not black.
- **Paper** (`#fbfbf9`): the page ground. Warm off-white.
- **Rule** (`#c8c9c4`): every table border, every `h2` underline, the footer divider.
- **Table Head** (`#eeeee9`): the only fill in the entire stylesheet.

### Window Chrome

- **`#ff5f56` / `#ffbd2e` / `#27c93f`**: macOS traffic-light dots in the banner title bars.

⚠ These three are borrowed platform chrome, not brand colours. `#27c93f` sits 8 hue-degrees
from Prompt Green `#3fb950` and does not mean success — it means "this is a window." Do not
consolidate them into the semantic palette and do not reuse them outside a title bar.

### Named Rules

**The Refusal-Is-Louder Rule.** A refusal gets a 4px left edge and `font-weight: 600`. A
measured figure gets neither. When a refusal and a measurement sit side by side, the refusal is
the heavier element on the page. This inverts the usual treatment on purpose and it is the
single most important rule in this system.

**The Two-Greens Rule.** `#3fb950` means a prompt or a confirmed success. `#27c93f` means a
window control. They are never interchangeable despite being nearly the same colour.

**The Borrowed-Ground Rule.** The bench neutrals are GitHub Primer's own values. They are used
so the assets sit native in the environment that renders them, not as an independent palette
choice. Changing the ground means leaving that environment.

## Typography

**Display Font:** none. This system has no display face.
**Body Font (receipt surfaces):** Georgia, with Times New Roman and generic serif as fallbacks.
**Label/Mono Font:** `ui-monospace`, with SFMono-Regular, Menlo, Consolas and Liberation Mono as
fallbacks. This is the only face used on bench surfaces.

**Character:** the receipt surfaces read as a printed document — a serif body, a 62rem measure,
1.55 line-height. The bench surfaces read as a terminal — mono at every size, weight 700 for
anything the instrument asserts. The pairing is not a designed pairing; it is two surfaces built
at different times.

### Hierarchy — receipt surfaces

- **H1** (700, `1.75rem`, line-height 1.2): one per page, the page's subject.
- **H2** (700, `1.25rem`, `border-bottom: 1px solid` Rule): section headings. The underline is
  structural, not decorative — it is the only separator the page has.
- **H3** (700, `1.05rem`): subsection headings. No rule.
- **Body** (400, `1rem`, line-height 1.55, max-width 62rem): prose.
- **Verdict** (`1.15rem`): larger than body, smaller than H2. A verdict is not a heading and is
  not body text; it gets its own step.
- **Figure / code / verdict-token** (mono, `0.92em`): every number, identifier and claim-state
  token. Slightly smaller than the surrounding serif so the x-heights match.
- **Footer** (`0.85rem`).

### Hierarchy — bench surfaces

- **Verdict** (mono 700, up to `52px`): the largest text on any asset. `→ CUT`, `→ UNMEASURED`.
- **Command** (mono, `21–30px`): the invocation being demonstrated.
- **Explanation** (mono, `24px`, Soft Ink).
- **Subtitle / legend / footer** (mono, `19–22px`, Muted).
- **Window label** (mono, `15–20px`, Deep Muted): the dimmest text on the asset.

### Named Rules

**The Mono-Carries-The-Claim Rule.** Every figure, token, command, identifier and evidence value
is monospace on both surfaces. Serif is for prose only. If a reader could copy it into a
terminal or cite it as a number, it is mono.

**The No-Display-Face Rule.** There is no display typeface and none is authorised. Scale and
weight carry emphasis. A `52px` mono verdict is this system's equivalent of a headline.

## Layout

**Receipt surfaces.** A single centred column, `max-width: 62rem`, `padding: 0 1.25rem 3rem`.
No grid framework, no sidebar, no multi-column body. The header is a flex row with
`justify-content: space-between` and `align-items: baseline`, wrapping at narrow widths. Two
layout primitives exist beyond the column:

- `dl` — a two-column definition grid, `minmax(10rem, max-content) 1fr`. This is the workhorse
  for cost-beside-evidence pairs.
- `.beside` — a wrapping flex row whose children are `flex: 1 1 20rem`. Used to place two
  related blocks side by side, collapsing to stacked below roughly 40rem.

Tables are `width: 100%` with `border-collapse: collapse` and left-aligned, top-aligned cells.

**Bench surfaces.** Fixed viewBox compositions: `780×176` for banners, `1280×640` for the social
preview. The preview insets its terminal frame `80px` from a `1280×640` field, giving a safe
area consistent with GitHub's crop behaviour.

**Spacing.** ⚠ The receipt stylesheet uses roughly sixteen distinct rem values and does not
follow a regular scale. The `spacing` tokens in this file's frontmatter name the values that
actually recur; they are a description of current practice, not a scale the code was built
against. Do not treat them as a ramp.

### Named Rules

**The One-Column Rule.** The published site is a single column at every width. Evidence is read
top to bottom in the order the generator emitted it. No layout may reorder or parallelise it.

## Elevation & Depth

**This system is flat, and the flatness is total.** There is no `box-shadow` anywhere in the
repository's stylesheet. There is no gradient, no blur, no glow, no opacity layering. Depth is
conveyed by exactly three devices:

1. **1px rules** in Rule (`#c8c9c4`) — table borders, `h2` underlines, the footer divider.
2. **A 2px bottom border** in Document Ink under the site header — the single heaviest line on
   the page, and the only thing that separates chrome from content.
3. **4px left edges** — Document Ink for `.rule`, Refusal Ochre for `.refusal`. These are the
   system's emphasis mechanism, replacing the callout boxes and tinted panels a conventional
   system would use.

On bench surfaces, the terminal frame is a 2px Hairline stroke over Surface fill on a Void
field. That two-tone separation is the only depth cue, and it is a border, not a shadow.

### Named Rules

**The No-Shadow Rule.** No shadow token exists and none may be added. If an element needs
separation, give it a rule or a left edge. This is not a stylistic preference — a shadow implies
a floating object, and nothing on an evidence surface floats.

## Shapes

**Receipt surfaces have no radius at all.** `border-radius` does not appear in the stylesheet.
Every table cell, every refusal block, every header is a hard rectangle.

**Bench surfaces round only the terminal frame** — `rx="12"` on banners, `rx="18"` on the social
preview — because that shape is quoting a window chrome, not expressing a form language. The
circles in the title bar are `r="6"` (banner) and `r="8"` (preview).

The form language is otherwise entirely orthogonal: rectangles, 1px rules, 4px left edges, and a
2px header underline.

### Named Rules

**The Square-Unless-Quoting Rule.** Radius is permitted only where the asset is depicting a
window. Content surfaces are square.

## Components

### Refusal Block — the signature component

- **Character:** the thing this instrument exists to be able to render. Never a degraded state.
- **Shape:** 4px left border in Refusal Ochre (`#8a5a00`), no radius.
- **Padding:** `0.25rem 0 0.25rem 0.6rem`.
- **Weight:** `font-weight: 600` — heavier than surrounding body text.
- **Selectors:** `.refusal`, `.refused`.
- **Behaviour:** styled identically whether the refusal is a whole verdict or a single missing
  figure. The stylesheet's own comment states the requirement: *"boxed so it cannot be mistaken
  for a missing value."*

### Rule Block

- **Character:** a quoted rule or governing clause.
- **Shape:** 4px left border in Document Ink, no radius.
- **Padding:** `0.25rem 0 0.25rem 0.85rem`.
- **Relationship to Refusal Block:** structurally identical, differing only in edge colour and
  weight. The pair is the system's entire callout vocabulary.

### Absent Marker

- **Style:** `font-style: italic`, no border, no colour change.
- **Purpose:** marks a genuinely absent value, as distinct from a refused one.

⭐ **The distinction between `.absent` and `.refusal` is load-bearing.** An absence is quiet and
italic. A refusal is bordered and bold. A system that rendered them the same way would be
claiming the instrument had no answer when in fact it declined to give one.

### Data Table

- **Border:** 1px Rule on every cell; `border-collapse: collapse`.
- **Head:** Table Head fill (`#eeeee9`), the only fill in the stylesheet.
- **Caption:** left-aligned, `font-weight: 700`, `padding-bottom: 0.3rem`.
- **Cells:** `0.35rem 0.5rem` padding, `text-align: left`, `vertical-align: top`.
- **Width:** always 100%.

### Definition Grid

- **Style:** CSS grid, `minmax(10rem, max-content) 1fr`, gap `0.2rem 1rem`.
- **Terms:** `font-weight: 700`. **Definitions:** no margin.
- **Purpose:** the cost-beside-evidence pairing.

### Site Header

- **Style:** flex row, `space-between`, baseline-aligned, wrapping with `gap: 0.5rem 1.5rem`.
- **Border:** 2px solid Document Ink underneath — the page's heaviest line.
- **Wordmark:** `font-weight: 700`, `letter-spacing: 0.02em`.
- **Nav:** horizontal `ul`, `gap: 1rem`, no list markers, links in Certificate Navy.

### Terminal Frame (bench surfaces)

- **Style:** Surface fill, 2px Hairline stroke, `rx` 12–18.
- **Title bar:** three chrome circles, then the repository name in Deep Muted, then a 1.5px
  Quiet Hairline divider.
- **Body:** a `$` prompt in Prompt Green, the command in Ink, arguments in Deep Muted, then a
  verdict line led by `→` in Flagged Amber at the largest size on the asset.

## Do's and Don'ts

### Do:

- **Do** give every refusal the 4px Refusal Ochre edge and `font-weight: 600`. The Refusal-Is-
  Louder Rule is the system's defining commitment.
- **Do** keep `.absent` italic and unbordered, distinct from `.refusal`. The two states mean
  different things.
- **Do** set every figure, token, command and identifier in monospace at `0.92em` on receipt
  surfaces.
- **Do** build separation from 1px rules, the 2px header border, and 4px left edges.
- **Do** keep the published site a single column at every width.
- **Do** keep Prompt Green to the `$` prompt and confirmed success only.

### Don't:

- **Don't** add a `box-shadow`, gradient, blur, glow or opacity layer. None exists today and the
  No-Shadow Rule forbids introducing one.
- **Don't** add `border-radius` to a content surface. Radius exists only where an asset depicts a
  window.
- **Don't** dim, collapse, abbreviate or footnote a refusal. The stylesheet's opening comment
  forbids it and the site's purpose depends on it.
- **Don't** reuse the window-chrome greens (`#27c93f`) as a success colour. They mean "window."
- **Don't** introduce a display typeface. Scale and weight carry emphasis.
- **Don't** render a number that no receipt supplies. The generator refuses rather than
  interpolates; the visual layer must not reintroduce what the generator declined to emit.
- **Don't** treat the frontmatter `spacing` tokens as a designed ramp. They describe current
  practice and the current practice is irregular.
- **Don't** use the prose form `Skill Harness` for a command, URL, package identifier or
  evidence label. Those are always `skill-harness`, lowercase and hyphenated. The two forms are
  a deliberate convention, not drift — see Known Divergences.

## Known Divergences

⛔ **These are measured defects and open questions, recorded so a future pass does not have to
rediscover them. None is resolved here.**

1. **The display name renders two ways, and on the evidence this is a convention rather than a
   defect.** ⚠ An earlier reading of this file called the title-cased form an outlier. That was
   wrong, and the correction is recorded here rather than silently applied.

   - **`skill-harness`** — the identifier form. `pyproject.toml:6`, `README.md:8`, both banner
     SVGs, the social preview, the GitHub repository name, the CLI invocation.
   - **`Skill Harness`** — the prose form, used as a proper noun. `CONTRIBUTING.md:1`
     ("Contributing to Skill Harness"), `CLAUDE.md:52`, `docs/case-studies/`, and
     `src/skill_harness/sitegen/templates/page.html:11`
     (`<p class="wordmark">Skill Harness: published receipts</p>`).

   The site wordmark is prose, and it matches how the repository already writes the name in
   prose everywhere else. It is **consistent**, not divergent.

   ⭐ The shared brand document bans the rename in four named contexts — *"inside commands, URLs,
   package identifiers, or evidence labels."* A page wordmark is none of the four, so the ban
   does not reach it. Anyone acting on a "make the name render one way" instruction should read
   that scope before changing anything: collapsing the two forms would break the prose register
   across `CONTRIBUTING.md`, `CLAUDE.md` and the case studies to fix a wordmark that is not
   broken.

   **What IS worth checking** is the inverse: whether the identifier form leaks into prose, or
   the prose form leaks into a command, URL, package identifier or evidence label. Neither was
   observed during this extraction. `src/skill_harness/` is PEP 8 module naming and is not a
   display rendering at all.

2. **The two systems described above are unreconciled**, and the receipt surfaces were built
   while the shared brand document was unread. Tracked in `#216`.

3. **The dark banner's verdict token draws from a different enum than the social preview's.**
   `banner-dark.svg:14` renders `→ UNMEASURED`; `social-preview.svg:18` renders `→ CUT`.
   `UNMEASURED` is a live clause status (`src/skill_harness/aggregation/status.py:52`,
   `aggregation/profile.py:54`); `CUT` and `CANT_TELL_YET` are verdicts
   (`aggregation/verdict.py:119`). Both tokens are current. Whether presenting a status token in
   the verdict position is intended is **not established by this document** — it is flagged for
   the owner, not asserted as an error.

4. **The light/dark banner pair does not do what its filenames imply, and this may be a defect.**
   `banner-light.svg` and `banner-dark.svg` are byte-identical except for one attribute: the
   frame stroke, `#d0d7de` versus `#30363d`. Both keep the `#0d1117` dark interior. A reader
   expecting a light-mode asset gets a dark terminal with a pale outline. The file's own comment
   says this is intentional — *"dark interior; light border so it sits well on a light README"* —
   so it is recorded here as a documented decision rather than an error. ⚠ It is flagged because
   the naming does not carry the intent, and a future pass restyling "the light banner" would
   likely change the wrong thing.
