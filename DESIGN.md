---
name: skill-harness
description: The skill eval that refuses to invent a score.
# Declared system: Test Bench. Every `bench-*` token is declared for every surface.
# Every `receipt-*` token and every `chrome-*` token is RETIRING: still on the tree today
# (the conformance check must stay green on main), removed by the surface ticket named
# beside it. Do not use a retiring token on a new surface.
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
  bench-cant-tell: "#58a6ff"        # declared, unused on the tree today; the refusal edge takes it at #308
  chrome-close: "#ff5f56"           # retiring at #309 (gone from the social preview at #310; the banners still carry it)
  chrome-minimise: "#ffbd2e"        # retiring at #309 (gone from the social preview at #310; the banners still carry it)
  chrome-zoom: "#27c93f"            # retiring at #309 (gone from the social preview at #310; the banners still carry it)
  receipt-ink: "#16181d"            # retiring at #308
  receipt-paper: "#fbfbf9"          # retiring at #308
  receipt-rule: "#c8c9c4"           # retiring at #308
  receipt-accent: "#1f4f82"         # retiring at #308
  receipt-refusal-edge: "#8a5a00"   # retiring at #308
  receipt-thead: "#eeeee9"          # retiring at #308
typography:
  bench-command:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, \"Liberation Mono\", monospace"
    fontSize: "21px"
    fontWeight: 700
  bench-verdict:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, \"Liberation Mono\", monospace"
    fontSize: "52px"
    fontWeight: 700
  bench-prose:                      # declared for the site at #308; not on the tree today
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  bench-h1:                         # declared for the site at #308
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.2
  bench-h2:                         # declared for the site at #308
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
  bench-figure:                     # declared for the site at #308
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, \"Liberation Mono\", monospace"
    fontSize: "0.92em"
    fontWeight: 400
  receipt-body:                     # retiring at #308
    fontFamily: "Georgia, \"Times New Roman\", serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  receipt-h1:                       # retiring at #308
    fontFamily: "Georgia, \"Times New Roman\", serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.2
  receipt-h2:                       # retiring at #308
    fontFamily: "Georgia, \"Times New Roman\", serif"
    fontSize: "1.25rem"
    fontWeight: 700
  receipt-figure:                   # retiring at #308 (bench-figure replaces it)
    fontFamily: "ui-monospace, \"SFMono-Regular\", Menlo, Consolas, monospace"
    fontSize: "0.92em"
    fontWeight: 400
  # Retiring sizes: on the tree today, removed by the ticket named; declared so the fence is green on main.
  retiring-site-h3:                 # retiring at #308
    fontSize: "1.05rem"
  retiring-site-verdict:            # retiring at #308
    fontSize: "1.15rem"
  retiring-site-footer:             # retiring at #308
    fontSize: "0.85rem"
  retiring-banner-label:            # retiring at #309
    fontSize: "15px"
  retiring-banner-readout:          # retiring at #309
    fontSize: "19px"
rounded:
  none: "0"
  banner: "12px"                    # retiring at #309 with the window chrome
spacing:
  # Extracted values, still on the tree; #308 moves the stylesheet onto the declared scale below.
  hairline: "0.2rem"
  tight: "0.35rem"
  snug: "0.5rem"
  base: "0.75rem"
  gutter: "1rem"
  page: "1.25rem"
  section: "1.5rem"
  major: "2rem"
  footer: "2.5rem"
  # Declared scale (primer input, unopposed by every SME fired): 4 8 16 24 32 48 96 px.
  scale-1: "4px"
  scale-2: "8px"
  scale-3: "16px"
  scale-4: "24px"
  scale-5: "32px"
  scale-6: "48px"
  scale-section: "96px"
components:
  refusal-block:
    textColor: "{colors.bench-ink}"
    edgeColor: "{colors.bench-cant-tell}"
    typography: "{bench-prose}"
    padding: "0.25rem 0 0.25rem 0.6rem"
    rounded: "{rounded.none}"
  rule-block:
    textColor: "{colors.bench-ink}"
    edgeColor: "{colors.bench-ink}"
    padding: "0.25rem 0 0.25rem 0.85rem"
    rounded: "{rounded.none}"
  data-table:
    backgroundColor: "{colors.bench-surface}"
    textColor: "{colors.bench-ink}"
    padding: "0.35rem 0.5rem"
    rounded: "{rounded.none}"
  table-head:
    backgroundColor: "{colors.bench-void}"
    textColor: "{colors.bench-ink}"
    padding: "0.35rem 0.5rem"
  readout-frame:
    backgroundColor: "{colors.bench-surface}"
    textColor: "{colors.bench-ink}"
    strokeColor: "{colors.bench-hairline}"
    rounded: "{rounded.none}"
