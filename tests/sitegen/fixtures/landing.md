# skill exists ≠ skill was delivered ≠ model used skill

lead: A measurement instrument for controlled skill-vs-no-skill comparisons.
claim: CANT_TELL_YET
action: Read the published receipts -> receipts

## What it refuses to claim

- **No lift figure from an unpaired run**: a comparison needs both arms, so a run with one arm reports the arm it has and no difference between them.
- **No cost figure the run did not meter**: each leg of the cost triple carries a token count or a typed refusal naming why the count is missing.
- **No verdict the evidence does not support**: the verdict vocabulary is KEEP, CUT and CANT_TELL_YET, and the third one is a result.
- **No number in place of a missing number**: a field with nothing behind it says so, and the build stops rather than render a plausible figure.
- **No deploy called successful because the job went green**: the workflow fetches the published address and looks for this build's own marker.

## What it measures, in the instrument's own terms

A skill exists when the file is present. It was delivered when the runtime put its description into the model's context, which this instrument calls exposure and treats as the treatment condition. The model used it when it loaded the body, which is invocation, a downstream behavior the instrument records rather than the treatment.

The comparison is paired: the same task runs with the skill and without it, epoch by epoch, so the difference between the arms is the thing being measured rather than the difference between two populations.

Cost is reported as a triple, standing against fired against auxiliary tokens, because a skill that helps and a skill that helps for the price of every prompt are different answers to the same question.

## Install

command: pip install skill-harness
command: skill audit --help

Install the package with pip. Then run the audit command to see the options.

## Where the verdicts land

- Published receipts -> receipts
- The reporting standard every receipt validates against -> reporting-standard
- The skill collection these verdicts are recorded in -> https://github.com/MrBinnacle/skills
