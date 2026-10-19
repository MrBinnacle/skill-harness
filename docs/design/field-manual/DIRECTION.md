# Direction contract — The Field Manual

Locked by the owner, 2026-09-15. Seed key `9d090308`, re-roll round 1, assigned index 3.

This is the contract `impeccable`'s new-work flow requires before code. The finish review
audits the built site against it. `reference-hero.html` in this directory is the approved
reference, and `reference-hero-1440.png` is what it renders to at 1440x900.

---

**THESIS.** A skill is a specimen and this site is the manual that identifies it. It refuses
the dark benchmark dashboard this category always ships, and refuses its opposite, the white
page with one big number. The reason this world carries the product rather than decorating
it: taxonomy already has a dignified vocabulary for cannot determine from this specimen. A
field guide writes indeterminate and no reader hears failure. That is `CANT_TELL_YET` with
cultural precedent instead of an argument the page has to win every time.

**OWN-WORLD.** Green-black ground `#171A15` over void `#0E100D`, with a fine matte tooth of
flocked grain and a beam sweep. Olive drab `#6E7356` carries whole fields and means one thing
only: a try that caught the fact. Bone `#D8D2C0` is the ink and the primary action. Brass
`#C9A227` is spent on section marks and callouts, never on a verdict. Every corner is 90
degrees. Hairlines are 1px grid gaps over a `#3A3F33` parent, never borders. Macro type is
Archivo Black, uppercase, `clamp(3.4rem, 11.5vw, 11.5rem)` at `-0.045em` and `0.86` leading.
Telemetry is JetBrains Mono, 11px, uppercase, `0.09em`, and it labels; it never sets a
paragraph.

**STORY.** A person who writes skills arrives unsure whether to ship the one they just wrote.
They learn the method in one sentence, see what the instrument refuses in the next,
then watch one real specimen measured in front of them. They leave and run it on their own
skill.

**FIRST VIEWPORT.** A telemetry stamp row, then the question at display scale across two
lines with `help?` in olive. Beneath it a two-column band: the method on the left, what the
instrument refuses on the right, divided by a hairline. The primary action sits at the foot
of the page in bone, the brightest element on the surface.

**FORM.** The Field Manual, position 3 of 7 on the grounded list, assigned by seed
`9d090308` at re-roll 1. The palette and materials are owner-pinned and outrank the roll.

**FINISH.** unreviewed and undocumented is unfinished; this build ends with the finish review,
the verdict, DESIGN.md, and every shipping raster carrying its provenance

---

## What the reference already fixed, with numbers

A design-check seat measured the first cut and four findings were real:

| Defect | Before | After |
|---|---|---|
| Try cells, hit against miss | 2.04:1 | **3.87:1**, miss moved to void |
| Primary action text | 3.87:1, fails AA at 14px | **11.63:1**, bone fill |
| `CANT_TELL_YET` marker | brass, the page's warning hue | **bone**, the page's brightest ink |
| Vocabulary | epochs, arms, planted-fact | tries, sets, spot the false fact, each defined before use |

The verdict marker matters most and it is the one a later pass is most likely to undo. The
box geometry was already identical for every verdict. The marker colour was not, and brass
marks warnings elsewhere on this page, so a brass square filed the refusal under caution while
the geometry claimed equality. `PRODUCT.md` principle 2 is the rule that binds it. A refusal
takes bone. `KEEP` takes olive. `CUT` takes bone-dim.

## What is NOT done

The reference is a prototype and it sits outside the fence on purpose.

`tests/test_design_tokens_conformance.py` rejects any colour, font-family or font-size literal
in `style.css` or `assets/*.svg` that `DESIGN.md` does not declare. None of this world is
declared yet. So the port order is fixed and it is the opposite of what a first instinct
suggests: build the world, then let the documenter write `DESIGN.md` from what was built, per
`new-work.md`. The conformance suite runs red on the branch in between, and green before the
pull request.

Still to do: the seven remaining pages, the four fenced SVG assets, `.impeccable/design.json`
re-derived against the new `DESIGN.md`, and the tests that assert the retired world.
