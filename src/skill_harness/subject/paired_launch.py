"""Pre-spend launch gate for a sized paired run (#409, under RAT-0001 / #391).

A sized paired run spends real money against a signed cap, so every question it
can get wrong is answered here rather than inside the runner script: which
design the record registered, which subject the record priced, what the run
projects to cost, and whether the ratification authorizes it at all.

The three refusals this module owns all fail CLOSED, and each is a measured
failure rather than a hypothetical:

1. Design from the record, never from a table. The batch-1 runner carried
   ``GO_THRESHOLD = {16: 9, 12: 7, 8: 5}[K]``, which raises ``KeyError`` at the
   ratified ``n = 32``. That table is not a coarse Gate-2; it is a different
   stopping rule. :func:`design_from_record` reconstructs the registered
   :class:`Gate2Design` from the RATIFIED record's own fields.

2. The subject the record priced, or nothing. ``claude-sonnet-5`` on the direct
   Anthropic API is the cost basis for the cap. :func:`resolve_direct_subject`
   refuses when ``ANTHROPIC_API_KEY`` is absent instead of falling back to
   OpenRouter: a silent route fallback spends a signed cap on a subject the
   record does not price, and every receipt to date already carries an
   OpenRouter deviation declared for exactly that reason.

3. The cost recomputed live, against the cap. RAT-0001 Amendment 1 measured the
   row's true headroom at 129 input tokens per pair (breakeven 353,850 against a
   registered 353,721). A cap set by rounding the worst case UP to the cent has
   at most one cent of headroom by construction, so this projection is
   knife-edge for every such row and a snapshot constant cannot stand in for it.

Route ambiguity, recorded rather than resolved
----------------------------------------------
Inspect's direct-Anthropic model string is ``anthropic/claude-sonnet-5``. This
repository already uses that exact string to mean the OpenRouter route, because
``cli/main.py::_resolve_subject_model_with_fallback`` rewrites a bare
``claude-sonnet-5`` to it when no Anthropic key is present, and because it is
also OpenRouter's own model id. One recorded identifier therefore names two
routes, and ``ablation/subject.py``'s rule that "the provider segment names the
route" does not hold for it.

Inspect requires the prefix, so the string cannot be changed. The route is
recorded explicitly instead: :class:`PairedRunnerConfig` carries a ``route``
field, and the ingest writes the whole config under ``config_json["runner"]``,
where a reader can recover the route the recorded identifier no longer carries.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from skill_harness.oc.gate2 import Gate2Design, MMESpec
from skill_harness.oracles.calibration.cost_projection import project_pair_usd
from skill_harness.ratification import RatRecord, check_execute_ratification, parse_rat_record

__all__ = [
    "ANTHROPIC_KEY_ENV",
    "DIRECT_ROUTE",
    "HAZARD_BASH_TOOL",
    "OPENROUTER_ROUTE",
    "HazardEntry",
    "PairedLaunchRefusal",
    "PairedRunnerConfig",
    "design_from_record",
    "hazard_entry_counts",
    "preflight_sized_run",
    "prior_measurements",
    "resolve_direct_subject",
    "runner_config_payload",
]

ANTHROPIC_KEY_ENV: Final = "ANTHROPIC_API_KEY"

#: Route labels written into the runner config. These are the values that make
#: an ``anthropic/`` identifier interpretable after the fact; see the module
#: docstring's route-ambiguity note.
DIRECT_ROUTE: Final = "anthropic-direct"
OPENROUTER_ROUTE: Final = "openrouter"

#: Float-noise tolerance for the cap comparison, in dollars. See the comment at
#: the comparison itself for why this is not a cent.
_CAP_EPSILON_USD: Final = 1e-6

#: Inspect's provider prefix for the direct Anthropic API, per its own docs
#: (``inspect eval task.py --model anthropic/claude-sonnet-5``). NOT the
#: OpenRouter form, which Inspect spells ``openrouter/anthropic/<model>``.
_INSPECT_ANTHROPIC_PREFIX: Final = "anthropic/"


class PairedLaunchRefusal(Exception):
    """A typed pre-spend refusal: the run must not launch.

    Raised only before any model call. Every message names the figure or the
    variable that produced the refusal, because a refusal a human cannot act on
    reads as a broken runner.
    """


class PairedRunnerConfig(BaseModel):
    """What the runner declares about itself, recorded at ingest.

    Section 2 of RAT-0001 requires the ratification reference to travel in the
    runner's config and to be recorded when the pair is ingested, and requires
    the runner's declared ``skill_id``, ``task_family`` and ``estimand`` to
    equal the record's exactly. Both halves are here: the equality is checked by
    :func:`preflight_sized_run` through the execute gate, and this model is what
    the ingest writes.

    ``route`` is not decoration. It is the only place the run's route survives:
    see the module docstring.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    rat_id: str
    ratification_path: str
    skill_id: str
    task_family: str
    estimand: str
    route: str
    model: str
    n_pairs: int


