# The rebuilt gitpull cost basis cannot be registered at the design's own n

**Date:** 2026-09-05. **Ticket:** `#420`. **Prior record:** `RAT-0001`, Amendment 2 (`#418`).

## Finding first

`#420` asks for a rebuilt cost basis for the `gitpull` task family, from either the measured run
or a cache-aware projection. **Neither branch closes.**

The measured branch produces a worst case above the registered ceiling, so the drift check would
refuse the record. The cache-aware branch has no projector to compute it with, and the house rule
that would let one compute it by hand is the rule that exists to prevent exactly that.

This is a halt, not a delay. The remaining move is a pre-registration design decision, and that is
not this session's to take.

## 1. The measured branch, computed through the live path

Computed with `project_pair_usd` from
`src/skill_harness/oracles/calibration/cost_projection.py:298`, at the `claude-sonnet-5` rates in
`src/skill_harness/ablation/subject.py:205` (input $2.00, output $10.00 per MTok).

**Control first.** The registered inputs reproduce the registered figure exactly:

```
project_pair_usd("claude-sonnet-5", input=353_721, output=2_230) = $0.72974200
```

`RAT-0001` §6 states `$0.729742` per pair. The method agrees with the record it is replacing, so
the disagreement below is in the tokens, not in the arithmetic.

**The rebuild:**

```
project_pair_usd("claude-sonnet-5", input=539_011, output=2_963) = $1.10765200
```

| n | Worst case | Cap, rounded up to the cent | Against the $35.00 ceiling |
|---|---|---|---|
| **32** (registered) | **$35.444864** | **$35.45** | **breach, by $0.45** |
| 31 | $34.337212 | $34.34 | within |
| 30 | $33.229560 | $33.23 | within |

`RAT-0001` registers `n: 32`. So the rebuilt basis at the registered design breaches the ceiling.

## 2. Why that is a refusal and not a rounding argument

`scripts/drift_check.py` row DC-12 (`_check_rat_ledger`, `:688-721`) reads every
`docs/ratifications/RAT-*.md` front-matter block and fails on:

- `hard_cap_usd > 35.0` — *"exceeds the $35.00 ceiling"*
- `hard_cap_usd < worst_case_cost_usd` — *"below the record's own worst-case cost"*

A valid cap must sit in `[worst_case, 35.00]`. At n = 32 the measured worst case is $35.444864, so
**that interval is empty**. There is no number that satisfies both conditions. The record cannot
be written in a form the gate accepts, and `#420`'s own acceptance criterion is that the drift
check passes on the commit that registers it.

Note what DC-12 does *not* do: it never re-derives `worst_case_cost_usd` from `PRICE_PER_MTOK`,
and it never checks the prose against the front-matter. A record could be made green by writing a
smaller number into the front-matter. That is available and it is fraud, so it is not an option;
it is recorded here because the gate's blindness to it is a real property of the gate.

## 3. Why the cache-aware branch has no path either

`#420` offers a second route: *"a projection that prices cache writes and cache reads explicitly
with a declared cache-read share and a declared floor for the no-discount case."*

Three facts close it:

1. **`project_pair_usd` has no cache term, deliberately.** Its docstring says
   *"no cache discount - worst case"*, and `_project_tokens_usd` (`:269-295`) reads only
   `rates["input"]` and `rates["output"]`. The pricing snapshot *does* carry `cache_read` and
   `cache_write` on all eight model keys — the gap is in the projector, not the prices.
2. **The one cache-aware projector models a different thing.** `project_calibration_cost`
   (`cost_projection.py:135`) prices a stable judge system-prompt prefix against per-call unique
   tails. That is the shape of a calibration sweep, not of a Gate-2 evaluation pair. Applying it
   to pairs would report a number about a structure the run does not have.
3. **Hand arithmetic is banned, by name.** `RAT-0001` §6 requires `cost_provenance` to name a live
   `cost_projection` function, and drift row DC-9 bans a snapshot constant by token — *"never hand
   arithmetic, never a snapshot constant."*

So a cache-aware basis needs a **new projector** for pair cost. That is an instrument build, and
it needs a declared cache-read share. The only observation available is 98.6% from a single run,
which is one measurement of one task family under one prompt.

## 4. What this says about the original projection

Worth stating plainly, because it is the reusable lesson rather than a fact about this ticket.

The registered projection was **conservative in dollars and wrong in tokens at the same time.** It
carried no cache term, which made it over-price by roughly seven times ($23.36 cap against $4.93
realised). It was built from an 8-pair pilot, which made it under-count the transcript growth of a
32-pair run by a factor of 1.524.

The two errors pointed in opposite directions, and the dollar error was the larger one. **That is
why the cap held, and the cap holding is not evidence that the basis was sound.** A no-cache
projection is a safe *budget* and an unsafe *token model*, and a later row-pick that inherits it
inherits the unsafe half.

## 5. The fork, stated and not taken

Three ways forward. Each changes something registered, so none is a mechanical rebuild.

| Path | What it costs | Whose call |
|---|---|---|
| **Reduce n to 31** | Registerable at $34.34. Reduces power over the registered H1 region, and `n` is a registered field. | Pre-registration design — reserved tier |
| **Raise the $35 ceiling** | Registerable at n = 32. Moves a spend ceiling the drift check enforces across every record. | Money and policy — the operator's |
| **Build a cache-aware pair projector** | Registerable at a lower, honest figure. A new instrument, needing a declared cache-read share and a no-discount floor beside it. | Instrument design, then a new row-pick |

**None is taken here.** `#420` is labelled `ready-for-agent` and its body scopes itself as
mechanical — *"no re-run, no change to RAT-0001, no change to `PRICE_PER_MTOK`"* — but the
arithmetic shows the mechanical version does not exist. The ticket is mis-scoped, not blocked by
missing work.

The n = 31 option is the one to resist deciding quickly. It is arithmetically tidy and it silently
buys registerability with statistical power, which is the trade a pre-registration exists to stop
anyone making after seeing the data.

*Revisit if:* `PRICE_PER_MTOK` changes, which moves every figure above; or the `gitpull` prompt or
fixture changes, which makes 539,011 a measurement of a different task; or a cache-aware pair
projector lands, which opens the third path and makes this finding's arithmetic the floor rather
than the answer.
