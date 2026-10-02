"""#691: Stage 1A readout screen — Placebo inertness, adherence, within-pair correlation.

Reads the S486 Stage 1A readout from a path argument and prints three sections.
No model call, no spend. The readout path may be a ``.json`` file, a ``run.log``
whose tail carries a JSON block, or a directory holding either. Per-epoch rows
with ``arm``, ``epoch``, ``void`` and ``final_world_correct`` are required;
``manifest_read`` is required on Full and Placebo rows.

Section 1 — Placebo inertness. A two-sided anytime-valid interval on
``mu_P - mu_N`` at alpha 0.05, from the raw 0/1 outcomes in launch order, using
the engine's ``one_sided_betting_bound`` on each arm at alpha 0.025 (union bound).
A direct two-sided fixed-n Newcombe interval on the same rates is printed as a
comparison. The screen states whether the anytime-valid interval excludes
+/-0.20 and, when it does not, the n at which the same rates would exclude it
under the evenly-spaced launch-order convention.

Section 2 — Adherence, descriptive only. Three rates: assignment to read,
assignment to outcome, and read to outcome (correct among read, correct among
unread, per arm). Manifest-read happens after assignment; splitting outcomes by
it conditions on a post-treatment variable. These are adherence descriptives,
not a mechanism.

Section 3 — Within-pair correlation, descriptive. The phi coefficient of Full
and Placebo correctness across launch indices, with a 95% interval (Fisher
z-transform). #684's simulator draws the arms independently and states that
pairing confers no matched-pairs advantage under independence. A materially
positive observed correlation is named as an input #685 must model before any
sizing is relied on.

Run: PYTHONPATH=src python scripts/screens/419/stage1a_readout_691.py READOUT_PATH
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from functools import lru_cache
from math import atanh, sqrt, tanh
from pathlib import Path
from statistics import NormalDist
from typing import Any

from skill_harness.aggregation.confidence_sequence import one_sided_betting_bound

ALPHA = 0.05
ALPHA_ARM = 0.025
BOUNDARY = 0.20
ORDER_CONVENTION = "evenly-spaced launch order"
N_SEARCH_CAP = 2000
POST_TREATMENT_SENTENCE = (
    "Manifest-read happens after assignment. "
    "Splitting outcomes by it conditions on a post-treatment variable. "
    "These are adherence descriptives, not a mechanism."
)
MATERIAL_POSITIVE_NOTE = (
    "materially positive: name it as an input #685 must model before any sizing is relied on."
)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


# ---------------------------------------------------------------------------
# Readout loading
# ---------------------------------------------------------------------------


def load_readout(path: Path) -> dict[str, Any]:
    """Load a Stage 1A readout from a .json file, a run.log, or a directory.

    A directory prefers ``readout.json`` then ``run.log``. A ``run.log`` yields
    the last JSON object found in the file (the block at its tail). The parsed
    object must carry per-epoch ``rows``; counts alone cannot support the
    launch-order interval, the read-to-outcome split, or the within-pair table.
    """
    if path.is_dir():
        readout_json = path / "readout.json"
        run_log = path / "run.log"
        if readout_json.is_file():
            path = readout_json
        elif run_log.is_file():
            path = run_log
        else:
            raise ValueError(f"{path}: directory holds neither readout.json nor run.log")
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
    else:
        data = _json_from_log_tail(text, source=str(path))
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError(
            f"{path}: readout carries no per-epoch rows; the screen needs "
            "arm/epoch/void/final_world_correct per launch index"
        )
    return data


def _json_from_log_tail(text: str, *, source: str) -> dict[str, Any]:
    """Return the last JSON object in ``text``; raise when none parses."""
    candidates = list(_JSON_BLOCK_RE.finditer(text))
    for match in reversed(candidates):
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"{source}: no JSON object found in the log tail")


def _cell_outcomes(rows: Sequence[dict[str, Any]], arm: str) -> list[tuple[int, int, bool | None]]:
    """Return (launch_index, correct, manifest_read) for valid epochs of ``arm``."""
    selected = [
        row
        for row in rows
        if str(row.get("arm", "")).lower() == arm and not bool(row.get("void", False))
    ]
    if not selected:
        raise ValueError(f"readout has no valid {arm} epochs")
    selected.sort(key=lambda row: int(row["epoch"]))
    epochs = [int(row["epoch"]) for row in selected]
    if len(epochs) != len(set(epochs)):
        raise ValueError(f"duplicate {arm} epoch in readout")
    out: list[tuple[int, int, bool | None]] = []
    for row in selected:
        correct = int(bool(row["final_world_correct"]))
        manifest = row.get("manifest_read")
        out.append((int(row["epoch"]), correct, None if manifest is None else bool(manifest)))
    return out


# ---------------------------------------------------------------------------
# Section 1 — Placebo inertness
# ---------------------------------------------------------------------------


@lru_cache(maxsize=256)
def _av_interval_cached(
    placebo_xs: tuple[float, ...],
    null_xs: tuple[float, ...],
    alpha_arm: float = ALPHA_ARM,
) -> tuple[float, float]:
    lb_p = one_sided_betting_bound(placebo_xs, alpha=alpha_arm, side="lower")
    ub_p = one_sided_betting_bound(placebo_xs, alpha=alpha_arm, side="upper")
    lb_n = one_sided_betting_bound(null_xs, alpha=alpha_arm, side="lower")
    ub_n = one_sided_betting_bound(null_xs, alpha=alpha_arm, side="upper")
    return lb_p - ub_n, ub_p - lb_n


def _av_interval(
    placebo_xs: Sequence[float],
    null_xs: Sequence[float],
    *,
    alpha_arm: float = ALPHA_ARM,
) -> tuple[float, float]:
    """Two-sided anytime-valid interval on mu_P - mu_N via a union bound.

    Each arm contributes a one-sided ``one_sided_betting_bound`` at ``alpha_arm``.
    LB(mu_P - mu_N) = LB(mu_P) - UB(mu_N); UB(mu_P - mu_N) = UB(mu_P) - LB(mu_N).
    With ``alpha_arm = 0.025`` each, the union bound puts each endpoint's error
    at 0.05.
    """
    return _av_interval_cached(tuple(placebo_xs), tuple(null_xs), alpha_arm)


def _wilson(x: int, n: int, z: float) -> tuple[float, float]:
    center = (x + z * z / 2.0) / (n + z * z)
    half = z * sqrt(x * (n - x) / n + z * z / 4.0) / (n + z * z)
    return center - half, center + half


def newcombe_unpaired(
    k1: int, n1: int, k2: int, n2: int, *, level: float = 0.95
) -> tuple[float, float]:
    """Direct two-sided fixed-n interval on p1 - p2 (Newcombe square-and-add Wilson).

    Unpaired: Placebo and Null-A are separate arms. Wald is banned in this
    repository; the square-and-add of the two marginal Wilson intervals is the
    fixed-n comparison the ticket asks for beside the anytime-valid union bound.
    """
    if n1 <= 0 or n2 <= 0:
        raise ValueError(f"arm sample sizes must be positive; got n1={n1}, n2={n2}")
    if not 0 <= k1 <= n1 or not 0 <= k2 <= n2:
        raise ValueError(f"counts out of range: k1={k1}/n1={n1}, k2={k2}/n2={n2}")
    z = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = _wilson(k1, n1, z)
    l2, u2 = _wilson(k2, n2, z)
    delta = p1 - p2
    lower = delta - sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = delta + sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2)
    return lower, upper


def evenly_spaced(n: int, k: int) -> list[float]:
    """Place ``k`` successes at evenly-spaced launch indices in ``n`` slots."""
    if k <= 0:
        return [0.0] * n
    if k >= n:
        return [1.0] * n
    xs = [0.0] * n
    for i in range(k):
        pos = round((i + 0.5) * n / k)
        pos = min(n - 1, max(0, pos))
        xs[pos] = 1.0
    placed = sum(xs)
    j = 0
    while placed < k and j < n:
        if xs[j] == 0.0:
            xs[j] = 1.0
            placed += 1
        j += 1
    return xs


@lru_cache(maxsize=64)
def n_to_exclude_pm(
    correct_ref: int,
    n_ref: int,
    *,
    alpha_arm: float = ALPHA_ARM,
    boundary: float = BOUNDARY,
    cap: int = N_SEARCH_CAP,
) -> int | None:
    """Smallest n at which the same rate excludes +/-boundary under even spacing.

    The same counts means the same rate ``correct_ref / n_ref``, scaled to each
    candidate n. Order is the evenly-spaced launch-index convention named in
    the output. Geometric probing finds a bracket in which exclusion holds;
    a binary search then returns the first n in that bracket. Exclusion is
    treated as monotone in n under this convention (the interval shrinks as
    n grows at a fixed rate). Returns None when no n <= cap reaches exclusion.
    """
    if n_ref <= 0:
        raise ValueError(f"n_ref must be positive; got {n_ref}")
    rate = correct_ref / n_ref

    def excludes(n: int) -> bool:
        k = round(rate * n)
        lo, hi = _av_interval(evenly_spaced(n, k), evenly_spaced(n, k), alpha_arm=alpha_arm)
        return hi < boundary and lo > -boundary

    if excludes(n_ref):
        return n_ref
    probe = n_ref
    last_no: int = n_ref
    while probe < cap:
        probe = min(cap, probe * 2)
        if excludes(probe):
            lo_n, hi_n = last_no, probe
            while hi_n - lo_n > 1:
                mid = (lo_n + hi_n) // 2
                if excludes(mid):
                    hi_n = mid
                else:
                    lo_n = mid
            return hi_n
        last_no = probe
    return None


def placebo_inertness(
    placebo_xs: Sequence[float],
    null_xs: Sequence[float],
    *,
    alpha_arm: float = ALPHA_ARM,
    boundary: float = BOUNDARY,
) -> dict[str, Any]:
    """Compute the Placebo-minus-Null inertness section from raw launch-order outcomes."""
    if not placebo_xs or not null_xs:
        raise ValueError("placebo and null streams must both be non-empty")
    for label, xs in (("placebo", placebo_xs), ("null", null_xs)):
        for i, x in enumerate(xs):
            if x not in (0.0, 1.0):
                raise ValueError(f"{label}[{i}]={x!r} is not a raw 0/1 outcome")

    n_p, n_n = len(placebo_xs), len(null_xs)
    k_p = int(sum(placebo_xs))
    k_n = int(sum(null_xs))
    av_lo, av_hi = _av_interval(placebo_xs, null_xs, alpha_arm=alpha_arm)
    excludes = bool(av_hi < boundary and av_lo > -boundary)
    fixed_lo, fixed_hi = newcombe_unpaired(k_p, n_p, k_n, n_n, level=1.0 - ALPHA)
    fixed_excludes = bool(fixed_hi < boundary and fixed_lo > -boundary)
    n_excl = None
    if not excludes:
        n_excl = n_to_exclude_pm(k_p, n_p, alpha_arm=alpha_arm, boundary=boundary)
    return {
        "n_placebo": n_p,
        "correct_placebo": k_p,
        "n_null": n_n,
        "correct_null": k_n,
        "alpha": ALPHA,
        "alpha_arm": alpha_arm,
        "anytime_valid_lo": av_lo,
        "anytime_valid_hi": av_hi,
        "excludes_pm_boundary": excludes,
        "inertness_established": bool(excludes),
        "n_to_exclude_pm_boundary": n_excl,
        "order_convention": ORDER_CONVENTION,
        "fixed_n_lo": fixed_lo,
        "fixed_n_hi": fixed_hi,
        "fixed_n_excludes_pm_boundary": fixed_excludes,
        "boundary": boundary,
    }


# ---------------------------------------------------------------------------
# Section 2 — Adherence, descriptive only
# ---------------------------------------------------------------------------


def _rate(k: int, n: int) -> str:
    return f"{k}/{n} = {k / n:.3f}" if n else f"{k}/{n} = nan"


def adherence(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Three descriptive adherence rates from per-epoch read and outcome flags."""
    arms: dict[str, Any] = {}
    for arm in ("full", "placebo"):
        cells = _cell_outcomes(rows, arm)
        n = len(cells)
        correct = sum(c for _, c, _ in cells)
        reads = [flag for _, _, flag in cells if flag is not None]
        if len(reads) != n:
            raise ValueError(f"{arm}: every valid epoch must carry a manifest_read flag")
        read_n = sum(1 for flag in reads if flag)
        unread_n = n - read_n
        correct_read = sum(c for _, c, flag in cells if flag)
        correct_unread = sum(c for _, c, flag in cells if not flag)
        arms[arm] = {
            "n": n,
            "correct": correct,
            "read_n": read_n,
            "unread_n": unread_n,
            "correct_read": correct_read,
            "correct_unread": correct_unread,
            "assignment_to_read": _rate(read_n, n),
            "assignment_to_outcome": _rate(correct, n),
            "correct_among_read": _rate(correct_read, read_n),
            "correct_among_unread": _rate(correct_unread, unread_n),
        }
    return {
        "full": arms["full"],
        "placebo": arms["placebo"],
        "post_treatment_sentence": POST_TREATMENT_SENTENCE,
    }


