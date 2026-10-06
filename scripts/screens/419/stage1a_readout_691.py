"""#691: Stage 1A readout screen - Placebo inertness, adherence, within-pair correlation.

Reads the S486 Stage 1A run from the operator's disk and prints three sections. No model
call, no spend.

Inputs. Two, both required:

- ``RUN``: the Stage 1A run directory (holding ``run.log`` and ``run/look-001`` ...), its
  ``run.log``, or the log directory holding the ``look-*`` directories itself. Per-epoch
  outcomes and the ``manifest_read`` flags come from the ``.eval`` logs under ``look-*``,
  read with the existing Stage 1A readers in ``v5_cue_stage1a`` (``_read_rows_by_launch``,
  ``_manifest_reads``). The JSON block at the tail of ``run.log`` carries no per-epoch rows;
  when present it is read only for cross-checks (counts, ``pairs``, ``void_epochs`` and the
  run's recorded bounds), and any disagreement is a refusal.
- ``--null-readout``: the S475 readout whose Null-A epochs Stage 1A reused (looks 1 to 7
  hold no Null-A log), read with ``v5_cue_stage1a.load_null_a``. The Null-A stream is the
  reused outcomes followed by the new ones in launch order, the order the run records
  ("Null-A reused epochs then new epochs in launch order"). Omitting it is a usage error.

Every stream is built in launch order (the look number), and void epochs are excluded from
every count, stream and pair.

Section 1 - Placebo inertness. A two-sided anytime-valid interval on ``mu_P - mu_N``: the
engine's ``one_sided_betting_bound`` on each arm, combined by a union bound,
LB = LB(mu_P) - UB(mu_N) and UB = UB(mu_P) - LB(mu_N). The ticket's wording ("two-sided at
alpha 0.05, union bound, 0.025 each") supports two readings, and the bar owner has not chosen
between them, so both are printed and labelled:

- 0.025 per one-sided bound: each endpoint holds at 0.05; the interval holds at 0.10 by the
  union bound over its two endpoints.
- 0.0125 per one-sided bound: 0.05 in total over the four bounds.

Each reading carries its own exclusion statement against +/-0.20. A direct two-sided fixed-n
interval (unpaired Newcombe square-and-add Wilson, 95%) is printed as a comparison.

"n to exclude +/-0.20" is a property of a convention, not of the data: it depends on how the
same rates are spread over a longer stream. Two conventions are printed, each named, under each
alpha reading: the same rates at evenly-spaced launch indices, and the real launch order
repeated (cycled) to length n. Neither is chosen.

Section 2 - Adherence, descriptive only. Three rates with counts: assignment to read,
assignment to outcome, and read to outcome (correct among read, correct among unread, per
arm). Manifest-read happens after assignment; splitting outcomes by it conditions on a
post-treatment variable. These are adherence descriptives, not a mechanism.

Section 3 - Within-pair correlation, descriptive. The 2x2 table and phi coefficient of Full
and Placebo correctness across launch indices valid in both arms, with a 95% Fisher-z
interval. #684's simulator draws the arms independently; a materially positive phi (interval
above zero) is named as an input #685 must model before any sizing is relied on.

Run: PYTHONPATH=src python scripts/screens/419/stage1a_readout_691.py RUN \
         --null-readout S475_READOUT.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from math import atanh, isclose, sqrt, tanh
from pathlib import Path
from statistics import NormalDist
from types import ModuleType
from typing import Any

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

ALPHA = 0.05
BOUNDARY = 0.20
N_SEARCH_CAP = 1000
ALPHA_READINGS: tuple[tuple[float, str], ...] = (
    (
        0.025,
        "0.025 per one-sided bound: each endpoint at 0.05, the interval at 0.10 by the union bound",
    ),
    (0.0125, "0.0125 per one-sided bound: 0.05 in total over the four bounds"),
)
CONVENTION_EVEN = "same rates at evenly-spaced launch indices"
CONVENTION_REPEAT = "real launch order repeated to length n"
POST_TREATMENT_SENTENCE = (
    "Manifest-read happens after assignment. "
    "Splitting outcomes by it conditions on a post-treatment variable. "
    "These are adherence descriptives, not a mechanism."
)
MATERIAL_POSITIVE_NOTE = (
    "materially positive: name it as an input #685 must model before any sizing is relied on."
)
NULL_ORDER = "Null-A reused epochs then new epochs in launch order"
_SCREEN_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Epoch:
    """One world-A epoch: arm, launch index, outcome, void flag, and manifest read (or None)."""

    arm: str
    launch: int
    correct: bool
    void: bool
    manifest_read: bool | None = None


# ---------------------------------------------------------------------------
# Reading the run with the existing Stage 1A readers
# ---------------------------------------------------------------------------


def _stage1a_module() -> ModuleType:
    """Load the ``v5_cue_stage1a`` screen module, whose readers this screen reuses."""
    loaded = sys.modules.get("v5_cue_stage1a")
    if isinstance(loaded, ModuleType):
        return loaded
    if str(_SCREEN_DIR) not in sys.path:
        sys.path.insert(0, str(_SCREEN_DIR))
    spec = importlib.util.spec_from_file_location(
        "v5_cue_stage1a", _SCREEN_DIR / "v5_cue_stage1a.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load v5_cue_stage1a from the screen directory")
    module = importlib.util.module_from_spec(spec)
    sys.modules["v5_cue_stage1a"] = module
    spec.loader.exec_module(module)
    return module


def resolve_run(path: Path) -> tuple[Path, Path | None]:
    """Return (log directory holding ``look-*``, ``run.log`` or None) for a run path."""
    run_dir = path.parent if path.is_file() else path
    run_log = run_dir / "run.log"
    for candidate in (run_dir / "run", run_dir):
        if candidate.is_dir() and any(p.is_dir() for p in candidate.glob("look-*")):
            return candidate, run_log if run_log.is_file() else None
    raise ValueError(f"{path}: no look-* directories under the run (expected run/look-001 ...)")


def read_epochs(log_dir: Path) -> list[Epoch]:
    """Read world-A epochs and manifest reads from the ``.eval`` logs under ``look-*``."""
    s1a = _stage1a_module()
    rows: list[Any] = s1a._read_rows_by_launch(log_dir)
    manifest: dict[tuple[str, int], bool] = s1a._manifest_reads(log_dir)
    return [
        Epoch(
            arm=str(row.arm),
            launch=int(row.epoch),
            correct=bool(row.final_world_correct),
            void=bool(row.void),
            manifest_read=manifest.get((str(row.arm), int(row.epoch))),
        )
        for row in rows
        if str(row.world) == "a"
    ]


def read_reused_null(path: Path) -> tuple[int, ...]:
    """The reused Null-A outcomes in epoch order, via ``v5_cue_stage1a.load_null_a``."""
    null_a = _stage1a_module().load_null_a(path)
    if null_a.outcomes is None:
        raise ValueError(f"{path}: reused Null-A readout carries no per-epoch rows")
    return tuple(int(o) for o in null_a.outcomes)


def recorded_summary(run_log: Path) -> dict[str, Any]:
    """Return the last JSON object in ``run.log`` (the run's own recorded summary)."""
    text = run_log.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    last: dict[str, Any] | None = None
    start = text.find("{")
    while start >= 0:
        try:
            parsed, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(parsed, dict):
            last = parsed
        start = text.find("{", end)
    if last is None:
        raise ValueError(f"{run_log}: no JSON object found in the log")
    return last


# ---------------------------------------------------------------------------
# Streams
# ---------------------------------------------------------------------------


def _valid(epochs: Sequence[Epoch], arm: str) -> list[Epoch]:
    """Non-void epochs of one arm, sorted by launch index; duplicates refuse."""
    selected = sorted((e for e in epochs if e.arm == arm and not e.void), key=lambda e: e.launch)
    launches = [e.launch for e in selected]
    if len(launches) != len(set(launches)):
        raise ValueError(f"duplicate {arm} launch index in the readout")
    return selected


def streams(epochs: Sequence[Epoch], reused_null: Sequence[int]) -> dict[str, list[float]]:
    """Launch-order 0/1 streams per arm; Null-A is the reused outcomes then the new ones."""
    out = {arm: [float(e.correct) for e in _valid(epochs, arm)] for arm in ("full", "placebo")}
    out["null"] = [float(o) for o in reused_null] + [
        float(e.correct) for e in _valid(epochs, "null")
    ]
    for arm, xs in out.items():
        if not xs:
            raise ValueError(f"readout has no valid {arm} epochs")
    return out


def _bits(xs: Sequence[float]) -> str:
    return "".join(str(int(x)) for x in xs)


# ---------------------------------------------------------------------------
# Section 1 - Placebo inertness
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4096)
def _av_interval_cached(
    placebo_xs: tuple[float, ...], null_xs: tuple[float, ...], alpha_arm: float
) -> tuple[float, float]:
    lb_p = one_sided_betting_bound(placebo_xs, alpha=alpha_arm, side="lower")
    ub_p = one_sided_betting_bound(placebo_xs, alpha=alpha_arm, side="upper")
    lb_n = one_sided_betting_bound(null_xs, alpha=alpha_arm, side="lower")
    ub_n = one_sided_betting_bound(null_xs, alpha=alpha_arm, side="upper")
    return lb_p - ub_n, ub_p - lb_n


