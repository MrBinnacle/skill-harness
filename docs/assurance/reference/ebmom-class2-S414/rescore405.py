"""Development re-score for skill-harness#405 (S411): the two calibration rows proposed
for the superseding amendment, measured on the branch's own worlds BEFORE any decision.

NOT CONFIRMATORY. Root seed SMOKE_NOT_CONFIRMATORY, R = 40, throwaway. Imports the branch's
fit.py, errors.py and ebmom_acceptance_matrix.py at agent/issue-360 4bd4633 unchanged (copied
beside this file as fit-branch.py, errors-branch.py, matrix.py). Adds nothing to them.

PROPOSED ROWS (the candidate replacement for section 5 rows 5 and 6 as KILL rows):

  5c  false-PASS rate among PASS decisions: #{PASS and true theta_k <= 0.60} / #{PASS}
  6c  false-FAIL rate among FAIL decisions: #{FAIL and true theta_k >  0.60} / #{FAIL}

  Test per regime: exact binomial, one-sided greater, null p = 0.05 (the complement of the
  locked PASS_P = 0.95 and equal to the locked FAIL_P = 0.05), at test level 0.01 -- the same
  construction section 5 row 1 already uses for admission calibration. Rejection = the row
  fails. Truth is the true ENCODED clause mean the generator already returns and the frozen
  harness discards (matrix.run_regime: `clauses, _truths = draw_world(...)`).

  The vs-oracle rows 5, 6, 7 and their excess over main are computed unchanged and REPORTED,
  so this file's numbers stay comparable with smoke405b-R40.json and the confirmatory run.

ESTIMATORS SCORED (same worlds, world for world):

  main      baseline_fit, as the frozen harness scores it.
  cand      branch as-is, HARNESS-faithful refused path: unpooled Beta(1+w, 1+n-w), raw
            threshold. Reproduces the confirmatory run's procedure.
  cand_prod branch as-is, PRODUCTION-faithful refused path: PASS requires the clause to be in
            fit_skill's bh_fdr_passes AND raw P >= 0.95 (engine.py:355-363, status.py B1);
            FAIL by raw threshold. The frozen harness does not model this.
  cand_bpA  admitted path as cand; on REFUSAL, bounded pooling at the one-sided (1 - alpha)
            upper confidence bound on the latent variance:
                v_bound = latent_raw + z_{0.95} * se,  se = sqrt(2 / (K - 1)) * total_var
                c_bound = mu (1 - mu) / v_bound - 1
            (the form S406 Finding C measured), decided by the locked rule, no BH-FDR.
  cand_bpB  admitted path as cand; on REFUSAL, bounded pooling at the admission test's own
            critical order statistic: v_bound = critical_order_statistic, so the estimator is
            continuous across the admission boundary. Decided by the locked rule, no BH-FDR.

  On either bounded-pooling path a non-positive c_bound falls back to unpooled and is counted.

PREDICTIONS, stated before the run (scored in RESULTS.md whichever way they land):

  P1  cand FAILS row 6c in tie_heavy_null: every clause there has theta = 0.65, so every FAIL
      is false by construction; 12 FAILs at R = 40 give an exact-binomial p of 0.05^12.
  P2  cand PASSES row 5c in all five regimes.
  P3  cand_bpA and cand_bpB PASS both rows in tie_heavy_null.
  P4  main FAILS row 5c in small_n_bite. This is the least confident prediction: main's 823
      wrong-vs-oracle PASSes there sit at oracle probabilities near 0.85-0.95, so 5-15 percent
      of them are truly false, and whether the aggregate clears 0.05 depends on the mix.
  P5  cand PASSES row 5c in low_heterogeneity: its 109 wrong-vs-oracle PASSes sit at oracle
      P = 0.904 and 0.932, so at most 10 percent of them are truly false.
  P6  Faithfulness control: cand's vs-oracle excess over main reproduces smoke405b-R40.json's
      plugin row exactly in every regime (-567,-122,+1 / +109,+19,-194 / 0,-35,0 / 0,+12,-14 /
      +17,0,-164).

Run from this directory:  python rescore405.py 40
Output: rescore405-R40.json and a table on stdout. ASCII only.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
import types
from pathlib import Path
from typing import Any

from scipy.stats import beta as beta_dist
from scipy.stats import binomtest, norm

HERE = Path(__file__).parent


def _load(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.modules["skill_harness"] = types.ModuleType("skill_harness")
sys.modules["skill_harness.aggregation"] = types.ModuleType("skill_harness.aggregation")
_load("skill_harness.aggregation.errors", HERE / "errors-branch.py")
fit_branch = _load("skill_harness.aggregation.fit", HERE / "fit-branch.py")
matrix = _load("matrix", HERE / "matrix.py")

T = float(fit_branch.WIN_RATE_THRESHOLD)
VAR_FLOOR = float(fit_branch.VAR_FLOOR)
ALPHA = float(fit_branch.HETEROGENEITY_TEST_ALPHA)
Z_UPPER = float(norm.ppf(1.0 - ALPHA))
PASS_P = float(matrix.PASS_P)
FAIL_P = float(matrix.FAIL_P)
CAL_NULL_P = 1.0 - PASS_P  # 0.05; equals FAIL_P by the locked rule
CAL_TEST_LEVEL = float(matrix.CALIBRATION_TEST_LEVEL)  # 0.01, row 1's level
ROOT = "SMOKE_NOT_CONFIRMATORY"
ESTIMATORS = ("oracle", "main", "cand", "cand_prod", "cand_bpA", "cand_bpB")
# "oracle" is the reference column, not a candidate: the decider that knows the true
# hyperprior, scored against the same truth. If it fails a calibration row, the regime's
# generative model or its oracle is mis-specified (a harness self-check, not a kill).

SMOKE405B_PLUGIN_EXCESS = {
    "small_n_bite": (-567, -122, 1),
    "low_heterogeneity": (109, 19, -194),
    "benign_large_n": (0, -35, 0),
    "tie_heavy_null": (0, 12, -14),
    "tie_heavy_signal": (17, 0, -164),
}


def decisions_from_prior(clauses, a0: float, b0: float) -> list[str]:
    return [
        matrix.decision(float(beta_dist.sf(T, a0 + cl.w, b0 + (cl.n - cl.w)))) for cl in clauses
    ]


def bounded_c(mu: float, v_bound: float) -> float | None:
    if v_bound <= VAR_FLOOR:
        return None
    c = mu * (1.0 - mu) / v_bound - 1.0
    if c <= 0.0 or mu * c <= 0.0 or (1.0 - mu) * c <= 0.0:
        return None
    return c


class Tally:
    """Counts for one estimator in one regime, split by path.

    S411 correction: the first version tallied paths POOLED, and the per-path rates were
    then derived by subtracting one column's total from another's. That derivation is only
    valid if the column being subtracted contributed zero decisions of that kind on the
    refused path, which was true at R = 40 in `low_heterogeneity` and is NOT established at
    R = 1000. Two derived figures were published on the ticket before this was caught. The
    tally is now per path at source, and nothing is derived.

    A world is one cluster. `worlds` counts, per path and per decision kind, how many
    distinct replicates contributed a FALSE decision, because a cell of four decisions drawn
    from one world is not four independent observations and the amendment's clustered bound
    needs the cluster count, not the decision count.
    """

    def __init__(self) -> None:
        self.pass_n = {"admitted": 0, "refused": 0}
        self.pass_false = {"admitted": 0, "refused": 0}
        self.fail_n = {"admitted": 0, "refused": 0}
        self.fail_false = {"admitted": 0, "refused": 0}
        self.pass_false_worlds: dict[str, set[int]] = {"admitted": set(), "refused": set()}
        self.fail_false_worlds: dict[str, set[int]] = {"admitted": set(), "refused": set()}
        self.pass_worlds: dict[str, set[int]] = {"admitted": set(), "refused": set()}
        self.fail_worlds: dict[str, set[int]] = {"admitted": set(), "refused": set()}
        self.wrong_pass = 0
        self.wrong_fail = 0
        self.abstain = 0

    def add(self, fitted: list[str], oracle: list[str], truths: list[float],
            path: str, world: int) -> None:
        wp, wf, ab = matrix.score(oracle, fitted)
        self.wrong_pass += wp
        self.wrong_fail += wf
        self.abstain += ab
        for d, th in zip(fitted, truths, strict=True):
            if d == "PASS":
                self.pass_n[path] += 1
                self.pass_worlds[path].add(world)
                if th <= T:
                    self.pass_false[path] += 1
                    self.pass_false_worlds[path].add(world)
            elif d == "FAIL":
                self.fail_n[path] += 1
                self.fail_worlds[path].add(world)
                if th > T:
                    self.fail_false[path] += 1
                    self.fail_false_worlds[path].add(world)

    def row(self) -> dict[str, Any]:
        def cal(k: int, n: int, false_worlds: int, worlds: int) -> dict[str, Any]:
            if n == 0:
                return {"count": 0, "of": 0, "rate": None, "p_value": None, "passes": None,
                        "worlds": worlds, "false_worlds": false_worlds,
                        "note": "no decisions of this kind; row not testable"}
            p = float(binomtest(k, n, CAL_NULL_P, alternative="greater").pvalue)
            return {"count": k, "of": n, "rate": k / n, "p_value": p,
                    "passes_exact_binomial": p >= CAL_TEST_LEVEL,
                    "worlds": worlds, "false_worlds": false_worlds,
                    "note": "the exact binomial treats clause decisions as independent; the "
                            "amendment's kill is a world-block bootstrap and `worlds` is the "
                            "cluster count that bound needs"}

        out: dict[str, Any] = {
            "vs_oracle": {"wrong_pass": self.wrong_pass, "wrong_fail": self.wrong_fail,
                          "abstention": self.abstain},
        }
        for path in ("admitted", "refused"):
            out[f"row5c_false_pass_{path}"] = cal(
                self.pass_false[path], self.pass_n[path],
                len(self.pass_false_worlds[path]), len(self.pass_worlds[path]))
            out[f"row6c_false_fail_{path}"] = cal(
                self.fail_false[path], self.fail_n[path],
                len(self.fail_false_worlds[path]), len(self.fail_worlds[path]))
        out["row5c_false_pass_pooled"] = cal(
            sum(self.pass_false.values()), sum(self.pass_n.values()),
            len(self.pass_false_worlds["admitted"] | self.pass_false_worlds["refused"]),
            len(self.pass_worlds["admitted"] | self.pass_worlds["refused"]))
        out["row6c_false_fail_pooled"] = cal(
            sum(self.fail_false.values()), sum(self.fail_n.values()),
            len(self.fail_false_worlds["admitted"] | self.fail_false_worlds["refused"]),
            len(self.fail_worlds["admitted"] | self.fail_worlds["refused"]))
        return out


def run(replicates: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "root_seed": ROOT, "replicates": replicates, "is_confirmatory": False,
        "cal_null_p": CAL_NULL_P, "cal_test_level": CAL_TEST_LEVEL, "z_upper": Z_UPPER,
        "regimes": {},
    }
    for regime in matrix.REGIMES:
        t0 = time.time()
        tallies = {e: Tally() for e in ESTIMATORS}
        admitted = 0
        bp_fallback = {"cand_bpA": 0, "cand_bpB": 0}
        for r in range(replicates):
            clauses, truths = matrix.draw_world(regime, matrix.derive_seed(ROOT, regime.name, r))
            oracle = matrix.oracle_decisions(regime, clauses)
            k = len(clauses)

            # The candidate's admission verdict labels the world for EVERY column, including
            # `oracle` and `main`, which have no admission concept of their own. That keeps the
            # per-path slices comparable: "the refused path" names a set of worlds, and each
            # column's rate on that set answers "what does this decider do where the candidate
            # refuses". It is not a claim that `main` refuses anything.
            res = fit_branch.fit_skill(clauses)
            prov = res.aggregation_provenance
            is_admitted = res.aggregation_method == "ebmom_hierarchical"
            path = "admitted" if is_admitted else "refused"

            tallies["oracle"].add(oracle, oracle, truths, path, r)
            ba, bb = matrix.baseline_fit(clauses)[1:]
            tallies["main"].add(matrix.fitted_decisions(clauses, ba, bb), oracle, truths, path, r)

            if is_admitted:
                admitted += 1
                a0, b0 = float(prov["alpha_hat"]), float(prov["beta_hat"])
                dec = decisions_from_prior(clauses, a0, b0)
                for e in ("cand", "cand_prod", "cand_bpA", "cand_bpB"):
                    tallies[e].add(dec, oracle, truths, path, r)
                continue

            unpooled = decisions_from_prior(clauses, 1.0, 1.0)
            tallies["cand"].add(unpooled, oracle, truths, path, r)

            passes = res.bh_fdr_passes if res.bh_fdr_passes is not None else frozenset()
            prod = [
                ("PASS" if cl.clause_id in passes else "UNDECIDED") if d == "PASS" else d
                for d, cl in zip(unpooled, clauses, strict=True)
            ]
            tallies["cand_prod"].add(prod, oracle, truths, path, r)

            att = prov["attempted"]
            mu = float(att["sample_mean"])
            latent_raw = float(att["latent_var_raw"])
            total_var = float(att["sample_var_raw"])
            het = att["heterogeneity_test"]
            se = math.sqrt(2.0 / (k - 1)) * total_var

            cA = bounded_c(mu, latent_raw + Z_UPPER * se)
            if cA is None:
                bp_fallback["cand_bpA"] += 1
                tallies["cand_bpA"].add(unpooled, oracle, truths, path, r)
            else:
                tallies["cand_bpA"].add(
                    decisions_from_prior(clauses, mu * cA, (1 - mu) * cA), oracle, truths, path, r)

            cB = bounded_c(mu, float(het["critical_order_statistic"]))
            if cB is None:
                bp_fallback["cand_bpB"] += 1
                tallies["cand_bpB"].add(unpooled, oracle, truths, path, r)
            else:
                tallies["cand_bpB"].add(
                    decisions_from_prior(clauses, mu * cB, (1 - mu) * cB), oracle, truths, path, r)

        rows = {e: tallies[e].row() for e in ESTIMATORS}
        m = tallies["main"]
        excess = {}
        for e in ESTIMATORS:
            t = tallies[e]
            excess[e] = (t.wrong_pass - m.wrong_pass, t.wrong_fail - m.wrong_fail, t.abstain - m.abstain)
        ctrl = tuple(excess["cand"]) == SMOKE405B_PLUGIN_EXCESS[regime.name]
        out["regimes"][regime.name] = {
            "admitted": admitted, "replicates": replicates,
            "bounded_pooling_unpooled_fallbacks": bp_fallback,
            "estimators": rows, "excess_over_main_vs_oracle": excess,
            "faithfulness_control_matches_smoke405b": ctrl,
            "seconds": round(time.time() - t0, 1),
        }
        print(f"[{regime.name}] admitted {admitted}/{replicates}  control={ctrl}  "
              f"{time.time()-t0:.0f}s", flush=True)
        for e in ESTIMATORS:
            print(f"   {e:10s} vs-oracle excess {excess[e]}", flush=True)
            for path in ("admitted", "refused"):
                r5 = rows[e][f"row5c_false_pass_{path}"]
                r6 = rows[e][f"row6c_false_fail_{path}"]
                print(f"      {path:8s} 5c {r5['count']:>6}/{r5['of']:<7}"
                      f"(worlds {r5['false_worlds']}/{r5['worlds']})   "
                      f"6c {r6['count']:>6}/{r6['of']:<7}"
                      f"(worlds {r6['false_worlds']}/{r6['worlds']})", flush=True)
    return out


if __name__ == "__main__":
    R = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    if len(sys.argv) > 2:
        # A different root: used ONLY for the burned confirmatory root f95e4de5..., whose
        # worlds became development evidence when the 2026-09-05 run rejected. Never a
        # fresh root: that is section 9's, committed by digest before it is revealed.
        ROOT = sys.argv[2]
    report = run(R)
    tag = "" if len(sys.argv) <= 2 else "-" + ROOT[:8]
    path = HERE / f"rescore405-R{R}{tag}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path}")
