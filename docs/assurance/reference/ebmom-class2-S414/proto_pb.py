"""Mechanism class 2 for the admitted path: admission-conditioned parametric bootstrap (S413).

NOT a mechanism of record. A development probe under amendment v1 section 7 item 2, measuring the
second class named in v2 section 4 after the first (normal-approximation hyperparameter
uncertainty, `proto_hu.py`) narrowed the failing cell without clearing it. Ticket: sh#437 item 1.

The mechanism (`cand_pb` column). On an ADMITTED fit, decide each clause not on the plug-in
posterior Beta(alpha_hat + w_k, beta_hat + n_k - w_k) but on the tail probability averaged over S
draws of the hyperparameters from the finite-sample distribution the fitted model itself implies,
conditioned on admission:

    draw K clause means      theta_j ~ Beta(alpha_hat, beta_hat)
    draw one synthetic world under those means, preserving every clause's n_k and the pooled
      tie fraction the observed data carry
    recompute the moments the fit computes: mu*, sample_var*, sampling_var*, latent* = the peel
    KEEP the draw when latent* > crit, the admission test's critical order statistic; the fit was
      admitted, so the sampling distribution is conditioned on the event that admitted it
    c_s = mu_s (1 - mu_s) / latent_s - 1;  draws with c_s <= 0 are dropped and counted
    P_k = mean_s  P(theta > 0.60 | Beta(mu_s c_s + w_k, (1 - mu_s) c_s + n_k - w_k))

decided by the locked rule (PASS >= 0.95, FAIL <= 0.05), on the OBSERVED w_k and n_k. S = 200
kept draws. Seeds from SHA-256 over "<root>|<regime>|<world>|pb", so the column is deterministic.
The refused path is form B, so `cand_pb` is the candidate v2 would freeze if class 2 is adopted.

What this replaces and what it does not. Class 1 drew (mu, v) from a normal approximation to their
sampling distribution. Class 2 replaces the normal with the model's own finite-sample distribution,
which at K = 200 and n = 25 is skewed for a variance estimator and is truncated by admission rather
than approximated as truncated. Both classes centre the draws at the fitted values, so neither
corrects the winner's-curse bias in the point estimate; class 2 captures the SHAPE of the sampling
distribution, not a bias correction. This is stated because it bounds what a pass here would mean.

The observation model. The generator draws each observation in {0, 0.5, 1}: a tie with probability
`tie_rate`, else a decisive win with probability p_k. The fitted hyperprior is over the ENCODED
clause mean theta_k = 0.5 t + (1 - t) p_k. To generate a world under drawn encoded means this file
uses the branch's own pooled tie fraction (`fit-branch.py` `_pooled_null`) and inverts the encoding
per clause, p_k = (theta_k - 0.5 t) / (1 - t), which is `_draw_null_clause`'s model generalised from
one pooled mean to one mean per clause. Three of the five registered regimes are tie-free, where
this reduces to the binomial draw exactly.

Usage, from this directory:
    python proto_pb.py worlds  <root> <regime> <world> [<world> ...]   per-clause detail
    python proto_pb.py regime  <root> <regime> <R>                     one regime, per-world dump
    python proto_pb.py all     <root> <R>                              all five regimes
ASCII only.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time

import numpy as np
from scipy.stats import beta as beta_dist

import rescore405 as base

T = base.T
S = 200
MAX_BLOCKS = 40          # bounded effort when admission conditioning is severe
BLOCK = 400              # candidate draws per block


def _pooled_tie(clauses) -> float:
    return float(base.fit_branch._pooled_null(clauses).tie)


def _moments(w: np.ndarray, sum_sq: np.ndarray, n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Recompute (sample_mean, latent_var_raw) exactly as fit_skill does, vectorised over draws.

    fit_skill: rates = w/n; sample_var = sum((r - mean)^2) / (k - 1) [unbiased, /(k-1) not /k];
    sampling_var_k = (sum_sq_k - n_k r_k^2) / ((n_k - 1) n_k), meaned over clauses; the peel is
    sample_var - sampling_var, retained UNCLIPPED.
    """
    r = w / n
    mu = r.mean(axis=1)
    sample_var = r.var(axis=1, ddof=1)
    within_ss = sum_sq - n * r * r
    sampling_var = (within_ss / ((n - 1.0) * n)).mean(axis=1)
    return mu, sample_var - sampling_var