def av_interval(
    placebo_xs: Sequence[float], null_xs: Sequence[float], *, alpha_arm: float
) -> tuple[float, float]:
    """Anytime-valid interval on mu_P - mu_N from four one-sided bounds at ``alpha_arm``."""
    return _av_interval_cached(tuple(placebo_xs), tuple(null_xs), alpha_arm)


def _excludes(lo: float, hi: float, boundary: float = BOUNDARY) -> bool:
    return hi < boundary and lo > -boundary


def _wilson(x: int, n: int, z: float) -> tuple[float, float]:
    center = (x + z * z / 2.0) / (n + z * z)
    half = z * sqrt(x * (n - x) / n + z * z / 4.0) / (n + z * z)
    return center - half, center + half


def newcombe_unpaired(
    k1: int, n1: int, k2: int, n2: int, *, level: float = 0.95
) -> tuple[float, float]:
    """Direct two-sided fixed-n interval on p1 - p2 (Newcombe square-and-add Wilson)."""
    if n1 <= 0 or n2 <= 0:
        raise ValueError(f"arm sample sizes must be positive; got n1={n1}, n2={n2}")
    if not 0 <= k1 <= n1 or not 0 <= k2 <= n2:
        raise ValueError(f"counts out of range: k1={k1}/n1={n1}, k2={k2}/n2={n2}")
    z = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = _wilson(k1, n1, z)
    l2, u2 = _wilson(k2, n2, z)
    delta = p1 - p2
    return (
        delta - sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2),
        delta + sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2),
    )


