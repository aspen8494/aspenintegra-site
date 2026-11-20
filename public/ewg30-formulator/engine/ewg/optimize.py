"""EWG2.5 formulation optimizer.

Solves for GFC fractions that maximize waste loading while the product glass
satisfies every property and model-validity constraint of PNNL-35884 Rev. 1
Section 3.

Mixing convention (review 2026-10-02, fix #6 — paper Table 3-4):
  Table 3-4 "fraction of component oxide in glass" rows are OXIDE mass fractions
  of the final glass.  glass = Σ x_k · e_k where e_k is the oxide contributed by
  component k (Waste row → the waste's oxide vector scaled by its oxide mass
  fraction of total waste mass; GFC rows → their contributed oxide).  The waste
  row value IS the waste loading; the raw GFC mass per unit glass is x_k / y_k
  (y_k = as-fired oxide yield per unit raw GFC).

  Proof: Batch 3 reproduces the paper's Table 3-5 to 4 decimal places under this
  convention (B2O3 0.2200 vs 0.2200, Na2O 0.1413 vs 0.1414, ZnO 0.0400 vs
  0.0400, Fe2O3 0.0321 vs 0.0322); the previous raw-mass-fraction interpretation
  was off 5-11 wt% on every major oxide.

Decision variables: x_k = oxide mass fraction of component k in the final glass
(sum = 1).  Raw GFC demand is recovered post-solve as x_k / y_k.
"""
from __future__ import annotations
import math
import os
from typing import Any, Dict, Optional
import numpy as np
from scipy.optimize import minimize

from .gfc import GFCS, GFC_NAMES, ALL_OXIDES, gfc_matrix
from . import properties as P
from . import tensor_backend as TB

# EWG2 logic (paper 3.3 / App B): don't add V2O5 unless sulfate-limited;
# Cr2O3 <= 0.6 wt% if selected. Enforced via bounds toggled by caller.
CR2O3_MAX = 0.006

def _uc(ucomp, key):
    """Ucomp value for a property in the constraint's own units (0 by default)."""
    return float((ucomp or {}).get(key, 0.0))

# Full component basis: every waste-oxide component + GFC-derived oxides.
# The previous ALL_OXIDES (10 GFC-derived oxides only) silently dropped
# Fe2O3, MnO, P2O5, UO3, ThO2, RE2O3, Bi2O3, MgO from the glass (#3.2 of review).
FULL_OXIDES = [
    "Al2O3","B2O3","CaO","Cl","Cr2O3","F","Fe2O3","K2O","Li2O","MgO","MnO",
    "Na2O","NiO","P2O5","SiO2","SO3","SnO2","TiO2","V2O5","ZnO","ZrO2",
    "RE2O3","Bi2O3","BaO","CdO","SrO","PbO","Ag2O","PdO","Rh2O3","RuO2",
    "UO3","ThO2","As2O3","BeO","CoO","CuO","HgO","MoO3","Nb2O5",
    "Sb2O3","SeO2","TeO2","Ta2O5","Tl2O","WO3","Y2O3","Cs2O","Others",
]
FULL_OXIDES = list(dict.fromkeys(FULL_OXIDES))


def _rows(waste: Dict[str, float]) -> np.ndarray:
    """Build contribution matrix: rows = [Waste] + GFCs, cols = FULL_OXIDES.
    Waste row: the waste's oxide mass fractions (normalized to total waste oxide;
    the ~1.2% volatile shortfall vs 1.0 is physical — H2O/halogens leave the melt).
    GFC rows: GFCS normalized to sum 1 (relative oxide split) — under the
    paper's Table 3-4 convention (fix #6, PAPER-VERIFIED), x_k IS the oxide
    fraction of glass from GFC k and the yield division happens only in the
    raw-demand recovery (x_k / y_k).  Proof: Batch 3 reproduces Table 3-5 to
    ≤0.3% on every major oxide (B2O3 0.2200, ZnO 0.0400, Na2O 0.1413, Li2O
    0.0138); the previous raw-yield rows double-counted the yield loss."""
    w = {k: v for k, v in waste.items()}
    s = sum(w.values())
    wn = np.array([w.get(o, 0.)/s for o in FULL_OXIDES])
    G = []
    for gname in GFC_NAMES:
        gfc = GFCS[gname]
        sg = sum(gfc.values())
        G.append([gfc.get(o, 0.0)/sg if sg else 0.0 for o in FULL_OXIDES])
    return np.vstack([wn, np.array(G)])


