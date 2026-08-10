# Why this exists

The README says what the tool does. This page is the other question people ask: who built a
measurement instrument for AI skills, and on what authority?

Short answer: none, at the start.

## The question came first

I wanted to know if a skill was any good. There are several skills out there that all claim to
make AI writing sound less like AI writing — how do you tell them apart in a way that means
something? I figured other people had asked the same thing and that the answer existed
somewhere. I went looking for it. What I found was mostly with-and-without comparisons at
three runs a side, which I couldn't make myself trust once I saw how much the same task varies
against itself. So I kept going, and the looking turned into a build.

## I'm not an ML engineer

I don't pretend to be one, and the tool is shaped by that rather than in spite of it.

If you have the training, you can look at a result and know from experience whether it smells
right. I can't do that. Every claim had to carry something I could check, because the
alternative was trusting an intuition I hadn't yet had time to develop. That constraint is why
the harness refuses to emit a number the evidence doesn't support: I built the thing I needed
in order to not fool myself, and then found out the discipline was worth more than the score.

That is also why "the model already does this fine" kept coming back as the answer. I had no
prior investment in skills being valuable. I only wanted to know.

## How you build something you don't know how to build

The one part I'd claim was clever: I got reasonably good at asking *who actually knows what
they're talking about here, right now* — the same instinct any NCO relies on, where you don't
memorize the manual, you know where to find the answer and how to apply it.

That's the start of the loop, not the end of it. Four things made it work:

**Experts get verified too.** Knowing who knows doesn't get you out of checking. When I
started running strong reviewers against claims I could verify at source, roughly one in five
of their checkable objections turned out to be wrong. Not bad reviewers — that rate is normal,
and it's exactly why every answer that came back was treated as an input that still had to
survive verification rather than a conclusion. Inspect what you expect.

**Failure gets defined before you act.** Kill-criteria and revisit conditions written down in
advance, so a result can't be read backwards into whatever I was hoping for. Several of them
fired. One of them killed a whole line of work that had already been built.

**Every break becomes a rule that fires without anyone remembering it.** When something broke,
it produced a written lesson, and the lesson became a standing rule, a test, or an automated
guard. Ignorance was the starting condition, not a steady state — the loop converts it one
incident at a time. The record keeps the mistakes visible instead of tidying them away, which
is why this repo publishes its own null results and its own reversals.

**Every concept had to survive plain language before I'd decide on it.** I deliberately had
things explained to me the way you'd brief a senior stakeholder — plain terms, no performed
jargon — so I could sit with the actual concept and make an informed call. This wasn't a
concession. A decision wrapped in vocabulary you can't unpack is a decision you aren't really
making; stripping the jargon out is what kept the calls mine.

Compressed: know who knows, check them anyway, decide in advance what failure looks like, turn
every break into a standing rule, and then build the same honesty into the tool.

## The instrument is that loop turned inward

`CAN'T-TELL-YET`, and `UNMEASURED` with a typed reason attached, are "I don't actually know"
applied to the tool's own output with the same seriousness I had to apply it to myself. It
would have been easy to ship something that always returns a score. It would also have been
useless to me, which is the only user I was sure of.

It felt, going through it, like brute force, ignorance, curiosity, and an unreasonable number
of questions. Looking at what it actually was: a verification loop with an append-only memory,
run for long enough.

Part of the point was finding out whether I could do it. That question got answered too.

— Matthew Gruber