def evenly_spaced(n: int, k: int) -> list[float]:
    """Place ``k`` successes at evenly-spaced launch indices in ``n`` slots."""
    if k <= 0:
        return [0.0] * n
    if k >= n:
        return [1.0] * n
    xs = [0.0] * n
    for i in range(k):
        xs[min(n - 1, max(0, round((i + 0.5) * n / k)))] = 1.0
    placed = sum(xs)
    j = 0
    while placed < k and j < n:
        if xs[j] == 0.0:
            xs[j] = 1.0
            placed += 1
        j += 1
    return xs


def repeated(xs: Sequence[float], n: int) -> list[float]:
    """The real launch-order stream cycled to length ``n``."""
    return [xs[i % len(xs)] for i in range(n)]


def _first_excluding_n(excludes: Callable[[int], bool], start: int, cap: int) -> int | None:
    """Smallest n in [start, cap] with ``excludes(n)``, by a linear scan.

    Exclusion is not monotone in n: under the repeated-order convention the stream's phase
    at n moves the bounds, so a doubling-and-bisection search can land on a later crossing
    (535 rather than 488 on the S486 streams at 0.025). Only a scan returns the smallest n.
    """
    return next((n for n in range(start, cap + 1) if excludes(n)), None)


def n_to_exclude_even(
    placebo_xs: Sequence[float], null_xs: Sequence[float], *, alpha_arm: float
) -> int | None:
    """n at which each arm's observed rate, at evenly-spaced indices, excludes +/-0.20."""
    p_rate, n_rate = sum(placebo_xs) / len(placebo_xs), sum(null_xs) / len(null_xs)

    def excludes(n: int) -> bool:
        lo, hi = av_interval(
            evenly_spaced(n, round(p_rate * n)),
            evenly_spaced(n, round(n_rate * n)),
            alpha_arm=alpha_arm,
        )
        return _excludes(lo, hi)

    return _first_excluding_n(excludes, max(len(placebo_xs), len(null_xs)), N_SEARCH_CAP)


