# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A person who writes or maintains agent skills and has to decide whether to ship one.

They arrive with a specific skill in mind. They want to know whether it helps, and they
want to be able to check the answer themselves rather than take it on trust.

No other audience is confirmed. Do not add one without asking.

## Product Purpose

Skill Harness measures whether a skill helps.

It runs the same task twice. Once with the skill, once without it. Then it compares the
two runs.

The site exists to get people to run it on their own skills. That is what success means
here. A reader who finishes the page and installs the package is the outcome. A reader
who finishes the page and is merely impressed is not.

## Positioning

The instrument refuses to invent a number.

When the difference between the two runs is too small to call, or the sample is too thin,
it says so. It returns a typed refusal instead of a score. A number filled in by a tool
that does not know the answer is worse than no number, because the reader cannot tell the
two apart.

That refusal is the thing a neighbouring product cannot truthfully copy without building
the same discipline underneath it.

## Operating Context

A user installs the package and audits a skill file on their own machine. The result is a
receipt. Receipts are published to the site.

Every published receipt validates against a reporting standard before the page is written.
A receipt that does not validate stops the build, so nothing on the site was rendered from
an unvalidated receipt.

## Capabilities and Constraints

The verdict vocabulary is closed, and it is the product. A verdict is one of:

- `KEEP`
- `CUT`, with a sub-reason
- `CANT_TELL_YET`

`CANT_TELL_YET` is a result. It is not a failure and not an absence. The codebase states
this in its own words: "a refusal is a result here, not an absence". Any surface that
presents `CANT_TELL_YET` as a negative outcome, or dims it, collapses it, or pushes it into
a footnote, has broken the product.

A run marked as a declared synthetic control validates the instrument. It is not a claim
about any real skill.

No production skill has returned a `KEEP` verdict. That is a current fact about the
evidence, not a defect, and no surface may imply otherwise.

## Brand Commitments

Name: Skill Harness.

Voice, stated by the owner and binding: plain and simple. Easy to understand conceptually,
grammatically, and out loud. Not jargon.

A reader should not need to already hold the epistemics to follow a sentence on this site.
Where a term is unavoidable, the page defines it before the reader meets it. A term met
before it is defined is a defect.

## Evidence on Hand

Four published receipts in `docs/sers/receipts/`:

- one `KEEP`, which belongs to a declared synthetic control
- three `CANT_TELL_YET`, one of them qualified "unmeasured: underpowered"

Absences that future work must not fabricate:

- no production skill has a `KEEP` verdict
- there are no users, customers, testimonials, benchmarks, or adoption figures
- nothing here measures skills at large, only the skills in the receipts

The reporting standard is in `docs/sers/`. The declared synthetic control receipt is
`synthetic-control-keep-2026-07-27.json`.

## Product Principles

1. Get the reader to run it. Judge every surface on whether it moves a skill author toward
   auditing their own skill, not on whether it impresses them.

2. A refusal is a result. Show `CANT_TELL_YET` as plainly and as confidently as `KEEP`. The
   moment a refusal looks like a failure, users start avoiding it, and the honesty that
   makes the instrument worth using becomes the reason people stop.

3. Never claim more than the receipts show. A stranger who pulls on any line must find it
   holds. This outranks persuasion, because a claim that fails on inspection costs more
   trust than it ever bought.

4. Plain words beat correct jargon. If a sentence needs the reader to already understand
   the method, rewrite the sentence.

5. The reader can check everything. Every figure traces to a receipt, and the method runs
   on their machine.

## Accessibility & Inclusion

WCAG 2.2 AA.

Recorded as the practitioner default rather than as a requirement the owner stated, so
later work does not treat it as an open question. Text contrast clears 4.5:1, large text
clears 3:1, and interactive targets are at least 44px in their smallest dimension.
