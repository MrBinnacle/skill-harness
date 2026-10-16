"""Development demonstration behind the 2026-09-02 heterogeneity-target ruling on #360.

NOT confirmatory. PINNED TO COMMIT 7d50b4a: this script monkeypatches the
`_draw_null_clause(clause, encoded_mean_0, rng)` signature that existed at that commit and
does not run against the amended null. Run it from a detached worktree of 7d50b4a with
PYTHONPATH pointing at that worktree's src/. It exists so the table in
docs/assurance/ebmom-peel-preregistration-amendment.md (section 3, the null as amended) is
re-derivable, not so it can be re-run against main.

Measures the admission rate of three candidate bootstrap nulls on two synthetic worlds,
R replicates each, root seed SMOKE_NOT_CONFIRMATORY (the throwaway seed the branch already
used). Nothing here moves a threshold; it shows which null matches which hypothesis. ASCII only.

Nulls:
  current  : ties fixed per clause, encoded mean common (7d50b4a as built; superseded)
  decisive : ties fixed per clause, decisive rate common (reading D)
  encoded  : all outcomes redrawn from one pooled categorical (reading E; ruled)

Worlds:
  tie_heavy_null : registered regime; common p=0.75, common t=0.40; theta=0.65 for all
  tie_split      : common p=0.75; t alternates 0.20/0.60 by clause; theta=0.70/0.60
                   (homogeneous in p, heterogeneous in theta)

Measured 2026-09-02 (admitted / R):
  tie_heavy_null  current 16/40, 79/200   decisive 0/40, 7/200   encoded 0/40, 5/200
  tie_split       current 40/40, 200/200  decisive 2/40, 9/200   encoded 40/40, 199/200
"""

from __future__ import annotations

import json
import random
import sys
import time

from skill_harness.aggregation import fit
from skill_harness.aggregation.fit import ClauseObservations, _decompose

sys.path.insert(0, "scripts")
from ebmom_acceptance_matrix import REGIMES, derive_seed, draw_world

ROOT = "SMOKE_NOT_CONFIRMATORY"
R = int(sys.argv[1]) if len(sys.argv) > 1 else 40

TIE_HEAVY_NULL = next(r for r in REGIMES if r.name == "tie_heavy_null")


def draw_tie_split(
    seed: int, k: int = 200, n: int = 25, p: float = 0.75
) -> list[ClauseObservations]:
    rng = random.Random(seed)  # noqa: S311
    out = []
    for i in range(k):
        t = 0.20 if i % 2 == 0 else 0.60
        w = ss = 0.0
        for _ in range(n):
            if rng.random() < t:
                obs = 0.5
            elif rng.random() < p:
                obs = 1.0
            else:
                obs = 0.0
            w += obs
            ss += obs * obs
        out.append(ClauseObservations(clause_id=f"c{i}", w=w, n=n, sum_sq=ss))
    return out


# --- candidate nulls, each a drop-in for fit._draw_null_clause -------------

_current = fit._draw_null_clause


def _null_decisive(clause, encoded_mean_0, rng, *, pooled):
    """Reading D: ties fixed, common decisive rate p_0 = sum wins / sum decisive."""
    _w, ties, _l = _decompose(clause)
    decisive = clause.n - ties
    w = 0.5 * ties
    ss = 0.25 * ties
    for _ in range(decisive):
        if rng.random() < pooled["p_0"]:
            w += 1.0
            ss += 1.0
    return ClauseObservations(clause_id=clause.clause_id, w=w, n=clause.n, sum_sq=ss)


def _null_encoded(clause, encoded_mean_0, rng, *, pooled):
    """Reading E: every observation redrawn from the pooled categorical."""
    w = ss = 0.0
    for _ in range(clause.n):
        u = rng.random()
        if u < pooled["t_0"]:
            w += 0.5
            ss += 0.25
        elif u < pooled["t_0"] + pooled["win_0"]:
            w += 1.0
            ss += 1.0
    return ClauseObservations(clause_id=clause.clause_id, w=w, n=clause.n, sum_sq=ss)


def pooled_stats(clauses):
    tot_n = sum(c.n for c in clauses)
    wins = ties = 0
    for c in clauses:
        wi, ti, _ = _decompose(c)
        wins += wi
        ties += ti
    decisive = tot_n - ties
    return {
        "t_0": ties / tot_n,
        "win_0": wins / tot_n,
        "p_0": wins / decisive if decisive else 0.0,
    }


def install(kind):
    if kind == "current":
        fit._draw_null_clause = _current
        return
    state = {}

    def wrapper(clause, encoded_mean_0, rng):
        if "pooled" not in state:
            state["pooled"] = pooled_stats(state["clauses"])
        fn = _null_decisive if kind == "decisive" else _null_encoded
        return fn(clause, encoded_mean_0, rng, pooled=state["pooled"])

    orig_test = fit._heterogeneity_test

    def test_wrapper(clauses, latent_var_raw):
        state.clear()
        state["clauses"] = clauses
        return orig_test(clauses, latent_var_raw)

    fit._draw_null_clause = wrapper
    fit._heterogeneity_test = test_wrapper


ORIG_TEST = fit._heterogeneity_test


def run(kind, world):
    fit._heterogeneity_test = ORIG_TEST
    install(kind)
    admitted = 0
    stats = []
    for r in range(R):
        seed = derive_seed(ROOT, world, r)
        clauses = (
            draw_world(TIE_HEAVY_NULL, seed)[0]
            if world == "tie_heavy_null"
            else draw_tie_split(seed)
        )
        res = fit.fit_skill(clauses)
        prov = res.aggregation_provenance
        test = prov.get("heterogeneity_test") or prov["attempted"]["heterogeneity_test"]
        admitted += int(test["admitted"])
        stats.append(test["statistic"])
    fit._heterogeneity_test = ORIG_TEST
    fit._draw_null_clause = _current
    return {"admitted": admitted, "R": R, "rate": admitted / R, "mean_latent_raw": sum(stats) / R}


if __name__ == "__main__":
    t0 = time.time()
    out = {}
    for world in ("tie_heavy_null", "tie_split"):
        for kind in ("current", "decisive", "encoded"):
            out[f"{world}/{kind}"] = run(kind, world)
            print(
                f"{world:15s} {kind:9s} {out[f'{world}/{kind}']}  t={time.time() - t0:.0f}s",
                flush=True,
            )
    print(json.dumps(out, indent=2))