def n_to_exclude_repeated(
    placebo_xs: Sequence[float], null_xs: Sequence[float], *, alpha_arm: float
) -> int | None:
    """n at which each arm's real launch order, repeated to length n, excludes +/-0.20."""

    def excludes(n: int) -> bool:
        lo, hi = av_interval(repeated(placebo_xs, n), repeated(null_xs, n), alpha_arm=alpha_arm)
        return _excludes(lo, hi)

    return _first_excluding_n(excludes, max(len(placebo_xs), len(null_xs)), N_SEARCH_CAP)


def _reading(
    placebo_xs: Sequence[float], null_xs: Sequence[float], alpha_arm: float, label: str
) -> dict[str, Any]:
    lo, hi = av_interval(placebo_xs, null_xs, alpha_arm=alpha_arm)
    excl = _excludes(lo, hi)
    return {
        "alpha_arm": alpha_arm,
        "label": label,
        "lo": lo,
        "hi": hi,
        "excludes": excl,
        "n_even": None if excl else n_to_exclude_even(placebo_xs, null_xs, alpha_arm=alpha_arm),
        "n_repeat": None
        if excl
        else n_to_exclude_repeated(placebo_xs, null_xs, alpha_arm=alpha_arm),
    }


def placebo_inertness(placebo_xs: Sequence[float], null_xs: Sequence[float]) -> dict[str, Any]:
    """Both alpha readings of the anytime-valid interval, plus the fixed-n comparison."""
    if not placebo_xs or not null_xs:
        raise ValueError("placebo and null streams must both be non-empty")
    for label, xs in (("placebo", placebo_xs), ("null", null_xs)):
        for i, x in enumerate(xs):
            if x not in (0.0, 1.0):
                raise ValueError(f"{label}[{i}]={x!r} is not a raw 0/1 outcome")
    k_p, n_p, k_n, n_n = int(sum(placebo_xs)), len(placebo_xs), int(sum(null_xs)), len(null_xs)
    fixed_lo, fixed_hi = newcombe_unpaired(k_p, n_p, k_n, n_n, level=1.0 - ALPHA)
    return {
        "n_placebo": n_p,
        "correct_placebo": k_p,
        "n_null": n_n,
        "correct_null": k_n,
        "point": k_p / n_p - k_n / n_n,
        "readings": [_reading(placebo_xs, null_xs, a, lbl) for a, lbl in ALPHA_READINGS],
        "fixed_n_lo": fixed_lo,
        "fixed_n_hi": fixed_hi,
        "fixed_n_excludes": _excludes(fixed_lo, fixed_hi),
    }


# ---------------------------------------------------------------------------
# Section 2 - Adherence, descriptive only
# ---------------------------------------------------------------------------


def _rate(k: int, n: int) -> str:
    return f"{k}/{n} = {k / n:.3f}" if n else f"{k}/{n} = nan"


def adherence(epochs: Sequence[Epoch]) -> dict[str, Any]:
    """Three descriptive adherence rates from per-epoch read and outcome flags."""
    arms: dict[str, Any] = {}
    for arm in ("full", "placebo"):
        cells = _valid(epochs, arm)
        if any(e.manifest_read is None for e in cells):
            raise ValueError(f"{arm}: every valid epoch must carry a manifest_read flag")
        read = [e for e in cells if e.manifest_read]
        unread = [e for e in cells if not e.manifest_read]
        arms[arm] = {
            "assignment_to_read": _rate(len(read), len(cells)),
            "assignment_to_outcome": _rate(sum(e.correct for e in cells), len(cells)),
            "correct_among_read": _rate(sum(e.correct for e in read), len(read)),
            "correct_among_unread": _rate(sum(e.correct for e in unread), len(unread)),
        }
    return {**arms, "post_treatment_sentence": POST_TREATMENT_SENTENCE}


# ---------------------------------------------------------------------------
# Section 3 - Within-pair correlation
# ---------------------------------------------------------------------------


def phi_interval(a: int, b: int, c: int, d: int, *, level: float = 0.95) -> tuple[float, float]:
    """Interval on phi via the Fisher z-transform; NaN with a zero margin or n <= 3."""
    n = a + b + c + d
    denom = sqrt((a + b) * (c + d) * (a + c) * (b + d))
    if n <= 3 or denom == 0.0:
        return float("nan"), float("nan")
    phi = (a * d - b * c) / denom
    if abs(phi) >= 1.0:
        return phi, phi
    zcrit = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)
    se = 1.0 / sqrt(n - 3)
    return tanh(atanh(phi) - zcrit * se), tanh(atanh(phi) + zcrit * se)


