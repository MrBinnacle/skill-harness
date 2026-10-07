"""World-block bootstrap bounds for rows 5c and 6c, per regime, estimator and path (S412).

Reads the per-world dump written by rescore405_worlds.py and computes, for every cell, the
one-sided 99 percent LOWER percentile bound on the false-claim rate that the sh#405 ruling of
2026-09-05 registered as the kill construction:

    resample the regime's R worlds with replacement, B = 999;
    on each resample, rate = sum(false) / sum(decisions) over the resampled worlds on the path;
    a resample with zero decisions on the path has no rate and is counted as 0 (it cannot show
    the rate above 0.05), and the count of such resamples is reported;
    the bound is the 10th smallest of the 999 rates (the order-statistic form, not an
    interpolated quantile, matching the amendment's finite-B rule);
    the row FAILS when the bound exceeds 0.05.

Also reported per cell, because the minimum-cluster question turns on them:

    G        decision-bearing worlds on the path (clusters with at least one decision)
    g        false-bearing worlds (clusters with at least one false decision)
    p_none   exact probability a resample of R worlds contains NO false-bearing world,
             ((R - g) / R) ** R; when this exceeds 0.01 the 1st percentile is 0 by construction
    p_exact  exact binomial p, one-sided greater, null 0.05, valid only when every decision in
             the cell sits in its own world (n == G)

Seeds: SHA-256 over "<root>|<regime>|<estimator>|<path>|<row>", first 8 bytes big-endian,
numpy default_rng. Deterministic, replayable.

Run from this directory:
    python clustered_bound.py <worlds.json>            every world
    python clustered_bound.py <worlds.json> 500:1000   worlds 500 to 999 only (the freeze half)

Reads either dump layout: rescore405_worlds.py writes the per-world table at the top level,
proto_pb.py writes it per regime. A subrange skips the per-path faithfulness control, because the
summary cells it checks are totals over every world, and it draws from its own seed stream.
Writes <input stem>-bounds.json and prints a table. ASCII only.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

B = 999
LEVEL_INDEX = 9          # the 10th smallest of 999 = one-sided 99 percent lower bound
KILL = 0.05
NULL_P = 0.05
TEST_LEVEL = 0.01


def seed_for(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def cell(root: str, regime: str, est: str, path: str, row: str, R: int,
         n_w: np.ndarray, f_w: np.ndarray) -> dict:
    n_total = int(n_w.sum())
    f_total = int(f_w.sum())
    G = int((n_w > 0).sum())
    g = int((f_w > 0).sum())
    out = {"decisions": n_total, "false": f_total, "G_decision_worlds": G,
           "g_false_worlds": g, "rate": (f_total / n_total) if n_total else None,
           "p_none_false_world": ((R - g) / R) ** R,
           "p_exact_binomial": None, "exact_binomial_valid": None,
           "bound_lower_99": None, "undefined_resamples": None, "fails": None}
    if n_total == 0:
        out["note"] = "no decisions of this kind on this path; not testable"
        return out
    out["p_exact_binomial"] = float(binomtest(f_total, n_total, NULL_P, alternative="greater").pvalue)
    out["exact_binomial_valid"] = bool(n_total == G)
    rng = np.random.default_rng(seed_for(root, regime, est, path, row))
    counts = rng.multinomial(R, np.full(R, 1.0 / R), size=B)          # (B, R) world multiplicities
    num = counts @ f_w
    den = counts @ n_w
    undefined = int((den == 0).sum())
    rates = np.where(den > 0, num / np.where(den > 0, den, 1), 0.0)
    rates.sort()
    bound = float(rates[LEVEL_INDEX])
    out.update({"bound_lower_99": bound, "undefined_resamples": undefined,
                "fails": bool(bound > KILL), "B": B})
    # S412 kill test: exact binomial over ONE decision per decision-bearing world. The
    # amendment's harness selects the decision by a seeded draw over clause_id; this dump
    # holds per-world counts only, so the selected decision's false indicator is drawn as
    # Bernoulli(false_w / n_w), which has the same distribution as selecting uniformly.
    rng1 = np.random.default_rng(seed_for(root, regime, est, path, row, "one-per-world"))
    idx = np.flatnonzero(n_w > 0)
    k = int((rng1.random(idx.size) < (f_w[idx] / n_w[idx])).sum())
    p1 = float(binomtest(k, G, NULL_P, alternative="greater").pvalue)
    # Is the cell's verdict fixed by the counts, or could another seed flip it? A world whose
    # decisions are ALL false contributes a false selection under every draw; a world with no
    # false decision contributes none under any. So k lies in [k_min, k_max] and the verdict is
    # fixed exactly when the rejection threshold sits outside that interval.
    k_min = int(((f_w[idx] == n_w[idx]) & (f_w[idx] > 0)).sum())
    k_max = g
    k_rej = None
    for t in range(G + 1):
        if binomtest(t, G, NULL_P, alternative="greater").pvalue < TEST_LEVEL:
            k_rej = t
            break
    fixed = k_rej is None or k_min >= k_rej or k_max < k_rej
    # How seed-dependent is it really? Over the seeded selection, k is Poisson-binomial with
    # per-world success f_w / n_w. Exact tail by DP; this is the probability that a different
    # registered seed reverses the cell's verdict, given these counts.
    p_reject = None
    if k_rej is not None:
        pw = f_w[idx] / n_w[idx]
        dist = np.zeros(G + 1)
        dist[0] = 1.0
        for q in pw:
            dist[1:] = dist[1:] * (1 - q) + dist[:-1] * q
            dist[0] *= (1 - q)
        p_reject = float(dist[k_rej:].sum())
    out.update({"opw_selected_false": k, "opw_G": G, "opw_p_exact": p1,
                "opw_fails": bool(p1 < TEST_LEVEL),
                "opw_k_min": k_min, "opw_k_max": k_max, "opw_k_reject_at": k_rej,
                "opw_verdict_fixed_by_counts": bool(fixed),
                "opw_p_reject_over_seeds": p_reject})
    return out


def _per_world(d: dict) -> dict:
    """Both dump layouts, normalised to {regime: {column: rows}}.

    `rescore405_worlds.py` writes the table at the top level under "per_world"; `proto_pb.py`
    writes it per regime under regimes[name]["per_world"]. The rows are the same six fields in
    the same order either way, and this file asserts that before using them.
    """
    if "per_world" in d:
        assert d["per_world_fields"] == ["world", "path", "pass_n", "pass_false",
                                         "fail_n", "fail_false"], d["per_world_fields"]
        return d["per_world"]
    return {name: reg["per_world"] for name, reg in d["regimes"].items()}


def main(path: Path, lo: int | None = None, hi: int | None = None) -> None:
    d = json.loads(path.read_text(encoding="utf-8"))
    root = d["root_seed"]
    R_full = int(d["replicates"])
    per_world_all = _per_world(d)
    sub = lo is not None
    lo = 0 if lo is None else lo
    hi = R_full if hi is None else hi
    assert 0 <= lo < hi <= R_full, (lo, hi, R_full)
    R = hi - lo
    result: dict = {"source": path.name, "root_seed": root, "replicates": R_full, "B": B,
                    "bound": "10th smallest of 999 world-block resample rates", "kill": KILL,
                    "world_range": [lo, hi], "is_subrange": sub,
                    "mechanism": d.get("mechanism", "none"), "regimes": {}}
    if sub:
        print(f"WORLD RANGE [{lo}, {hi}): {R} of {R_full} worlds. The per-path faithfulness "
              f"control is SKIPPED, because the summary cells it checks against are totals over "
              f"all {R_full} worlds. Seeds include the range, so a subrange is not a subset of "
              f"the full run's draws.", flush=True)
    print(f"{'regime':18s} {'column':9s} {'path':8s} row  false/dec   G    g   rate    bound99  p_none  exact_p   bound-verdict | opw k/G  opw_p    opw   [kmin,kmax] rej>=  seed-dep")
    for regime, cols in per_world_all.items():
        result["regimes"][regime] = {}
        # control: per-world sums must equal the summary cells the runner wrote. Only meaningful
        # over the full range; a subrange is a slice of those totals and cannot equal them.
        if not sub:
            for est, rows in cols.items():
                est_rows = d["regimes"][regime]["estimators"][est]
                for p in ("admitted", "refused"):
                    part = [r for r in rows if r[1] == p]
                    assert sum(r[2] for r in part) == est_rows[f"row5c_false_pass_{p}"]["of"], (regime, est, p)
                    assert sum(r[3] for r in part) == est_rows[f"row5c_false_pass_{p}"]["count"], (regime, est, p)
                    assert sum(r[4] for r in part) == est_rows[f"row6c_false_fail_{p}"]["of"], (regime, est, p)
                    assert sum(r[5] for r in part) == est_rows[f"row6c_false_fail_{p}"]["count"], (regime, est, p)
        for est, rows in cols.items():
            result["regimes"][regime][est] = {}
            for p in ("admitted", "refused"):
                for row, ni, fi in (("5c", 2, 3), ("6c", 4, 5)):
                    n_w = np.zeros(R)
                    f_w = np.zeros(R)
                    for r in rows:
                        if r[1] == p and lo <= r[0] < hi:
                            n_w[r[0] - lo] = r[ni]
                            f_w[r[0] - lo] = r[fi]
                    # The full-range seed label is unchanged, so the committed full-run table
                    # stays reproducible; a subrange gets its own stream.
                    label = root if not sub else f"{root}|worlds{lo}:{hi}"
                    c = cell(label, regime, est, p, row, R, n_w, f_w)
                    result["regimes"][regime][est][f"{row}_{p}"] = c
                    if c["decisions"] == 0:
                        verdict = "n/t"
                    else:
                        verdict = "FAIL" if c["fails"] else "pass"
                        if c["p_none_false_world"] > TEST_LEVEL and c["false"] > 0:
                            verdict += " (vacuous)"
                    rate = f"{c['rate']:.4f}" if c["rate"] is not None else "   -  "
                    bound = f"{c['bound_lower_99']:.4f}" if c["bound_lower_99"] is not None else "   -  "
                    pe = f"{c['p_exact_binomial']:.2e}" if c["p_exact_binomial"] is not None else "   -   "
                    if c["decisions"] == 0:
                        opw = "         n/t                   "
                    else:
                        rej = c["opw_k_reject_at"]
                        opw = (f"{c['opw_selected_false']:>3}/{c['opw_G']:<4} {c['opw_p_exact']:.2e}  "
                               + f"{('FAIL' if c['opw_fails'] else 'pass'):4s}"
                               + f"  [{c['opw_k_min']:>3},{c['opw_k_max']:>3}] rej>={str(rej):<4s} "
                               + ("fixed" if c["opw_verdict_fixed_by_counts"]
                                  else f"P(rej)={c['opw_p_reject_over_seeds']:.3f}"))
                    print(f"{regime:18s} {est:9s} {p:8s} {row}  {c['false']:>5}/{c['decisions']:<6} "
                          f"{c['G_decision_worlds']:>4} {c['g_false_worlds']:>4}  {rate}  {bound}  "
                          f"{c['p_none_false_world']:.3f}   {pe}  {verdict:16s} | {opw}")
    suffix = "-bounds" if not sub else f"-bounds-w{lo}-{hi}"
    out = path.with_name(path.stem + suffix + ".json")
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    rng_arg = sys.argv[2] if len(sys.argv) > 2 else None
    if rng_arg is None:
        main(Path(sys.argv[1]))
    else:
        a, b = rng_arg.split(":")
        main(Path(sys.argv[1]), int(a), int(b))