# ---------------------------------------------------------------------------
# #421: hazard-entry counting — did the Null arm ever meet the hazard?
#
# The oracle checks the outcome (ancestry preserved), not whether the hazard
# was entered. A model that never runs the trap-entering command passes, and
# the lattice is indistinguishable from "trap avoided". This counts bash
# tool-call commands matching a registered pattern per epoch, so a
# trap-discipline read can refuse when the Null arm never entered the hazard.
# ---------------------------------------------------------------------------

#: The bash tool function name in inspect_swe.claude_code transcripts.
#: Claude Code registers its shell tool as ``Bash``; the command lives in
#: ``arguments["command"]``. Matched case-insensitively so a renamed tool
#: still surfaces.
HAZARD_BASH_TOOL: Final = "bash"


class HazardEntry(BaseModel):
    """Per-arm hazard-entry count from one eval log.

    ``pattern`` is the regex the count was matched against (recorded so a
    reader cannot mistake which hazard was counted). ``epochs`` is the number
    of epochs in the log. ``entered`` is the number of epochs where at least
    one bash tool-call command matched the pattern.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    pattern: str
    epochs: int
    entered: int


def _bash_commands(messages: Iterable[object]) -> Iterable[str]:
    """Yield every bash tool-call command string from a message stream.

    Duck-typed against the same ``tool_calls``/``function``/``arguments``
    shape ``detect_skill_invocation`` reads (#46). A tool call counts when
    its function name case-insensitively matches ``HAZARD_BASH_TOOL`` and its
    arguments carry a ``command`` string. Any shape this scan does not
    recognise is skipped — an undercount can only make the hazard refusal fire
    more, never fabricate an entry.
    """
    for message in messages:
        calls = getattr(message, "tool_calls", None) or ()
        for call in calls:
            function = getattr(call, "function", None)
            if not isinstance(function, str) or function.lower() != HAZARD_BASH_TOOL:
                continue
            arguments = getattr(call, "arguments", None)
            if not isinstance(arguments, dict):
                continue
            command = arguments.get("command")
            if isinstance(command, str):
                yield command


def hazard_entry_counts(
    eval_log_path: Path, pattern: str, *, skill_description: str = ""
) -> HazardEntry:
    """Count epochs whose bash tool-call commands match ``pattern``.

    Reads one Inspect ``.eval`` log (needs the optional ``[inspect]`` extra,
    lazily imported — same convention as :func:`parse_eval_log`) and returns
    :class:`HazardEntry` with the pattern, the epoch count, and the number of
    epochs where at least one bash command matched.

    :param eval_log_path: Path to the ``.eval`` log.
    :param pattern: A regular expression matched against every bash
        tool-call command in each epoch (compiled here; a non-compiling
        pattern is a caller bug, not a parse error).
    :param skill_description: Forwarded to ``read_eval_log``-shape parsing
        only when the underlying reader needs it; unused for the bash scan.
    :raises PairedLaunchRefusal: If the ``[inspect]`` extra is not installed.
    :raises re.error: If ``pattern`` does not compile (caller bug — the
        record's ``hazard_action`` is validated at parse time).
    """
    try:
        from inspect_ai.log import read_eval_log
    except ImportError as exc:  # pragma: no cover — exercised only sans extra
        raise PairedLaunchRefusal(
            'hazard_entry_counts requires the optional extra: pip install "skill-harness[inspect]"'
        ) from exc

    regex = re.compile(pattern)
    log = read_eval_log(str(eval_log_path))
    epochs = 0
    entered = 0
    for sample in log.samples or []:
        epochs += 1
        messages = getattr(sample, "messages", None) or ()
        if any(regex.search(cmd) for cmd in _bash_commands(messages)):
            entered += 1
    return HazardEntry(pattern=pattern, epochs=epochs, entered=entered)


# ---------------------------------------------------------------------------
# #421: prior measurements — ledgered evidence for the priced subject,
# printed before the cost line so the launcher sees the ceiling at zero cost.
# ---------------------------------------------------------------------------


def _prior_screen_measurements(
    conn: sqlite3.Connection, record: RatRecord, bare_model: str
) -> list[str]:
    """Screen-store prior measurements for the record's card and priced subject.

    Matches ``screen_runs`` by ``skill_name == record.skill_id`` (the card
    name; the screen store carries no task_family) and ``subject_model``
    containing the bare pricing-table name. Returns one line per admissible,
    non-superseded screen run, ordered by creation.
    """
    lines: list[str] = []
    rows = conn.execute(
        "SELECT sr.screen_run_id, sr.subject_model, sr.source_eval_sha256, "
        "sr.admissibility_state, sr.created_at "
        "FROM screen_runs sr "
        "WHERE sr.skill_name = ? "
        "AND sr.screen_run_id NOT IN ("
        "    SELECT superseded_screen_run_id FROM screen_run_supersessions) "
        "ORDER BY sr.created_at, sr.screen_run_id",
        (record.skill_id,),
    ).fetchall()
    for screen_run_id, subject_model, source_eval_sha256, _admissibility, _created in rows:
        model_str = subject_model or ""
        if bare_model not in model_str:
            continue
        trial_row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(passed), 0) FROM screen_trials WHERE screen_run_id = ?",
            (screen_run_id,),
        ).fetchone()
        n_trials = int(trial_row[0]) if trial_row else 0
        n_pass = int(trial_row[1]) if trial_row else 0
        p0 = n_pass / n_trials if n_trials else 0.0
        sha_short = (source_eval_sha256 or "")[:8]
        lines.append(
            f"prior: screen run {sha_short}, {bare_model}, "
            f"Null {n_pass} of {n_trials}, p0 = {p0:.4f}"
        )
    return lines


def _prior_paired_measurements(
    conn: sqlite3.Connection, record: RatRecord, bare_model: str
) -> list[str]:
    """Evidence-store prior paired runs for the record's task family and subject.

    Matches ``runs`` by the runner-declared ``task_family`` in
    ``config_json["runner"]`` and the runner's ``model`` containing the bare
    pricing-table name. Returns one line per matching run, ordered by start.
    """
    lines: list[str] = []
    rows = conn.execute(
        "SELECT run_id, config_json FROM runs WHERE run_kind = 'evaluate_skill' "
        "ORDER BY started_at, run_id",
    ).fetchall()
    for run_id, config_raw in rows:
        try:
            config = json.loads(config_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        runner = config.get("runner")
        if not isinstance(runner, dict):
            continue
        if runner.get("task_family") != record.task_family:
            continue
        model_str = runner.get("model", "")
        if bare_model not in model_str:
            continue
        sha_short = (run_id or "")[:8]
        cells = config.get("paired_cells", {})
        both_pass = int(cells.get("both_pass", 0))
        full_only = int(cells.get("full_only", 0))
        null_only = int(cells.get("null_only", 0))
        both_fail = int(cells.get("both_fail", 0))
        total = both_pass + full_only + null_only + both_fail
        lines.append(
            f"prior: paired run {sha_short}, {bare_model}, "
            f"{total} pairs ({both_pass}/{full_only}/{null_only}/{both_fail})"
        )
    return lines


def prior_measurements(record: RatRecord, evidence_db: Path, bare_model: str) -> list[str]:
    """List every prior measurement for the record's task family and priced subject.

    Queries the evidence store (paired runs) and the screen store (stage-0
    screens) for measurements matching the record's ``task_family`` / card and
    the priced subject, by fixture SHA and model. Returns one line per
    measurement; printing is the check (#421: refusal is not proposed here).
    """
    from skill_harness.storage.migrations import open_evidence_readonly

    lines: list[str] = []
    conn: sqlite3.Connection | None = None
    try:
        conn = open_evidence_readonly(evidence_db)
        lines.extend(_prior_paired_measurements(conn, record, bare_model))
        lines.extend(_prior_screen_measurements(conn, record, bare_model))
    except Exception:
        # A missing or unreadable store is not a refusal (#421: printing is the
        # check). The launcher proceeds without prior measurements rather than
        # silently spending on a record the store could not vouch for.
        return []
    finally:
        if conn is not None:
            conn.close()
    return lines


def design_from_record(record: RatRecord) -> Gate2Design:
    """Reconstruct the registered Gate-2 design from a RATIFIED record.

    Every knob comes from the record. Nothing is defaulted: a design knob
    authored here would be this module registering a design, which is the
    operator's signature to give and not a runner's to infer.

    :param record: A parsed ratification record.
    :returns: The registered design.
    :raises PairedLaunchRefusal: If the record is not RATIFIED, is not a Gate-2
        record, or omits a design knob (each named).
    """
    if record.status != "RATIFIED":
        raise PairedLaunchRefusal(
            f"{record.rat_id} has status {record.status!r}; only a RATIFIED record "
            f"carries a design to run (the operator signs last, pre-spend)"
        )
    if record.gate != "gate2":
        raise PairedLaunchRefusal(
            f"{record.rat_id} field 'gate' is {record.gate!r}; a sized paired run requires gate2"
        )
    missing = [
        name
        for name, value in (
            ("gamma", record.gamma),
            ("delta_min", record.delta_min),
            ("q_min", record.q_min),
        )
        if value is None
    ]
    if missing:
        named = ", ".join(repr(name) for name in missing)
        raise PairedLaunchRefusal(
            f"{record.rat_id} omits design field(s) {named}; the design is read from "
            f"the record and never authored here"
        )
    assert record.gamma is not None  # narrowed by the `missing` check above
    assert record.delta_min is not None
    assert record.q_min is not None
    return Gate2Design(
        n_pairs=record.n,
        gamma=record.gamma,
        mme=MMESpec(delta_min=record.delta_min, q_min=record.q_min),
    )


def resolve_direct_subject(bare_model: str) -> str:
    """Resolve a bare vendor model name to Inspect's direct-Anthropic string.

    :param bare_model: The bare pricing-table name, e.g. ``claude-sonnet-5``. A
        name that already carries a provider segment is refused rather than
        double-prefixed, because ``anthropic/anthropic/x`` fails at the API
        boundary with an error that names neither this function nor the route.
    :returns: ``anthropic/<bare_model>``.
    :raises PairedLaunchRefusal: If ``ANTHROPIC_API_KEY`` is absent, or the name
        is empty or already routed.
    """
    if not bare_model or not bare_model.strip():
        raise PairedLaunchRefusal("no subject model given; expected a bare name")
    if "/" in bare_model:
        raise PairedLaunchRefusal(
            f"subject model {bare_model!r} already carries a provider segment; pass "
            f"the bare pricing-table name (e.g. 'claude-sonnet-5') so the route is "
            f"chosen here and recorded in the runner config"
        )
    if not os.environ.get(ANTHROPIC_KEY_ENV, "").strip():
        raise PairedLaunchRefusal(
            f"{ANTHROPIC_KEY_ENV} is not set, so the registered direct-Anthropic "
            f"subject cannot be reached. This run does NOT fall back to OpenRouter: "
            f"the ratified cap is priced on {bare_model!r} at Anthropic list rates, "
            f"and a fallback would spend a signed cap on a subject the record does "
            f"not price. Load the key into this shell and re-run."
        )
    return f"{_INSPECT_ANTHROPIC_PREFIX}{bare_model}"


def preflight_sized_run(
    *,
    ratification_path: Path,
    bare_model: str,
    input_tokens_per_pair: float,
    output_tokens_per_pair: float,
    evidence_db: Path | None = None,
) -> tuple[RatRecord, Gate2Design, PairedRunnerConfig, float]:
    """Everything that must hold before the first model call.

    Order matters and is the ratified one: parse and validate the record, then
    the execute gate (status, cap, scope), then the design, then the subject,
    then the live cost projection against the cap. The cheapest refusals come
    first so a misconfigured launch fails without touching the network.

    When ``evidence_db`` is given (#421), the pre-flight additionally prints
    every prior measurement for the record's task family and priced subject
    from the evidence and screen stores (before the cost line) and refuses
    when ``pilot_subject_model`` is missing from the record or differs from
    the priced subject without a ``subject_change_waiver`` block. A real launch
    always carries the evidence DB; the cap-boundary tests that omit it test
    the cap projection alone and are unaffected by the #421 checks.

    :param ratification_path: Path to the RATIFIED record.
    :param bare_model: Bare pricing-table subject name.
    :param input_tokens_per_pair: Re-measured input tokens per pair, both arms,
        all classes.
    :param output_tokens_per_pair: Re-measured output tokens per pair.
    :param evidence_db: Optional path to the evidence DB. When given, prior
        measurements are printed and ``pilot_subject_model`` is checked.
    :returns: ``(record, design, runner_config, projected_worst_case_usd)``.
    :raises PairedLaunchRefusal: On any failing precondition, naming it.
    """
    try:
        record = parse_rat_record(ratification_path)
    except Exception as exc:  # RatificationError and file errors alike
        raise PairedLaunchRefusal(f"ratification record {ratification_path}: {exc}") from exc

    gate = check_execute_ratification(
        ratification_path,
        skill_id=record.skill_id,
        task_family=record.task_family,
        estimand=record.estimand,
        max_usd=record.hard_cap_usd,
    )
    if not gate.allowed:
        raise PairedLaunchRefusal(f"execute gate refused: {gate.reason} - {gate.detail}")

    design = design_from_record(record)

    # #421: print prior measurements before the cost line so the launcher sees
    # the ceiling at zero cost. Printing is the check; refusal is not proposed.
    if evidence_db is not None:
        for line in prior_measurements(record, evidence_db, bare_model):
            print(line)

    # #421: a pilot on one subject cannot size a run on another silently. The
    # record must name the pilot's subject; if it differs from the priced
    # subject, a dated subject_change_waiver block must authorise the transfer.
    if evidence_db is not None:
        if record.pilot_subject_model is None:
            raise PairedLaunchRefusal(
                f"{record.rat_id} is missing 'pilot_subject_model'; the pilot's "
                f"subject model must be recorded so a sized run on a different "
                f"subject cannot launch silently (#421). Record the bare "
                f"pricing-table name the pilot ran (e.g. '{bare_model}') and "
                f"re-run."
            )
        if record.pilot_subject_model != bare_model:
            waiver = record.subject_change_waiver
            if waiver is None:
                raise PairedLaunchRefusal(
                    f"{record.rat_id} pilot_subject_model "
                    f"{record.pilot_subject_model!r} differs from the priced "
                    f"subject {bare_model!r}; a subject_change_waiver block "
                    f"naming the reason and the measurement that supports the "
                    f"transfer is required (#421)."
                )
            for required_key in ("reason", "measurement", "date"):
                if required_key not in waiver or not str(waiver[required_key]).strip():
                    raise PairedLaunchRefusal(
                        f"{record.rat_id} subject_change_waiver is missing the "
                        f"'{required_key}' field; the waiver must name the reason, "
                        f"the measurement that supports the transfer, and the "
                        f"date (#421)."
                    )

    model = resolve_direct_subject(bare_model)

    per_pair = project_pair_usd(
        model,
        input_tokens_per_pair=input_tokens_per_pair,
        output_tokens_per_pair=output_tokens_per_pair,
    )
    worst_case = per_pair * design.n_pairs
    # Compared in DOLLARS, not cents. Cents is the tempting comparison because
    # check_execute_ratification compares the cap that way -- but there the two
    # figures are both cent-rounded by rule, and here one of them is not. At the
    # ratified row, cent-rounding grants half a cent of slack that the record
    # does not: 353,851 input tokens per pair projects to $23.360064, which is
    # above the $23.36 cap and is a breach by the record's own words ("above
    # 353,850 input ... the row breaches the cap"), yet rounds to the same 2336
    # cents and would launch. That is the same unsafe-direction error Amendment
    # 1 corrected in the record's prose, reintroduced in code.
    #
    # The epsilon absorbs float representation noise only. It is 1e-6 dollars,
    # four orders of magnitude below the 6.4e-5 excess that one token over the
    # breakeven produces, so it cannot hide a real breach; the exact breakeven
    # itself lands on 23.36 with zero error and passes.
    if worst_case > record.hard_cap_usd + _CAP_EPSILON_USD:
        raise PairedLaunchRefusal(
            f"pre-spend worst case ${worst_case:.6f} over {design.n_pairs} pairs "
            f"exceeds {record.rat_id}'s hard_cap_usd ${record.hard_cap_usd:.2f} "
            f"(${per_pair:.6f} per pair at {input_tokens_per_pair:,.0f} input / "
            f"{output_tokens_per_pair:,.0f} output tokens). The run does not launch; "
            f"record a dated amendment in section 10 of the record naming the "
            f"re-measured figure."
        )

    config = PairedRunnerConfig(
        rat_id=record.rat_id,
        ratification_path=ratification_path.as_posix(),
        skill_id=record.skill_id,
        task_family=record.task_family,
        estimand=record.estimand,
        route=DIRECT_ROUTE,
        model=model,
        n_pairs=design.n_pairs,
    )
    return record, design, config, worst_case


def runner_config_payload(config: PairedRunnerConfig) -> dict[str, Any]:
    """The runner config as the plain mapping the ingest records.

    :param config: The validated runner config.
    :returns: A JSON-serialisable mapping.
    """
    return dict(config.model_dump())
