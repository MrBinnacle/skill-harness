# Displaced enforcement: when a skill's real firing lives in a hook

> This harness measures a skill by ablating it: same task, skill present vs
> absent, honest comparison. That design has a blind spot worth naming out
> loud, because it changes how you read a null. For a discipline whose
> production reliability comes from a *hook* rather than from the model
> reading the skill, ablating the skill measures only the part that was never
> load-bearing. A flat result there is not evidence the discipline does
> nothing.

## What skill-ablation actually measures

The Full-vs-Null contrast (see
[`double-ceiling-structurally-unmeasured.md`](double-ceiling-structurally-unmeasured.md))
holds everything fixed except the skill's *text* — is the skill's content in
the model's context or not. That is exactly the right instrument for a
**background reference**: a skill whose entire mechanism is "the model reads
it and behaves better." If the text helps, the arms diverge; if it doesn't,
they don't, and UNMEASURED or a null is the honest answer.

But not every skill fires that way. Certain disciplines are actions an author
*requires* to happen, and the model reading a paragraph about them is the
unreliable path — the same retrieval-is-unreliable problem the skill was
written to defend against. For those, the author does not lean on the skill
text at all in production. They back it with a deterministic **hook**: a
`PreToolUse` block, a `PostToolUse` check, a `UserPromptSubmit` nudge that
surfaces the skill on a matching prompt. The skill text becomes the
human-readable *reference* for a discipline whose *enforcement* lives in the
hook layer.

## The blind spot

The harness ablates the skill. It does not ablate the hook — the hook is not
part of the subject-under-test, and in the pinned sandbox it is not even
present. So for a displaced-enforcement discipline:

- **Full arm** = model has the skill text. Whether it acts on it depends on
  retrieval, which is the unreliable channel by construction.
- **Null arm** = model lacks the skill text.
- **Neither arm** exercises the hook, which is where the discipline actually
  fires in production.

A flat or noisy contrast is then the *expected* result — and it says nothing
about the discipline's production value, because the load-bearing layer was
never in the experiment. Reading that null as "the discipline is worthless"
is the same category error the harness exists to prevent, wearing different
clothes: it reports on what it did not measure.

## The loop makes it total, not partial

The gap is widest under proactive / `/loop` execution, where there is no
human turn. Retrieval probability of the skill text goes to zero; a
`disable-model-invocation` procedure arrives as inert plain text; a
prompt-triggered nudge never fires. The *only* layer still firing is the
`PreToolUse`/`PostToolUse` hook — the one the skill-ablation never touches.
In that regime the skill text's contribution is not merely hard to measure,
it is structurally zero, while the discipline itself is fully active. Skill
presence and discipline enforcement have come completely apart.

## How to read the verdict, and how to actually measure it

Two consequences, both in the spirit of UNMEASURED-as-first-class:

1. **Classify before ablating.** A displaced-enforcement discipline gets a
   skill-ablation verdict about its *reference text*, not about the
   discipline. That distinction belongs in the record, so a null is not
   quietly upgraded into "no benefit." The honest label is scoped: "the
   skill text carries no measurable standalone effect" — which for a
   reference-of-a-hook-enforced discipline may be true *and* beside the
   point.
2. **To measure the discipline, ablate the enforcement layer, not the
   text.** The correct contrast is hook-present vs hook-absent on a task
   where the failure can actually occur (the failure the hook intercepts),
   ideally under the loop regime where the hook is the sole active layer.
   That is a different experiment than this harness's skill-ablation, and
   naming it is the point — measuring the text and reporting on the
   discipline are not the same claim.

## Where this shows up in the sibling collection

Two shipped skills in
[MrBinnacle/skills](https://github.com/MrBinnacle/skills) are exactly this
class, and their `EVIDENCE.md` records now say so under an **Enforcement
note**:

- `git-pull-rebase-trap` — the *preventive* half (check `pull.rebase` before
  the pull) rides on a `PreToolUse` block in the author's env; the published
  skill is the trap-explanation-and-recovery reference. A skill-ablation
  measures the reference, not the block.
- `downstream-instruction-framing` — the author treats it as mandatory and
  backs it with a `UserPromptSubmit` nudge plus a `PreToolUse` guard on
  handoff/plan writes; the skill text is the discipline reference. Its own
  EVIDENCE already flagged that "after-the-fact triggers can miss" — the
  hook is what closes that, on the tool call itself.

For both, a future Full-vs-Null skill run is a legitimate measurement of the
*text's* standalone effect, and must be published as such — not as the
discipline's verdict.

## Provenance

Methodological note, not a data run: no epochs were collected for this
entry. It records a scope boundary of the skill-ablation instrument, sibling
to the double-ceiling boundary — that result says *the task class* can make
the contrast uninformative; this one says *the skill class* (enforcement
displaced into a hook) can, too. The enforcement-layer framing traces to the
authoring rule in the sibling collection's `CLAUDE.md` ("a discipline you
require to fire cannot live only in the skill layer") and to the two
EVIDENCE records cited above. Written 2026-07-15.