def _draw_worlds(rng, thetas: np.ndarray, n: np.ndarray, tie: float):
    """One synthetic world per row of `thetas`, in the generator's {0, 0.5, 1} alphabet."""
    if tie <= 0.0:
        w = rng.binomial(n.astype(int), np.clip(thetas, 0.0, 1.0))
        return w.astype(float), w.astype(float)     # sum_sq == w on tie-free data
    ties = rng.binomial(n.astype(int), tie)
    decisive = n.astype(int) - ties
    p_dec = np.clip((thetas - 0.5 * tie) / (1.0 - tie), 0.0, 1.0)
    wins = rng.binomial(decisive, p_dec)
    return wins + 0.5 * ties, wins + 0.25 * ties


def pb_probs(clauses, prov, root: str, regime_name: str, world: int) -> tuple[list[float], dict]:
    att = prov["attempted"] if "attempted" in prov else prov
    a0, b0 = float(prov["alpha_hat"]), float(prov["beta_hat"])
    crit = float(att["heterogeneity_test"]["critical_order_statistic"])
    K = len(clauses)
    n = np.array([cl.n for cl in clauses], dtype=float)
    w_obs = np.array([cl.w for cl in clauses], dtype=float)
    tie = _pooled_tie(clauses)

    seed = int.from_bytes(
        hashlib.sha256(f"{root}|{regime_name}|{world}|pb".encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)

    kept_mu: list[np.ndarray] = []
    kept_c: list[np.ndarray] = []
    n_kept = 0
    n_drawn = 0
    n_below_crit = 0
    n_nonpositive_c = 0
    for _ in range(MAX_BLOCKS):
        if n_kept >= S:
            break
        thetas = rng.beta(a0, b0, size=(BLOCK, K))
        w_s, sq_s = _draw_worlds(rng, thetas, np.broadcast_to(n, (BLOCK, K)), tie)
        mu_s, lat_s = _moments(w_s, sq_s, np.broadcast_to(n, (BLOCK, K)))
        n_drawn += BLOCK
        admitted = lat_s > crit
        n_below_crit += int((~admitted).sum())
        mu_s, lat_s = mu_s[admitted], lat_s[admitted]
        c_s = mu_s * (1.0 - mu_s) / lat_s - 1.0
        ok = (c_s > 0.0) & (mu_s > 0.0) & (mu_s < 1.0)
        n_nonpositive_c += int((~ok).sum())
        mu_s, c_s = mu_s[ok], c_s[ok]
        if mu_s.size:
            kept_mu.append(mu_s)
            kept_c.append(c_s)
            n_kept += mu_s.size

    diag = {"drawn": n_drawn, "kept": n_kept, "below_crit": n_below_crit,
            "nonpositive_c": n_nonpositive_c, "exhausted": n_kept < S}
    if n_kept == 0:
        # No admissible draw. The mechanism has nothing to average and falls back to the plug-in,
        # counted, rather than inventing a decision.
        diag["fell_back_to_plugin"] = True
        return [float(beta_dist.sf(T, a0 + cl.w, b0 + (cl.n - cl.w))) for cl in clauses], diag
    diag["fell_back_to_plugin"] = False

    mus = np.concatenate(kept_mu)[:S]
    cs = np.concatenate(kept_c)[:S]
    diag["used"] = int(mus.size)
    a = mus[:, None] * cs[:, None] + w_obs[None, :]
    b = (1.0 - mus[:, None]) * cs[:, None] + (n - w_obs)[None, :]
    probs = beta_dist.sf(T, a, b).mean(axis=0)
    return [float(p) for p in probs], diag


class WorldTally(base.Tally):
    """base.Tally plus the per-world counts clustered_bound.py needs for a split-half score."""

    def __init__(self) -> None:
        super().__init__()
        self.worlds: dict[int, list] = {}

    def add(self, fitted, oracle, truths, path, world) -> None:
        super().add(fitted, oracle, truths, path, world)
        rec = self.worlds.setdefault(world, [path, 0, 0, 0, 0])
        for d, th in zip(fitted, truths, strict=True):
            if d == "PASS":
                rec[1] += 1
                if th <= T:
                    rec[2] += 1
            elif d == "FAIL":
                rec[3] += 1
                if th > T:
                    rec[4] += 1


COLS = ("oracle", "main", "cand_bpB", "cand_pb")


def run_regime(root: str, regime_name: str, R: int) -> dict:
    regime = next(r for r in base.matrix.REGIMES if r.name == regime_name)
    tallies = {c: WorldTally() for c in COLS}
    admitted = 0
    diags = {"exhausted": 0, "plugin_fallback": 0, "below_crit": 0, "drawn": 0, "kept": 0}
    t0 = time.time()
    for r in range(R):
        clauses, truths = base.matrix.draw_world(
            regime, base.matrix.derive_seed(root, regime.name, r))
        oracle = base.matrix.oracle_decisions(regime, clauses)
        res = base.fit_branch.fit_skill(clauses)
        prov = res.aggregation_provenance
        is_adm = res.aggregation_method == "ebmom_hierarchical"
        path = "admitted" if is_adm else "refused"

        tallies["oracle"].add(oracle, oracle, truths, path, r)
        ba, bb = base.matrix.baseline_fit(clauses)[1:]
        tallies["main"].add(base.matrix.fitted_decisions(clauses, ba, bb), oracle, truths, path, r)

        if is_adm:
            admitted += 1
            a0, b0 = float(prov["alpha_hat"]), float(prov["beta_hat"])
            plug = base.decisions_from_prior(clauses, a0, b0)
            tallies["cand_bpB"].add(plug, oracle, truths, path, r)
            probs, d = pb_probs(clauses, prov, root, regime.name, r)
            diags["exhausted"] += int(d["exhausted"])
            diags["plugin_fallback"] += int(d["fell_back_to_plugin"])
            diags["below_crit"] += d["below_crit"]
            diags["drawn"] += d["drawn"]
            diags["kept"] += d["kept"]
            tallies["cand_pb"].add([base.matrix.decision(p) for p in probs],
                                   oracle, truths, path, r)
            continue

        # Refused path: form B for both candidate columns, so the admitted-path mechanism is the
        # only thing that differs between cand_bpB and cand_pb.
        unpooled = base.decisions_from_prior(clauses, 1.0, 1.0)
        att = prov["attempted"]
        mu = float(att["sample_mean"])
        cB = base.bounded_c(mu, float(att["heterogeneity_test"]["critical_order_statistic"]))
        decB = unpooled if cB is None else base.decisions_from_prior(
            clauses, mu * cB, (1 - mu) * cB)
        tallies["cand_bpB"].add(decB, oracle, truths, path, r)
        tallies["cand_pb"].add(decB, oracle, truths, path, r)

    m = tallies["main"]
    rows = {c: tallies[c].row() for c in COLS}
    excess = {c: (tallies[c].wrong_pass - m.wrong_pass,
                  tallies[c].wrong_fail - m.wrong_fail,
                  tallies[c].abstain - m.abstain) for c in COLS}
    secs = round(time.time() - t0, 1)
    print(f"[{regime.name}] admitted {admitted}/{R}  {secs}s  "
          f"pb: exhausted={diags['exhausted']} plugin_fallback={diags['plugin_fallback']} "
          f"kept/drawn={diags['kept']}/{diags['drawn']}", flush=True)
    for c in COLS:
        print(f"   {c:9s} vs-oracle excess {excess[c]}", flush=True)
        for p in ("admitted", "refused"):
            r5 = rows[c][f"row5c_false_pass_{p}"]
            r6 = rows[c][f"row6c_false_fail_{p}"]
            print(f"      {p:8s} 5c {r5['count']:>6}/{r5['of']:<7}(worlds {r5['false_worlds']}"
                  f"/{r5['worlds']})   6c {r6['count']:>6}/{r6['of']:<7}"
                  f"(worlds {r6['false_worlds']}/{r6['worlds']})", flush=True)
    return {
        "admitted": admitted, "replicates": R, "seconds": secs, "pb_diagnostics": diags,
        "estimators": rows, "excess_over_main_vs_oracle": excess,
        "per_world": {c: [[w, *rec] for w, rec in sorted(tallies[c].worlds.items())]
                      for c in COLS},
    }


def run_worlds(root: str, regime_name: str, worlds: list[int]) -> None:
    regime = next(r for r in base.matrix.REGIMES if r.name == regime_name)
    for wi in worlds:
        clauses, truths = base.matrix.draw_world(
            regime, base.matrix.derive_seed(root, regime.name, wi))
        res = base.fit_branch.fit_skill(clauses)
        if res.aggregation_method != "ebmom_hierarchical":
            print(f"world {wi}: refused; this class applies to admitted fits only")
            continue
        prov = res.aggregation_provenance
        a0, b0 = float(prov["alpha_hat"]), float(prov["beta_hat"])
        plug = base.decisions_from_prior(clauses, a0, b0)
        probs, d = pb_probs(clauses, prov, root, regime.name, wi)
        pb = [base.matrix.decision(p) for p in probs]
        print(f"== world {wi}: c_hat={a0 + b0:.1f} kept={d.get('used', 0)}/{d['drawn']} "
              f"below_crit={d['below_crit']} nonpositive_c={d['nonpositive_c']}"
              + ("  PLUGIN FALLBACK" if d["fell_back_to_plugin"] else ""))
        for cl, dp, p, th, d2 in zip(clauses, plug, probs, truths, pb, strict=True):
            if dp == "FAIL" or d2 == "FAIL":
                pp = float(beta_dist.sf(T, a0 + cl.w, b0 + (cl.n - cl.w)))
                print(f"   {cl.clause_id}: w={cl.w:.0f}/{cl.n}  truth={th:.4f}  "
                      f"plug P={pp:.4f} -> {dp}   pb P={p:.4f} -> {d2}")
        flips = sum(1 for dp, d2 in zip(plug, pb, strict=True) if dp != d2)
        print(f"   decisions changed by the mechanism: {flips} of {len(clauses)}")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "worlds":
        run_worlds(sys.argv[2], sys.argv[3], [int(x) for x in sys.argv[4:]])
    elif mode == "regime":
        root, name, R = sys.argv[2], sys.argv[3], int(sys.argv[4])
        rep = {"root_seed": root, "replicates": R, "is_confirmatory": False, "mechanism": "class2",
               "S": S, "regimes": {name: run_regime(root, name, R)}}
        out = base.HERE / f"proto-pb-{name}-R{R}-{root[:8]}.json"
        out.write_text(json.dumps(rep, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {out}", flush=True)
    else:
        root, R = sys.argv[2], int(sys.argv[3])
        rep = {"root_seed": root, "replicates": R, "is_confirmatory": False, "mechanism": "class2",
               "S": S, "regimes": {}}
        for reg in base.matrix.REGIMES:
            rep["regimes"][reg.name] = run_regime(root, reg.name, R)
        out = base.HERE / f"proto-pb-all-R{R}-{root[:8]}.json"
        out.write_text(json.dumps(rep, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {out}", flush=True)