---

# Design System: skill-harness

<!--
DECLARED 2026-08-30 (skill-harness#307, spec #306, parent #216) by the Direction seat of the
owner's private research repository (the design head). The values were extracted from the repository on 2026-08-25; the
rules were produced by the installed taste SMEs, fired in order, with the S370 context pack and
the Brand Kit primer v0.1 as inputs. Every rule names the skill that produced it in brackets. A
live repository fact outranks every SME; the facts that bound this pass are listed under
"What the harness must never do". Owner rulings in force: harvest the installed taste skills;
do not hand-roll taste; the Notion primer is an input, the SMEs decide.
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

**Key Characteristics:**

- Refusal is primary content, never a degraded state.
- Flat by construction: no shadow token exists anywhere in the repository.
- Monospace carries every figure, token, command and identifier.
- Rules and borders build hierarchy; nothing floats.
- Numbers appear only where a receipt supplies them.
- One system, dark-locked, on every surface.

## The One System

**Declared: the Test Bench governs every public surface of this repository.** Ground is
Primer dark (`bench-void` behind `bench-surface`), separation is hairlines, claims are system
mono, radius is zero, and nothing sits behind a measurement. The receipt body's paper system
(Georgia, cream `#fbfbf9`, navy `#1f4f82`) is **retired**, not kept as an exception. It leaves
the stylesheet at #308.

Why retired and not excepted, in the SMEs' own terms:

- One theme per page, locked; a light section inside a dark page reads as a different website
  mid-scroll. A bench shell around a paper body is that sandwich. [design-taste-frontend §4.11;
  redesign-existing-projects, "Random dark sections in a light mode page"]
- One design system per project. For a GitHub-native developer tool the system is Primer, and
  the bench neutrals are already Primer's values. [design-taste-frontend §2.A]
- Georgia is a generic serif and serif is banned in software UI; the receipts site is a table
  and readout surface. [stitch-design-taste §3; design-taste-frontend §4.1]
- One palette per project; warm and cool greys do not mix. The paper greys are warm, the
  bench greys are cool. [design-taste-frontend §4.2; redesign-existing-projects, "Mixing warm
  and cool grays"]

What the paper system was carrying, and where it goes: the refusal edge. A refusal must stay
louder than a measurement (a live fact, `style.css:1-7`). On the bench the edge takes
`bench-cant-tell` `#58a6ff`, the third semantic colour, whose role is "can't-tell, unmeasured,
or refused state". Ochre `#8a5a00` retires with the paper because it fails contrast on
`bench-surface` and because it was never one of the three colours that carry claim-state
meaning. [fact: the semantic three carry claim-state meaning; design-taste-frontend §4.2
colour-consistency lock leaves no room for a fourth state colour]

The spec's candidate (bench chrome, paper body as one recorded exception) was put to the SMEs
and refused by three of them on the theme-lock, one-system and one-palette rules above. No SME
argued for it. The owner's deferral to `#216` is closed by this declaration.

*Revisit if:* the owner reads this page and rules for a light scheme; the fix is a second
Primer token set under `prefers-color-scheme: light`, not a return of paper.

## Colors

One palette. Every value is a `bench-*` token.

### Semantic three

These carry claim-state meaning and nothing else. They are never decorative, never an accent,
never a brand colour.

- **Prompt Green** (`#3fb950`, `bench-prompt`): the `$` on a command line, and confirmed
  success. Nothing else.
- **Flagged Amber** (`#d29922`, `bench-flagged`): warning-class state. Carries `→ CUT` on the
  social preview and `→ UNMEASURED` on the banner today.
- **Can't-Tell Blue** (`#58a6ff`, `bench-cant-tell`): can't-tell, unmeasured or refused state.
  The refusal edge on the site. Declared here for the first time; no surface uses it on the
  tree today.

### Neutrals

- **Void** (`#010409`): the outer field and the table head.
- **Surface** (`#0d1117`): the page ground and the readout frame.
- **Hairline** (`#30363d`) and **Quiet Hairline** (`#21262d`): every rule, border and divider.
  Two weights of the same idea.
- **Inverse Hairline** (`#d0d7de`): the frame stroke where the asset sits on a light README.
- **Ink** (`#e6edf3`), **Soft Ink** (`#c9d1d9`), **Muted** (`#8b949e`), **Deep Muted**
  (`#6e7681`): a four-step text ramp, brightest for the claim, dimmest for the label.

### Retiring

- **`receipt-*`** (paper, document ink, rule, navy, ochre, table head): leave at #308.
- **`chrome-*`** (`#ff5f56` / `#ffbd2e` / `#27c93f`, the macOS traffic lights): leave at #309
  and #310. They are decorative status dots on a fake window; both are named tells.
  [design-taste-frontend §9.F "decorative status dots", "fake terminal"]

### Named Rules

**The Refusal-Is-Louder Rule.** A refusal gets a 4px left edge in Can't-Tell Blue and
`font-weight: 600`. A measured figure gets neither. When a refusal and a measurement sit side
by side, the refusal is the heavier element on the page. [fact, `style.css:1-7`; unchanged]

**The Semantic-Only-Chroma Rule.** No colour outside the semantic three appears on any surface.
Links carry no chromatic accent; the underline is the affordance, in Ink, and the hover state
is Soft Ink. [design-taste-frontend §4.2, max one accent, and the accent here is spent on
state; stitch-design-taste §2]

**The Borrowed-Ground Rule.** The neutrals are GitHub Primer's own values, used so the assets
sit native in the environment that renders them. Changing the ground means leaving that
environment. [design-taste-frontend §2.A; primer, "Shared structural neutrals"]

## Typography

**Display Font:** none. **Prose:** the system sans stack, `bench-prose`, no web font, no
`Inter` named. **Claims:** `ui-monospace` stack, `bench-figure` / `bench-command` /
`bench-verdict`. Every figure, token, command, identifier, verdict and evidence value is mono;
prose is sans.

Why this pairing and not another: every SME that named a face (Geist, Satoshi, Cabinet
Grotesk, PP Editorial New) named a web font, and the repository loads none and adds no
dependency, so those rulings are refused by fact. The same SMEs ban `Inter` as a default, so
the primer's `Inter, ...` stack is adopted with `Inter` dropped; the surviving stack is what
the SMEs' "dashboard constraint" allows: sans for prose, mono for numbers.
[stitch-design-taste §3 "Dashboard Constraint"; design-taste-frontend §4.1; fact: no new
dependency, no web font]

### The ramp (site)

Four sizes and three weights. Nothing off the ramp.

- **H1** `bench-h1`: 1.75rem, 700, line-height 1.2, `letter-spacing: -0.01em`.
- **H2** `bench-h2`: 1.25rem, 600, `border-bottom: 1px solid` Hairline. The underline is the
  only section separator.
- **H3**: 1rem, 600. Hierarchy by weight, not by a fifth size. [redesign-existing-projects,
  "introduce 500/600 for subtler hierarchy"]
- **Prose** `bench-prose`: 1rem, 400, line-height 1.55, `max-width: 65ch`.
  [redesign-existing-projects, "body text too wide"; primer 65-75ch]
- **Verdict**: 1.25rem, 700, mono. A verdict is a claim token, so it sits on the mono stack at
  the H2 step, not on its own step. [fact: Mono-Carries-The-Claim; the 1.15rem literal was one
  of the three off-ramp sizes the detector found real]
- **Figure / code / verdict-token** `bench-figure`: mono, 0.92em, `font-variant-numeric:
  tabular-nums`. [redesign-existing-projects, "numbers in proportional font"]
- **Footer**: 1rem, Muted. Colour carries the demotion, not size. [redesign-existing-projects,
  "hierarchy through weight and colour"; retires the 0.85rem literal]

### The ramp (assets)

Mono at every size. Social preview (#310): **Verdict** 52px/700; every other line 21px, weight carried by tone (Ink, Soft Ink, Muted, Deep Muted), not by size. Banners, until #309: **Command** 21-30px · **Readout** 19px Muted · **Label** 15-20px Deep Muted.

### Named Rules

**The Mono-Carries-The-Claim Rule.** If a reader could copy it into a terminal or cite it as a
number, it is mono. [fact; unchanged]

**The No-Display-Face Rule.** Scale and weight carry emphasis; a 52px mono verdict is this
system's headline. [design-taste-frontend §9.B "no oversized H1s; hierarchy by weight and
colour"]

**The Balanced-Heading Rule.** Headings set `text-wrap: balance`. [redesign-existing-projects,
"orphaned words"]

## Layout

**Site.** A single centred column, `max-width: 62rem`, on the declared spacing scale. The
header is a flex row, baseline-aligned, wrapping at narrow widths; the current page is marked
in the nav. Two primitives beyond the column: `dl` (the cost-beside-evidence grid) and
`.beside` (two related blocks side by side, stacking below roughly 40rem). Tables are
`width: 100%`, `border-collapse: collapse`, left- and top-aligned.
[redesign-existing-projects, "no indication of current page"; "no max-width container" already
met]

**Assets.** Fixed viewBox compositions, `780x176` for banners and `1280x640` for the social
preview with a 96px safe area. Composition: flat Primer-dark field, wordmark, one readout
line, one footer. No verdict legend, no decorative data, no window chrome.
[design-taste-frontend §9.F "fake terminal", "decorative status dots", "middle-dot rationed";
primer social-preview concept]

**Spacing.** The declared scale is 4 · 8 · 16 · 24 · 32 · 48 · 96 px. The stylesheet's sixteen
irregular rem values move onto it at #308. The primer supplied the scale; no SME fired
contradicted it and every SME demanded a consistent one.
[stitch-design-taste §6; redesign-existing-projects, "consistent padding"]

### Named Rules

**The One-Column Rule.** Evidence is read top to bottom in the order the generator emitted it.
No layout may reorder or parallelise it. [fact; unchanged]

## Elevation & Depth

**Flat, and the flatness is total.** No `box-shadow`, no gradient, no blur, no glow, no
opacity layering, no grain. Depth is exactly three devices:

1. **1px rules** in Hairline: table borders, `h2` underlines, the footer divider.
2. **A 2px bottom border** in Ink under the site header: the heaviest line on the page.
3. **4px left edges**: Ink for `.rule`, Can't-Tell Blue for `.refusal`.

On assets, the readout frame is a 2px Hairline stroke over Surface on a Void field. That is a
border, not a shadow.

### Named Rules

**The No-Shadow Rule.** A shadow implies a floating object, and nothing on an evidence surface
floats. [fact; primer "1px rules rather than shadows"; design-taste-frontend §4.4]

**The No-Texture Rule.** Two SMEs asked for grain or noise to "break digital flatness"
(redesign-existing-projects; high-end-visual-design). Both are refused: the primer bans
texture behind small text, code and measurements, and the whole surface is measurement.
[fact: measurements, tables and receipts stay on flat digital surfaces]

## Shapes

**Radius is zero everywhere.** One radius system for the whole repository.
[design-taste-frontend §4.4 shape-consistency lock; primer 0-4px]

The `rx="12"` / `rx="18"` on the terminal frames retires with the window chrome at #309 and
#310; the Square-Unless-Quoting exception dies with the thing it was quoting. The form language
is rectangles, 1px rules, 4px left edges and a 2px header underline.

## Components

### Refusal Block (the signature component)

- **Shape:** 4px left border in Can't-Tell Blue, no radius.
- **Padding:** `0.25rem 0 0.25rem 0.6rem`. **Weight:** 600.
- **Selectors:** `.refusal`, `.refused`.
- **Behaviour:** identical whether the refusal is a whole verdict or one missing figure;
  *"boxed so it cannot be mistaken for a missing value."* [fact]

### Rule Block

- 4px left border in Ink, no radius, padding `0.25rem 0 0.25rem 0.85rem`. Structurally the
  refusal block with a different edge; the pair is the whole callout vocabulary.

### Absent Marker

- `font-style: italic`, no border, no colour. An absence is quiet; a refusal is bordered and
  bold. Rendering them alike would claim the instrument had no answer when it declined to give
  one. [fact]

### Data Table

- 1px Hairline on every cell, `border-collapse: collapse`; head fill Void; caption
  left-aligned, 700; cells `0.35rem 0.5rem`, left, top; width 100%; figures tabular mono.

### Definition Grid

- CSS grid `minmax(10rem, max-content) 1fr`, gap on the scale; terms 700.

### Site Header

- Flex row, baseline, wrapping; 2px Ink border beneath; wordmark 700 with
  `letter-spacing: 0.02em`; nav links in Ink, underlined, current page marked; a visible focus
  ring in Can't-Tell Blue on every link. [redesign-existing-projects, "missing focus ring",
  "no indication of current page"]

### Readout Frame (assets)

- Surface fill, 2px Hairline stroke, radius 0. Inside: the wordmark in Deep Muted, one command
  line (`$` in Prompt Green, command in Ink, argument in Deep Muted), one readout line led by
  `→` in the semantic colour its state names, one footer in Muted. No title bar, no dots, no
  legend.

## Do's and Don'ts

### Do

- Give every refusal the 4px Can't-Tell Blue edge and weight 600.
- Keep `.absent` italic and unbordered.
- Set every figure, token, command and identifier in mono with tabular figures.
- Build separation from 1px rules, the 2px header border and 4px left edges.
- Keep the site one column at every width, and the page dark-locked.
- Keep Prompt Green to the `$` and confirmed success only.
- Mark the current page in the nav and give every link a visible focus ring.

### Don't

- Add a shadow, gradient, blur, glow, grain or opacity layer.
- Add `border-radius` anywhere.
- Dim, collapse, abbreviate or footnote a refusal.
- Use any chromatic colour outside the semantic three, on anything.
- Introduce a web font, a display face, or `Inter` by name.
- Render a number that no receipt supplies.
- Draw a window: no title bar, no traffic-light dots, no fake terminal.
- Use the prose form `Skill Harness` for a command, URL, package identifier or evidence label.

## What the harness must never do

Each rule is one sentence and names the skill that produced it. The four the spec required
come first; the rest are what the SMEs added. A live repository fact outranks every rule here.

1. Nothing sits behind a measurement: no texture, gradient, glow, blur or grain under a
   figure, a table, a readout or a receipt. [design-taste-frontend §4.4, §9.A; fact]
2. No colour reads as a verdict or a state outside the semantic three, and no decorative
   colour appears at all. [design-taste-frontend §4.2; stitch-design-taste §2]
3. No count, star, user number or live figure appears in a static graphic. [fact: owner ruling
   #253 §8; design-taste-frontend §4.9 "fake-precise numbers"]
4. A refusal is displayed as primary content at full weight, never dimmed, collapsed or
   footnoted. [fact, `style.css:1-7`; design-taste-frontend §4.5 "empty states composed"]
5. No page flips theme mid-scroll; the whole repository is one dark-locked theme.
   [design-taste-frontend §4.11]
6. No serif face and no generic system serif appears on any software surface.
   [stitch-design-taste §3]
7. No fake terminal, fake window chrome, or invented terminal output appears in any asset.
   [design-taste-frontend §9.F; primer "real terminal snippets are copied from committed
   output"]
8. No decorative status dot, no version stamp, no section-number eyebrow, no scroll cue.
   [design-taste-frontend §9.F]
9. No motion of any kind on any surface; a static instrument has nothing to animate.
   [design-taste-frontend §5 "motion must be motivated"; primer "no decorative motion"]
10. No middle-dot separator chain; at most one `·` per line. [design-taste-frontend §9.F]
11. No em-dash in new visible copy; existing SVG text nodes keep theirs until the owner selects
    a replacement line, because a visible-text change is a new public line and the aria-label
    is byte-pinned. [design-taste-frontend §9.G, bounded by fact]
12. No mixed grey families: every neutral is a Primer cool grey. [redesign-existing-projects;
    design-taste-frontend §4.2]
13. No radius anywhere, and no second radius system. [design-taste-frontend §4.4]
14. No card, panel, pill, badge or floating element builds hierarchy; rules and edges do.
    [design-taste-frontend §4.4; stitch-design-taste §5]
15. No emoji, sparkle, robot, brain, circuit, wand, neural mesh or AI-signifier icon.
    [stitch-design-taste §9; primer banned-graphics list]

## Known Divergences

Measured defects and open questions, recorded so a future pass does not rediscover them.

1. **The display name renders two ways, and this is a convention rather than a defect.**
   `skill-harness` is the identifier form (`pyproject.toml:6`, `README.md:8`, the SVGs, the
   repository name, the CLI). `Skill Harness` is the prose form (`CONTRIBUTING.md:1`,
   `CLAUDE.md:52`, `docs/case-studies/`, `sitegen/templates/page.html:11`). The shared brand
   document bans the rename only "inside commands, URLs, package identifiers, or evidence
   labels"; a page wordmark is none of the four. What is worth checking is the inverse leak,
   and none was observed.

2. **Resolved 2026-08-30.** The two systems are reconciled by declaration above: one system,
   paper retired. The tree still carries the paper stylesheet and the banners' window chrome until #308
   and #309 land (#310 removed the social preview's); the retiring tokens stay declared so the conformance check is green on
   `main` and turns red the day a retired literal is reintroduced after its ticket merges.

3. **The dark banner's verdict token draws from a different enum than the social preview's.**
   `banner-dark.svg:14` renders `→ UNMEASURED` (a clause status, `aggregation/status.py:52`);
   `social-preview.svg:18` renders `→ CUT` (a verdict, `aggregation/verdict.py:119`). Both are
   current. Which state the readout line shows is a copy decision for #309 and #310, and any
   new line is a labelled candidate the owner selects.

4. **The light/dark banner pair differs by one stroke attribute** (`#d0d7de` vs `#30363d`);
   both keep the dark interior, by the file's own comment. The naming does not carry the
   intent. With the window chrome retiring at #309, the pair reduces to one composition with
   two frame strokes; whether one file with a `currentColor` stroke replaces two is #309's
   call.

5. **`bench-cant-tell` is declared and unused.** `grep -ri 58a6ff` over the tree returns
   nothing on 2026-08-30. It becomes live when #308 moves the refusal edge onto it.

6. **Resolved in part at #310.** The social preview's window chrome (traffic-light dots, title
   divider, `rx="18"`) is gone and the composition sits on the 96px safe area with two declared
   sizes (`bench-command` 21px, `bench-verdict` 52px). The sample verdict for a skill that does
   not exist (`my-skill`, `→ CUT (subsumed)`) and the verdict legend line are still on the
   asset: removing them deletes text nodes and visible strings, and #310's acceptance criteria
   pin all nine text nodes live with the aria-label byte-identical. They leave in the PR where
   the owner selects a readout line and a footer line from the labelled candidates on #310.

## Provenance

Fired in this order on 2026-08-30 by the Direction seat, each with the S370 context pack and
the Brand Kit primer v0.1 as the brief. One line per skill: what it ruled.

- **`mattpocock-skills:writing-for-agents`** (fired first; DESIGN.md is a governed basename):
  governed the writing of this file; no design rule.
- **`design-taste-frontend`** (v2): ruled one design system per project, Primer for a
  GitHub-native devtool; one theme per page, locked; serif unjustified with no brand serif
  named; one accent, spent here on state; the terminal window, traffic-light dots, legend and
  middle-dot chains are named tells; em-dash banned in new copy. Its own §13 puts data tables
  out of its scope, so its rulings bind the chrome and assets directly and the receipt body by
  the theme lock only.
- **`stitch-design-taste`**: produced the candidate rule set (atmosphere, palette roles,
  typography, components, layout, anti-patterns); ruled Georgia banned and serif banned in
  software UI; mono for numbers at this density; no pure black. Its §8 motion philosophy
  (perpetual micro-loops, spring physics) was refused: the surfaces are static and the primer
  bans decorative motion.
- **`redesign-existing-projects`** (audit only): found the generic serif, the two-weight
  hierarchy, proportional numerals, no `text-wrap: balance`, no focus ring, no current-page
  marker, warm-and-cool grey mixing, and the light-in-dark sandwich; its "add grain or
  background imagery to flat sections" was refused by the no-texture fact.
- **`high-end-visual-design`**: fired for the craft floor and **produced no rule this file
  carries.** Every instruction it gives (premium web fonts with `Inter` and system faces
  banned, double-bezel nested cards at 2rem radius, backdrop blur, pill buttons, eyebrow
  badges, 800ms scroll reveals, "1px solid gray borders" banned) is refused by a live fact
  (no dependency, no web font, flat evidence field, hairlines are the separator) or by the
  primer's banned-graphics list. Recorded as a refusal, not a partial adoption.
- **`minimalist-ui`, `industrial-brutalist-ui`, `gpt-taste`, `impeccable`, image
  generation**: not fired. Neither b nor c named minimalism or brutalism as the world; the
  system named was Primer.

Conflicts and how each was settled (both positions kept):

- **Dark-only vs both modes.** design-taste-frontend §6.C requires both modes; the primer and
  the three SVGs are dark, and the same skill's §4.11 locks one theme per page. This file
  carries dark-locked, on the owner's primer as explicit instruction. Revisit-if above.
- **Motion.** stitch-design-taste §8 asks for perpetual micro-interactions; design-taste-frontend
  §5 requires every animation to be motivated. This file carries no motion: there is no
  interaction to motivate, and the primer bans decorative motion.
- **Texture.** redesign-existing-projects and high-end-visual-design ask for grain; the primer
  and the flat-evidence fact refuse it. This file carries no texture.
- **Fonts.** Every SME named a web font; the no-dependency fact refuses all of them. This file
  carries the system stacks.