def within_pair_correlation(epochs: Sequence[Epoch]) -> dict[str, Any]:
    """2x2 table and phi of Full x Placebo correctness over launch indices valid in both."""
    full = {e.launch: e.correct for e in _valid(epochs, "full")}
    placebo = {e.launch: e.correct for e in _valid(epochs, "placebo")}
    shared = sorted(full.keys() & placebo.keys())
    if not shared:
        raise ValueError("no launch index is valid in both Full and Placebo")
    a = sum(1 for k in shared if full[k] and placebo[k])
    b = sum(1 for k in shared if full[k] and not placebo[k])
    c = sum(1 for k in shared if not full[k] and placebo[k])
    d = sum(1 for k in shared if not full[k] and not placebo[k])
    denom = sqrt((a + b) * (c + d) * (a + c) * (b + d))
    phi = (a * d - b * c) / denom if denom else 0.0
    lo, hi = phi_interval(a, b, c, d, level=1.0 - ALPHA)
    return {
        "pairs": shared,
        "table": (a, b, c, d),
        "phi": phi,
        "phi_ci_lo": lo,
        "phi_ci_hi": hi,
        "materially_positive": bool(len(shared) >= 4 and denom > 0 and lo > 0.0),
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_report(epochs: Sequence[Epoch], reused_null: Sequence[int]) -> dict[str, Any]:
    """Compute all three sections from world-A epochs and the reused Null-A outcomes."""
    xs = streams(epochs, reused_null)
    return {
        "streams": xs,
        "manifest_read": {
            arm: sum(bool(e.manifest_read) for e in _valid(epochs, arm))
            for arm in ("full", "placebo")
        },
        "inertness": placebo_inertness(xs["placebo"], xs["null"]),
        "adherence": adherence(epochs),
        "correlation": within_pair_correlation(epochs),
        "void": sorted(f"{e.arm}#{e.launch}" for e in epochs if e.void),
    }


def _checks(report: dict[str, Any], recorded: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    xs, arms = report["streams"], recorded["arms"]
    each_at = float(recorded["f_minus_n"]["each_at"])
    reads = report["manifest_read"]
    return [
        ("full correct", arms["full"]["correct"], int(sum(xs["full"]))),
        ("placebo correct", arms["placebo"]["correct"], int(sum(xs["placebo"]))),
        ("full manifest_read", arms["full"]["manifest_read"], reads["full"]),
        ("placebo manifest_read", arms["placebo"]["manifest_read"], reads["placebo"]),
        ("null-a n", recorded["null_a"]["n"], len(xs["null"])),
        ("null-a correct", recorded["null_a"]["correct"], int(sum(xs["null"]))),
        ("null-a order", recorded["null_a"]["order"], NULL_ORDER),
        ("pairs", recorded["pairs"], report["correlation"]["pairs"]),
        ("void_epochs", len(recorded["void_epochs"]), len(report["void"])),
        (
            "f_minus_n.lb_mu_f",
            recorded["f_minus_n"]["lb_mu_f"],
            one_sided_betting_bound(xs["full"], alpha=each_at, side="lower"),
        ),
        (
            "f_minus_n.ub_mu_n",
            recorded["f_minus_n"]["ub_mu_n"],
            one_sided_betting_bound(xs["null"], alpha=each_at, side="upper"),
        ),
    ]


def cross_check(report: dict[str, Any], recorded: dict[str, Any]) -> list[str]:
    """Compare the report with the run's recorded summary; raise on any disagreement."""
    lines = []
    for name, want, got in _checks(report, recorded):
        same = isclose(want, got, abs_tol=1e-12) if isinstance(want, float) else want == got
        if not same:
            raise ValueError(f"cross-check failed: {name}: run.log has {want!r}, logs give {got!r}")
        shown = f"{len(want)} keys" if isinstance(want, list) else repr(want)
        lines.append(f"cross_check {name}: run.log={shown}, logs agree")
    return lines


def _render_inertness(iner: dict[str, Any]) -> list[str]:
    lines = [
        "=== Placebo inertness (Placebo - Null-A) ===",
        f"n_placebo={iner['n_placebo']} correct_placebo={iner['correct_placebo']}",
        f"n_null={iner['n_null']} correct_null={iner['correct_null']}",
        f"point_estimate={iner['point']:.4f}",
    ]
    for r in iner["readings"]:
        verdict = "excludes" if r["excludes"] else "does not exclude"
        lines.append(f"[alpha reading: {r['label']}]")
        lines.append(f"  anytime_valid_interval=[{r['lo']:.4f}, {r['hi']:.4f}]")
        lines.append(f"  the interval {verdict} +/-{BOUNDARY:.2f}")
        if r["excludes"]:
            continue
        lines.append("  placebo inertness is not established at this n under this reading")
        for key, convention in (("n_even", CONVENTION_EVEN), ("n_repeat", CONVENTION_REPEAT)):
            value = r[key] if r[key] is not None else f"not reached by {N_SEARCH_CAP}"
            lines.append(f"  n_to_exclude_pm_{BOUNDARY:.2f}={value} (convention: {convention})")
    lines.append(
        "n_to_exclude is a property of the convention, not of the data; no convention is chosen"
    )
    lines.append(
        f"fixed_n_newcombe_interval=[{iner['fixed_n_lo']:.4f}, {iner['fixed_n_hi']:.4f}]"
        " (direct two-sided fixed-n comparison, unpaired, 95%)"
    )
    excl = str(iner["fixed_n_excludes"]).lower()
    lines.append(f"fixed_n_excludes_plus_minus_{BOUNDARY:.2f}={excl}")
    return lines


def _render_adherence(adh: dict[str, Any]) -> list[str]:
    lines = ["=== Adherence (descriptive only) ===", "assignment_to_read:"]
    lines += [f"  {arm}: {adh[arm]['assignment_to_read']}" for arm in ("full", "placebo")]
    lines.append("assignment_to_outcome:")
    lines += [f"  {arm}: {adh[arm]['assignment_to_outcome']}" for arm in ("full", "placebo")]
    lines.append("read_to_outcome:")
    for arm in ("full", "placebo"):
        lines.append(f"  {arm}_correct_among_read: {adh[arm]['correct_among_read']}")
        lines.append(f"  {arm}_correct_among_unread: {adh[arm]['correct_among_unread']}")
    lines.append(adh["post_treatment_sentence"])
    return lines


def _render_correlation(corr: dict[str, Any]) -> list[str]:
    a, b, c, d = corr["table"]
    lines = [
        "=== Within-pair correlation (Full x Placebo, descriptive) ===",
        f"n_pairs={len(corr['pairs'])} (paired by launch index; void epochs excluded)",
        f"table: both_correct={a} full_only={b} placebo_only={c} neither={d}",
        f"phi={corr['phi']:.4f}",
        f"phi_95_ci=[{corr['phi_ci_lo']:.4f}, {corr['phi_ci_hi']:.4f}] (Fisher z)",
        f"materially_positive={str(corr['materially_positive']).lower()}",
    ]
    if corr["materially_positive"]:
        lines.append(MATERIAL_POSITIVE_NOTE)
    else:
        lines.append(
            "the interval includes zero; #684's independence assumption is not contradicted"
            " at this n"
        )
    return lines


def render(report: dict[str, Any]) -> str:
    """Render the streams and the three sections as plain text."""
    xs = report["streams"]
    lines = ["=== Launch-order streams (epoch 1 to n; 1 = world correct) ==="]
    for tag, arm in (("P", "placebo"), ("N", "null"), ("F", "full")):
        lines.append(f"{tag} {_bits(xs[arm])}")
    lines.append(f"null_order: {NULL_ORDER}")
    lines.append(f"void_epochs: {', '.join(report['void']) or 'none'}")
    lines.append("")
    lines += _render_inertness(report["inertness"])
    lines.append("")
    lines += _render_adherence(report["adherence"])
    lines.append("")
    lines += _render_correlation(report["correlation"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("run", type=Path, help="Stage 1A run directory, its run.log, or log dir")
    parser.add_argument(
        "--null-readout",
        type=Path,
        required=True,
        help="the S475 readout.json whose Null-A epochs Stage 1A reused (required)",
    )
    args = parser.parse_args(argv)
    log_dir, run_log = resolve_run(args.run)
    report = build_report(read_epochs(log_dir), read_reused_null(args.null_readout))
    print(render(report))
    print("")
    if run_log is None:
        print("cross_check: skipped (no run.log beside the logs)")
    else:
        print("\n".join(cross_check(report, recorded_summary(run_log))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