def evaluate_mix(waste: Dict[str, float], x: np.ndarray):
    """x: oxide mass fractions (sum=1) of [waste, GFC1..N] in the final glass.
    NO defensive renormalization — the ~1.2% glass-sum shortfall vs 1.0 is the
    waste's volatile fraction (H2O/halogens leave the melt) and is physical."""
    M = _rows(waste)
    g = x @ M
    tot = g.sum()
    g = g / tot
    return dict(zip(FULL_OXIDES, g)), tot - 1.0  # volatile-loss closure term


def formulate(waste: Dict[str, float], allow_v2o5: Optional[bool] = None,
              allow_cr2o3: bool = True, confidence: float = 0.90,
              ucomp: Optional[Dict[str, float]] = None,
              verbose: bool = False) -> Dict:
    """Maximize waste loading (the Waste row's oxide fraction, x[0]) subject to
    the EWG3.0 (PNNL-38953) Table 3.1 constraint set on the per-model bases.

    Margins are the same smooth quantities P.evaluate applies (t(P) ±
    (Upred + Ucomp) inside the limits).  GFC rules (§3.4 / fact 6):
      - V2O5 GFC only allowed when pre-retention gSO3 >= 0.7 wt%
        (auto-decided when allow_v2o5 is None),
      - Cr2O3 GFC => final-glass Cr2O3 <= 0.6 wt%.
    """
    waste = {k: v for k, v in waste.items() if v}
    n = 1 + len(GFC_NAMES)
    names = ["Waste"] + GFC_NAMES
    M = _rows(waste)

    # V2O5 gate (§3.4): allowed only when the pre-retention glass gSO3 would be
    # >= 0.7 wt%; decided after a first pass with V2O5 disabled (see below).
    gate_pending = allow_v2o5 is None
    if allow_v2o5 is None:
        allow_v2o5 = False

    def glass_of(x):
        g = x @ M
        s = g.sum()
        return (g / s if s > 0 else g)

    def ev_of(x):
        g = dict(zip(FULL_OXIDES, glass_of(x)))
        return P.evaluate(g, confidence=confidence, ucomp=ucomp)

    # PERF (hang fix, 2026-11-12): every one of the 24 constraint closures
    # called ev_of() independently, so each solver point triggered up to 24
    # full property-stack evaluations (plus ~10 more inside every SLSQP
    # numeric constraint Jacobian) even though each closure uses exactly one
    # margin.  Measured on 135.120.100 whole-farm: 269k evaluate() calls per
    # campaign, ~8-640 s per campaign — the app's evaluate loop presented as
    # a multi-minute "hang" (worst at campaign 27 of 109).  Memoize on the
    # exact x vector: evaluate() is a pure function of it, so every closure
    # and every finite-difference column for the same x now shares one
    # evaluation.  Bit-identical results (same floats in, same out; verified
    # vs a pre-fix run on campaign 27).
    _ev_cache: Dict[bytes, Any] = {}

    def ev_of_shared(x):
        key = x.tobytes()
        hit = _ev_cache.get(key)
        if hit is None:
            hit = ev_of(x)
            _ev_cache[key] = hit
        return hit

    # smooth SLSQP margins (all pass as >= 0).  Mirrors P.evaluate Eq 3.6:
    # t(P) ± (Upred + Ucomp) bound INSIDE the published limits.
    def cfun(idx):
        uc = [
            ("pct_hi",   None),
            ("ccr",      None),
            ("ccd",      None),
            ("cv",       None),
            ("eta1150_lo", None),
            ("eta1150_up", None),
            ("eta1100_up", None),
            ("ec1100_lo", None),
            ("ec1200_up", None),
            ("so3_mt",  None),
            ("kneck",   None),
            ("tl_p",    None),
            ("tl_zr",   None),
            ("c950",    None),
            ("np_p",    None),
            ("nnali",   None),
            ("nalk_lo", None), ("nalk_hi", None),
            ("nsial_lo", None), ("nsial_hi", None),
            ("nsibi_lo", None), ("nsibi_hi", None),
            ("thzr",    None),
            ("f_br",    None),
        ]
        name = uc[idx][0]

        def f(x):
            ev = ev_of_shared(x)
            u = ev.upred or {}
            ln = math.log
            log10 = math.log10
            if name == "pct_hi":
                return (P.PCT_LIMIT_G_L *
                        math.exp(-(u.get("pct", 0.) + _uc(ucomp, "pct")))) - math.exp(ev.ave_ln_nl)
            if name == "ccr":
                return 4.95 - ev._tclp_raw["Cr"] * math.exp(u.get("tclp", 0.))
            if name == "ccd":
                return 0.48 - ev._tclp_raw["Cd"] * math.exp(u.get("tclp", 0.))
            if name == "cv":
                return 16.9 - ev._tclp_raw["V"] * math.exp(u.get("tclp", 0.))
            if name == "eta1150_lo":
                return (log10(ev.eta1150) - u.get("eta1150_ln", 0.) - _uc(ucomp, "eta1150")
                        - log10(P.ETA1150_RANGE[0]))
            if name == "eta1150_up":
                return log10(P.ETA1150_RANGE[1]) - (log10(ev.eta1150) +
                        u.get("eta1150_ln", 0.) + _uc(ucomp, "eta1150"))
            if name == "eta1100_up":
                return log10(P.ETA1100_MAX) - (log10(ev.eta1100) +
                        u.get("eta1100_ln", 0.) + _uc(ucomp, "eta1100"))
            if name == "ec1100_lo":
                return (log10(ev.ec1100) - u.get("ec1100_ln", 0.) - _uc(ucomp, "ec1100")
                        - log10(P.EC1100_MIN))
            if name == "ec1200_up":
                return log10(P.EC1200_MAX) - (log10(ev.ec1200) +
                        u.get("ec1200_ln", 0.) + _uc(ucomp, "ec1200"))
            if name == "so3_mt":
                gs_wt = 100.0 * ev.gSO3_br
                return (ev.wso3_3ts - P.SO3_MT_OFFSET - u.get("wso3", 0.) -
                        _uc(ucomp, "wso3")) - gs_wt
            if name == "kneck":
                return math.log(P.KNECK_LIMIT_IN) - (ev.ln_k1208 + u.get("k1208_ln", 0.)
                                                     + _uc(ucomp, "kneck"))
            if name == "tl_p":
                if ev.g.get("P2O5", 0.) < P.TL_P_GATE:
                    return 1.0   # not gated -> inactive
                return P.TL_LIMIT_C - (ev.tl_p + u.get("tl_p", 0.) + _uc(ucomp, "tl_p"))
            if name == "tl_zr":
                if ev.g.get("ZrO2", 0.) < P.TL_ZR_GATE:
                    return 1.0
                return P.TL_LIMIT_C - (ev.tl_zr + u.get("tl_zr", 0.) + _uc(ucomp, "tl_zr"))
            if name == "c950":
                return P.C950_MAX - (ev.c950 + u.get("c950", 0.) + _uc(ucomp, "c950"))
            if name == "np_p":
                return ev.np_p - _uc(ucomp, "np_p") - P.NPH_P_MIN
            if name == "nnali":
                return ev.NNaLi - P.IMMIN_MIN
            if name == "nalk_lo":
                return ev.NALK - P.NALK_RANGE[0]
            if name == "nalk_hi":
                return P.NALK_RANGE[1] - ev.NALK
            if name == "nsial_lo":
                return ev.NSiAl - P.NSIAL_RANGE[0]
            if name == "nsial_hi":
                return P.NSIAL_RANGE[1] - ev.NSiAl
            if name == "nsibi_lo":
                return ev.NSiBi - P.NSIBI_RANGE[0]
            if name == "nsibi_hi":
                return P.NSIBI_RANGE[1] - ev.NSiBi
            if name == "thzr":
                return P.THO2_ZRO2_MAX - (ev.g.get("ThO2", 0.) + ev.g.get("ZrO2", 0.))
            if name == "f_br":
                return P.F_BR_MAX - ev.gF_br
            raise KeyError(name)
        return f

    # MV bounds on each modeled component (Table 3.2 Overall, AR mass basis)
    mv_idx = [i for i, o in enumerate(FULL_OXIDES) if o in P.MV or o == "RE2O3"]

    def _mv_vec(x):
        return glass_of(x)

    def c_mv(i, which):
        o = FULL_OXIDES[i]
        lo, hi = P.MV.get(o, (0.0, 0.0289)) if o != "RE2O3" else P.MV.get("LN2O3", (0.0, 0.0289))
        if which == "lo":
            return lambda x: _mv_vec(x)[i] - lo
        return lambda x: hi - _mv_vec(x)[i]

    # ------------------------- constraint set -------------------------
    # Tensor backend (default): ONE vectorized ineq constraint covering the
    # same 24 margins + MV bounds, with the ANALYTIC Jacobian computed by
    # forward-mode AD over the oxide basis (ewg/tensor_backend.py).  This
    # removes (a) the per-closure fan-out and (b) scipy's finite-difference
    # Jacobian, which together cost ~(n+1) full evaluate() calls per SLSQP
    # iterate (~270k evaluate() calls per campaign measured 2026-11-12).
    # Margins are verified test-equal to the closure path (see tests.py);
    # set EWG_SOLVER_TENSOR=0 to fall back to the legacy closures.
    me = None
    if os.environ.get("EWG_SOLVER_TENSOR", "1") != "0":
        try:
            me = TB.MarginEval(M, confidence=confidence, ucomp=ucomp)
            constraints = [
                {"type": "eq", "fun": lambda x: x.sum() - 1.0,
                 "jac": lambda x: np.ones(len(x))},
                {"type": "ineq", "fun": me.margins, "jac": me.jac},
            ]
        except Exception:
            if verbose:
                print("  [optimize] tensor backend unavailable; legacy path")
            me = None
    if me is None:
        constraints = [{"type": "eq", "fun": lambda x: x.sum() - 1.0}]
        for i in range(24):
            constraints.append({"type": "ineq", "fun": cfun(i)})
        for i in mv_idx:
            constraints.append({"type": "ineq", "fun": c_mv(i, "lo")})
            constraints.append({"type": "ineq", "fun": c_mv(i, "hi")})

    bounds = [(0.0, 1.0)] * n
    # GFC rules
    if not allow_v2o5:
        bounds[names.index("V2O5")] = (0.0, 0.0)
    if allow_cr2o3:
        # EWG3.0 §3.4: Cr2O3 GFC => final glass Cr2O3 <= 0.6 wt% (AR basis)
        bounds[names.index("Cr2O3")] = (0.0, CR2O3_MAX)
    else:
        bounds[names.index("Cr2O3")] = (0.0, 0.0)

    # Multi-start SLSQP (fix: single start at wt0=0.40 can be MV-infeasible for
    # high-Na/High-SO3 wastes — Batch17's Na2O waste 0.6154 → glass Na2O 32%
    # > 27% max, and SLSQP's linesearch dies there).  Start from a LOW-waste
    # feasible point plus the paper-typical 0.40; keep the best FEASIBLE result.
    best = None
    ladder_cands = []  # all ladder (cand) tuples, for close-out seed diversity
    for wt_start in (0.40, 0.20, 0.10, 0.05, 0.30):
        x0 = np.full(n, (1 - wt_start) / (n - 1)); x0[0] = wt_start
        res = minimize(lambda x: -x[0], x0, method="SLSQP",
                       constraints=constraints, bounds=bounds,
                       options={"maxiter": 800, "ftol": 1e-9})
        x_try = res.x
        g_try = dict(zip(FULL_OXIDES, glass_of(x_try)))
        ev_try = P.evaluate(g_try)
        feas = res.success and ev_try.all_pass
        cand = (feas, float(x_try[0]), res, g_try, ev_try)
        ladder_cands.append(cand)
        if best is None or (cand[0], cand[1]) > (best[0], best[1]):
            best = cand
        if feas and abs(x_try[0] - 0.40) < 1e-6:
            break  # first-choice start already feasible

    # Compliance close-out (2026-11-12).  Symptom measured on 135.120.100 (7
    # of 109 campaigns: 28, 29, 58, 73, 84, 99, 106): heel-heavy feeds with a
    # narrow feasible GFC simplex end NON-CONVERGED ("Iteration limit reached"
    # / linesearch failure) at an unconverged WL, then report all_pass=False.
    # A raw maxiter bump (800 -> 3000) does NOT close them — verified: SLSQP
    # stalls on linesearch failures at ~unchanged iterates for 170+ s.  The
    # fix is a two-phase close-out:
    #   Phase F (feasibility): unconstrained SLSQP descent on the total
    #     margin violation F(x) = Σ relu(−margins) over the 24 EWG3.0 margins
    #     plus the Table 3.2 MV bounds.  No equality/inequality constraint
    #     machinery, so the linesearch cannot stall against constraints.
    #   Phase W (warm maximize): SLSQP on the original problem warm-started
    #     from the phase-F point (which is feasible or near-feasible).
    # Candidates are ranked by the standard keep-best rule (feasible first,
    # then higher WL), so phase F/W can never RETURN a worse result than the
    # ladder found — they only add candidates.  Normal campaigns (the other
    # 102) converge inside the ladder and never enter the close-out.
    wl_top_all = max((float(c[2].x[0]) for c in ladder_cands), default=0.0)
    if best is not None and (not best[0] or wl_top_all > best[1] + 2e-3):
        # Close-out triggers when (a) the kept best never converged feasible,
        # or (b) an infeasible ladder iterate wandered meaningfully ABOVE the
        # feasible best — SLSQP can converge prematurely to a feasible local
        # optimum (measured: c108/c109 135.120.100 — success=True at 0.3554
        # while other iterates reached 0.36+), so the anchors must also run
        # to try raising WL toward the true boundary.  The keep-best ranking
        # below makes this safe: it can never return a lower result.
        if me is not None:
            # Tensor close-out: total violation F(x) = sum relu(-margins)
            # with its analytic gradient (active rows of J).
            def viol(x):
                m = me.margins(x)
                return float(np.maximum(-m, 0.0).sum())

            def viol_jac(x):
                m = me.margins(x)
                if (m < 0.0).any():
                    return -me.jac(x)[m < 0.0].sum(axis=0)
                return np.zeros(len(x))
        else:
            funs = [cfun(i) for i in range(24)]
            for i in mv_idx:
                funs.append(c_mv(i, "lo"))
                funs.append(c_mv(i, "hi"))

            def viol(x):
                v = 0.0
                for f in funs:
                    try:
                        m = float(f(x))
                    except (KeyError, ZeroDivisionError, FloatingPointError):
                        m = -1.0
                    if m < 0.0:
                        v += -m
                return v
            viol_jac = None

        # Phase F': WL-anchored feasibility — pin the waste fraction at
        # descending anchors and minimize margin violation.  The first
        # anchor with F = 0 is (up to the anchor grid) the maximum feasible
        # WL; a free-WL feasibility descent would instead slide to a
        # trivially-feasible near-zero WL (measured: c29 -> 0.0276).
        wl_top = max(float(best[2].x[0]), 1e-6) if not best[0] else max(
            float(best[2].x[0]),
            max((float(c[2].x[0]) for c in ladder_cands if not c[0]), default=0.0),
            1e-6)

        def x_at(anchor_wl):
            assert best is not None  # guarded at block entry (pyright)
            x0 = np.array(best[2].x, dtype=float)
            cur = float(1.0 - x0[0])
            if cur > 1e-12:
                x0[1:] = x0[1:] * ((1.0 - anchor_wl) / cur)
            x0[0] = anchor_wl
            return x0

        n_rows_gfc = int(best[2].x.shape[0])  # decision-variable count for seeds

        # ladder iterates for seed diversity (keep in scope; the close-out
        # anchors are seeded from these)
        ladder_res = [cand[2] for cand in ladder_cands if cand is not None]

        x_seed = None  # best feasible close-out point found
        for scale in (0.995, 0.99, 0.985, 0.98, 0.975, 0.95, 0.90, 0.80, 0.65, 0.45):
            anchor = min(wl_top * scale, wl_top)
            kw = {} if viol_jac is None else {"jac": viol_jac}
            ac = [{"type": "eq", "fun": lambda x: x[0] - anchor,
                   "jac": lambda x: np.array([1.0] + [0.0] * (len(x) - 1))}]
            def _anchor_run(seed):
                return minimize(viol, seed, method="SLSQP", bounds=bounds,
                                constraints=ac,
                                options={"maxiter": 800, "ftol": 1e-10}, **kw)
            # Seed strategy, most-to-least informed (all deterministic):
            # 1) highest-WL ladder iterate rescaled to the anchor (original)
            # 2) ladder iterate CLOSEST to feasibility (least viol) rescaled
            # 3) clean uniform GFC split at the anchor
            ra = _anchor_run(x_at(anchor))
            g_a = dict(zip(FULL_OXIDES, glass_of(ra.x)))
            ev_a = P.evaluate(g_a, confidence=confidence, ucomp=ucomp)
            feas_a = ev_a.all_pass and viol(ra.x) <= 1e-9
            anchor_wl = anchor
            if not feas_a:
                near = min(ladder_res, key=lambda rr: viol(rr.x))
                x_near = np.array(near.x, dtype=float)
                cur = float(1.0 - x_near[0])
                if cur > 1e-12:
                    x_near[1:] = x_near[1:] * ((1.0 - anchor) / cur)
                x_near[0] = anchor
                rn = _anchor_run(x_near)
                g_n = dict(zip(FULL_OXIDES, glass_of(rn.x)))
                ev_n = P.evaluate(g_n, confidence=confidence, ucomp=ucomp)
                feas_n = ev_n.all_pass and viol(rn.x) <= 1e-9
                if feas_n:
                    ra, g_a, ev_a, feas_a = rn, g_n, ev_n, feas_n
            if not feas_a:
                # Seed sensitivity guard: anchored descent from the (often
                # grossly infeasible) ladder iterate can stall far worse than
                # the same anchor reached from a clean uniform GFC split
                # (observed: c58 seed viol 0.37 vs clean-seed viol 0 in 28
                # iters).  One deterministic clean-seed retry per anchor.
                xc_clean = np.full(n_rows_gfc, (1.0 - anchor) / (n_rows_gfc - 1))
                xc_clean[0] = anchor
                rc = _anchor_run(xc_clean)
                g_c = dict(zip(FULL_OXIDES, glass_of(rc.x)))
                ev_c = P.evaluate(g_c, confidence=confidence, ucomp=ucomp)
                feas_c = ev_c.all_pass and viol(rc.x) <= 1e-9
                if feas_c:
                    ra, g_a, ev_a, feas_a = rc, g_c, ev_c, feas_c
            cand_a = (feas_a, anchor_wl, ra, g_a, ev_a)
            if (cand_a[0], cand_a[1]) > (best[0], best[1]):
                best = cand_a
            if feas_a:
                x_seed = ra.x
                break  # highest feasible anchor reached -> reclaim WL below
        if x_seed is None:
            # fallback: free feasibility descent from the best iterate
            kw = {} if viol_jac is None else {"jac": viol_jac}
            rf = minimize(viol, best[2].x, method="SLSQP", bounds=bounds,
                          options={"maxiter": 2000, "ftol": 1e-10}, **kw)
            g_f = dict(zip(FULL_OXIDES, glass_of(rf.x)))
            ev_f = P.evaluate(g_f, confidence=confidence, ucomp=ucomp)
            feas_f = ev_f.all_pass and viol(rf.x) <= 1e-9
            cand_f = (feas_f, float(rf.x[0]), rf, g_f, ev_f)
            if (cand_f[0], cand_f[1]) > (best[0], best[1]):
                best = cand_f
            if feas_f:
                x_seed = rf.x
        if x_seed is not None:
            # Phase W: reclaim the WL between the feasible seed and the true
            # boundary with the original constrained maximization.
            res2 = minimize(lambda x: -x[0], x_seed, method="SLSQP",
                            constraints=constraints, bounds=bounds,
                            options={"maxiter": 800, "ftol": 1e-9})
            g2 = dict(zip(FULL_OXIDES, glass_of(res2.x)))
            ev2 = P.evaluate(g2)
            feas2 = res2.success and ev2.all_pass
            cand2 = (feas2, float(res2.x[0]), res2, g2, ev2)
            if (cand2[0], cand2[1]) > (best[0], best[1]):
                best = cand2
    feas, wl, res, gfinal, ev = best
    x = res.x

    # V2O5 gate (§3.4): pre-retention glass gSO3 >= 0.7 wt% -> re-solve allowing
    # the V2O5 GFC; keep the better (feasible, higher-WL) formulation.
    if gate_pending and allow_v2o5 is False:
        raw = x @ M
        s_raw = raw.sum()
        if s_raw > 0 and FULL_OXIDES.index("SO3") < len(raw):
            gso3_pre_wt = 100.0 * raw[FULL_OXIDES.index("SO3")] / s_raw
            if gso3_pre_wt >= 0.7:
                try:
                    r2 = formulate(waste, allow_v2o5=True, allow_cr2o3=allow_cr2o3,
                                   confidence=confidence, ucomp=ucomp, verbose=verbose)
                    if (r2.get("success") and r2["waste_loading"] > wl) or r2["waste_loading"] > wl:
                        return r2
                except Exception:
                    pass

    # Raw GFC mass fractions: x_k is the oxide fraction of glass from GFC k;
    # raw GFC demand per unit glass = x_k / y_k (y_k = oxide yield per raw mass).
    gfcs_used = {}
    for i in range(1, n):
        y_sum = sum(GFCS[names[i]].values())   # as-fired oxide yield per raw mass
        if x[i] > 1e-9 and y_sum > 1e-9:
            gfcs_used[names[i]] = float(x[i] / y_sum)

    # Physical waste loading = waste-oxide mass / glass mass.  With the oxide-
    # fraction convention (fix #6), glass = Σ x_k e_k sums to 1 exactly (the
    # eq-constraint enforces it), so x[0] IS the physical WL — no residual
    # deflation.  Report both for audit.
    tot_glass_input = float((x @ M).sum())
    wl_physical = float(x[0]) / max(tot_glass_input, 1e-9)

    return {
        "success": bool(res.success), "message": res.message,
        "waste_loading": float(x[0]), "wl_physical": wl_physical,
        "glass_input_total": tot_glass_input,
        "x": dict(zip(names, map(float, x))),
        "glass": gfinal, "gfc_raw_mass_fraction": gfcs_used,
        "evaluation": ev,
    }