# ---------------------------------------------------------------------------
# Section 3 — Within-pair correlation
# ---------------------------------------------------------------------------


def phi_interval(a: int, b: int, c: int, d: int, *, level: float = 0.95) -> tuple[float, float]:
    """95% interval on the phi coefficient via the Fisher z-transform.

    phi is the Pearson correlation of the two binary correctness indicators.
    z = arctanh(phi), SE = 1/sqrt(n-3), back-transformed with tanh. A table
    with a zero margin or n <= 3 returns (phi, phi) — no interval is claimed.
    """
    n = a + b + c + d
    if n <= 3:
        return float("nan"), float("nan")
    denom = sqrt((a + b) * (c + d) * (a + c) * (b + d))
    if denom == 0.0:
        return float("nan"), float("nan")
    phi = (a * d - b * c) / denom
    if abs(phi) >= 1.0:
        return phi, phi
    z = atanh(phi)
    se = 1.0 / sqrt(n - 3)
    zcrit = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)
    return tanh(z - zcrit * se), tanh(z + zcrit * se)


def within_pair_correlation(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Phi coefficient of Full x Placebo correctness across shared launch indices."""
    full_cells = {epoch: correct for epoch, correct, _ in _cell_outcomes(rows, "full")}
    placebo_cells = {epoch: correct for epoch, correct, _ in _cell_outcomes(rows, "placebo")}
    shared = sorted(set(full_cells) & set(placebo_cells))
    if not shared:
        raise ValueError("no launch index is valid in both Full and Placebo")
    a = sum(1 for e in shared if full_cells[e] and placebo_cells[e])
    b = sum(1 for e in shared if full_cells[e] and not placebo_cells[e])
    c = sum(1 for e in shared if not full_cells[e] and placebo_cells[e])
    d = sum(1 for e in shared if not full_cells[e] and not placebo_cells[e])
    n = a + b + c + d
    denom = sqrt((a + b) * (c + d) * (a + c) * (b + d))
    phi = (a * d - b * c) / denom if denom else 0.0
    lo, hi = phi_interval(a, b, c, d, level=1.0 - ALPHA)
    materially_positive = bool(n >= 4 and denom > 0 and lo > 0.0)
    return {
        "n_pairs": n,
        "both_correct": a,
        "full_only": b,
        "placebo_only": c,
        "neither": d,
        "phi": phi,
        "phi_ci_lo": lo,
        "phi_ci_hi": hi,
        "materially_positive": materially_positive,
        "note": MATERIAL_POSITIVE_NOTE if materially_positive else "",
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_report(data: dict[str, Any]) -> dict[str, Any]:
    """Compute all three sections from a parsed readout."""
    rows = data["rows"]
    placebo_cells = _cell_outcomes(rows, "placebo")
    null_cells = _cell_outcomes(rows, "null")
    placebo_xs = [float(correct) for _, correct, _ in placebo_cells]
    null_xs = [float(correct) for _, correct, _ in null_cells]
    return {
        "inertness": placebo_inertness(placebo_xs, null_xs),
        "adherence": adherence(rows),
        "correlation": within_pair_correlation(rows),
    }


def _boundary_tag(boundary: float) -> str:
    """Machine-parseable tag for a boundary value: 0.20 -> ``0_20``."""
    return f"{boundary:.2f}".replace(".", "_")


def render(report: dict[str, Any]) -> str:
    """Render the three sections as plain text."""
    iner = report["inertness"]
    adh = report["adherence"]
    corr = report["correlation"]
    btag = _boundary_tag(iner["boundary"])
    lines: list[str] = []

    lines.append("=== Placebo inertness (Placebo - Null-A) ===")
    lines.append(f"n_placebo={iner['n_placebo']} correct_placebo={iner['correct_placebo']}")
    lines.append(f"n_null={iner['n_null']} correct_null={iner['correct_null']}")
    lines.append(
        f"anytime_valid_interval=[{iner['anytime_valid_lo']:.4f}, {iner['anytime_valid_hi']:.4f}]"
        f" (union bound, one_sided_betting_bound at alpha={iner['alpha_arm']} each)"
    )
    lines.append(f"excludes_plus_minus_{btag}={str(iner['excludes_pm_boundary']).lower()}")
    if iner["excludes_pm_boundary"]:
        lines.append("inertness_established=true")
    else:
        lines.append("inertness_established=false")
        lines.append(
            "placebo inertness is not established at this n; the interval still admits a"
            f" difference of {iner['boundary']:.2f} in either direction"
        )
        n_excl = iner["n_to_exclude_pm_boundary"]
        if n_excl is None:
            lines.append(
                f"n_to_exclude_pm_{btag}=not_reached_below_{N_SEARCH_CAP}"
                f" (same rates, {iner['order_convention']})"
            )
        else:
            lines.append(
                f"n_to_exclude_pm_{btag}={n_excl} (same rates, {iner['order_convention']})"
            )
    lines.append(
        f"fixed_n_newcombe_interval=[{iner['fixed_n_lo']:.4f}, {iner['fixed_n_hi']:.4f}]"
        " (direct two-sided fixed-n comparison)"
    )
    lines.append(
        f"fixed_n_excludes_plus_minus_{btag}={str(iner['fixed_n_excludes_pm_boundary']).lower()}"
    )
    lines.append("")

    lines.append("=== Adherence (descriptive only) ===")
    lines.append("assignment_to_read:")
    for arm in ("full", "placebo"):
        rec = adh[arm]
        lines.append(f"  {arm}: {rec['assignment_to_read']}")
    lines.append("assignment_to_outcome:")
    for arm in ("full", "placebo"):
        rec = adh[arm]
        lines.append(f"  {arm}: {rec['assignment_to_outcome']}")
    lines.append("read_to_outcome:")
    for arm in ("full", "placebo"):
        rec = adh[arm]
        lines.append(f"  {arm}_correct_among_read: {rec['correct_among_read']}")
        lines.append(f"  {arm}_correct_among_unread: {rec['correct_among_unread']}")
    lines.append(adh["post_treatment_sentence"])
    lines.append("")

    lines.append("=== Within-pair correlation (Full x Placebo, descriptive) ===")
    lines.append(f"n_pairs={corr['n_pairs']}")
    lines.append(
        f"table: both_correct={corr['both_correct']} full_only={corr['full_only']}"
        f" placebo_only={corr['placebo_only']} neither={corr['neither']}"
    )
    lines.append(f"phi={corr['phi']:.4f}")
    lines.append(f"phi_95_ci=[{corr['phi_ci_lo']:.4f}, {corr['phi_ci_hi']:.4f}]")
    lines.append(f"materially_positive={str(corr['materially_positive']).lower()}")
    if corr["note"]:
        lines.append(corr["note"])
    else:
        lines.append(
            "observed correlation is not materially positive; #684's independence"
            " assumption is not contradicted at this n"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "readout",
        type=Path,
        help="path to a Stage 1A readout .json, run.log, or directory holding one",
    )
    args = parser.parse_args(argv)
    data = load_readout(args.readout)
    report = build_report(data)
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
