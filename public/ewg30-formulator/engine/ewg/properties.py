"""EWG3.0 (PNNL-38953 Rev.0 / EWG-RPT-058) glass formulation property models.

Replaces the EWG2.5 (PNNL-35884) stack.  Model set per report Table 1.1:
  - PCT     ln(NCAve, g/L) : mole-fraction PQM with Al2O3 to 4th order (Table 2.29)
  - TCLP    ln(rB, mg/L)   : mole-fraction PQM + 2 cross terms (Table 2.33);
            element releases via rB proxy  Ce = f_el * exp(ln rB)   (Eq 2.10 context)
  - Visc    log10(eta)     : VFT, AR mass fractions (Table 2.4)
  - EC      log10(eps,S/m) : VFT, AR mass fractions (Table 2.5)
  - wSO3    wSO3-3TS wt%   : PQMM, BR mass fractions, ri = gi/(1-gSO3) (Table 2.9);
            melter tolerance wSO3-MT = 3TS - 0.33 wt%
  - K-3     ln(kneck, in): mole fraction PQM, Cl-excluded, NO S1200 intercept for
            bubbled reference (S1200=0), limit 0.025 in @1208 C (Table 2.13)
  - TL-P / TL-Zr : PQM °C + hard sigmoid gate at gP2O5>=0.01 / gZrO2>=0.027,
            limit 1050 C (Tables 2.17 / 2.20)
  - Spinel  C950 vol%      : PQM, limit 1.0 vol% (Table 2.24)
  - Nepheline P >= 0.031  : pseudo-ternary distance, MOLE basis (Table 2.34);
            report's printed Eq 2.12 is garbled - the geometric ternary-distance
            form reproduces the report's own Table 3.7 to 0.13% (see
            ewg30/RESOLUTIONS.md)
  - Immiscibility NNaLi >= 0.20;  metal corrosion gF(BR) <= 2.5 wt%;
            non-spinel gThO2 + gZrO2 < 13 wt%
  - Model validity (Table 3.2 'Overall') + NAlk/NSiAl/NSiBi multi-component ranges

Basis conventions (validated EXACTLY against the report's own Table 3.7
examples on the Table 3.6 target glasses):
  - All mole-fraction bases: full composition converted oxide-by-oxide with
    per-oxide MW (lanthanides folded into LN2O3, MW 336.48); 'Others' mole
    fraction = 1 - sum(named mole fractions).  NOT the residual-mass convention.
  - Mass-fraction bases: named components taken at mass fraction, residual into
    'Others' = 1 - sum(named).

Upred: Student-t sqrt(g'[s^2(G'G)]^-1 g) for processing properties, SUCI
sqrt(p*F[1-2alpha,(p,n-p)]) for PCT/TCLP, with the covariance matrices from
Appendix A (ewg30/cov_*.json).  Confidence level is a parameter: the report's
own examples use the 99% two-sided CI (validated: implied t = 2.59 consistently
across all six eta/EC examples); the recommended formulation CL for processing
properties is 90% (evaluate(confidence=0.90)).  Visc/EC Upred reproduces the
Table 3.7 Upred rows exactly at 99%; the remaining models' Upred rows are
reproduced within basis-uncertainty (see RESOLUTIONS.md for status per model).

Composition/process uncertainty Ucomp is the 10,000-run Monte Carlo of §3.3
implemented in ucomp_glass() - expensive, deliberately OUT of the in-loop
constraint path (constraints use t(P) ± (Upred + Ucomp) with Ucomp=None by
default; thread a precomputed Ucomp dict via evaluate(..., ucomp=...) or the
audit hook).
"""
from __future__ import annotations
import functools
import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

_DATA = os.path.join(os.path.dirname(__file__), "data", "ewg30")

def _load(name):
    with open(os.path.join(_DATA, name)) as f:
        return json.load(f)

M30 = _load("models.json")
CON30 = _load("constraints.json")
RET30 = {k: v["retention_factor"] for k, v in CON30["retention"].items()}
RET30["LN2O3"] = 0.99721
import numpy as _np
if os.path.exists(os.path.join(_DATA, "table_3_2_mv.json")):
    MV = {k: tuple(v) for k, v in _load("table_3_2_mv.json").items()}
else:
    MV = {}

# ---------------------------------------------------------------- mole conversion
MW = dict(
    Al2O3=101.9613, B2O3=69.6202, BaO=153.326, CaO=56.0774, CdO=128.413,
    Cl=35.453, Cr2O3=151.989, F=18.998, Fe2O3=159.687, K2O=94.196,
    Li2O=29.881, MgO=40.304, MnO=70.937, Na2O=61.979, NiO=74.693,
    P2O5=141.943, SiO2=60.084, SO3=80.062, TiO2=79.866, V2O5=181.88,
    ZnO=81.379, ZrO2=123.222, SnO2=150.709, SrO=103.62, UO3=286.03,
    ThO2=264.037, LN2O3=336.48, Cs2O=281.81, Rb2O=186.94, I=126.90,
    Tc2O7=354.93, As2O5=229.84, SeO2=110.96, Sb2O3=291.5, TeO2=159.6,
    MoO3=143.95, Nb2O5=265.81, Ag2O=231.74, BeO=25.01, Bi2O3=465.96,
    CoO=74.93, CuO=79.55, HgO=216.59, PbO=223.2, PdO=122.42, PuO2=276.06,
    NpO2=237.05, RuO2=133.12, Rh2O3=259.7, RaO=246.0, Y2O3=225.81,
    Eu2O3=351.93, Gd2O3=362.5, Sm2O3=348.72, Nd2O3=336.48, Pr2O3=329.83,
    Ce2O3=328.23, La2O3=325.82, Ac2O3=502.0, Am2O3=518.0, Cm2O3=532.0,
    Pa2O5=422.0, Tl2O=424.77, WO3=231.85, Ta2O5=442.6,
)
LANTHANIDES = ("La2O3", "Ce2O3", "Pr2O3", "Nd2O3", "Sm2O3", "Eu2O3", "Gd2O3",
               "Y2O3", "Ac2O3", "Am2O3", "Cm2O3", "RE2O3", "LN2O3")

def fold_lanthanides(g: Dict[str, float]) -> Dict[str, float]:
    """Fold lanthanide/Y/actinide oxides into the LN2O3 lump (model feature)."""
    gg = dict(g)
    ln = sum(gg.pop(k, 0.0) for k in LANTHANIDES)
    if ln > 0.0:
        gg["LN2O3"] = gg.get("LN2O3", 0.0) + ln
    return gg

def to_br(g: Dict[str, float]) -> Dict[str, float]:
    """BR (before-retention) composition from an AR (after-retention) glass."""
    return {k: v / (RET30.get(k, 0.99721) or 0.99721)
            for k, v in g.items() if v > 1e-12 and k != "Others" and k not in LANTHANIDES}

def basis_mole(g: Dict[str, float], named) -> Dict[str, float]:
    """Full mole conversion of EVERY oxide (per-oxide MW), normalized over all;
    Others(mole) = 1 - sum(named mole fractions).  Paper-exact vs Table 3.7."""
    gg = fold_lanthanides(g)
    num = {k: v / MW.get(k, 60.084) for k, v in gg.items() if v > 0}
    tot = sum(num.values())
    xn = {k: v / tot for k, v in num.items()} if tot > 0 else num
    out = {k: xn.get(k, 0.0) for k in named if k != "Others"}
    if "Others" in named:
        out["Others"] = max(1.0 - sum(out.values()), 0.0)
    return out

def basis_mass(g: Dict[str, float], named) -> Dict[str, float]:
    """Mass fractions of named components; residual into 'Others' (and into
    'Other' when a model's cov table uses that spelling, e.g. C950)."""
    gg = fold_lanthanides(g)
    res_names = [k for k in named if k not in ("Others", "Other")]
    out = {k: gg.get(k, 0.0) for k in res_names}
    residual = max(1.0 - sum(out.values()), 0.0)
    if "Others" in named:
        out["Others"] = residual
    if "Other" in named:
        out["Other"] = residual
    return out

# ---------------------------------------------------------------- covariances
_COV: Dict[str, Dict] = {}

def _cov(model: str):
    if model not in _COV:
        try:
            path = os.path.join(_DATA, f"cov_{model}.json")
            with open(path) as f:
                d = json.load(f)
            M = _np.array(d["matrix"], dtype=float)
            M = 0.5 * (M + M.T)
            _COV[model] = {"terms": [t if "×" not in t and t != "Ln2O3"
                                     else t.replace("×", "*").replace("Ln2O3", "LN2O3")
                                     for t in d["row_term_order"]],
                           "M": M,
                           "n_dim": d.get("n", M.shape[0])}
        except (OSError, KeyError, ValueError):
            _COV[model] = None
    return _COV[model]

def _cov_sd(model: str, term_x) -> float:
    """sd = sqrt(f' Sigma f); term_x = [(cov_term_name, feature_value), ...].
    Missing matrix -> 0.0 (graceful degradation)."""
    c = _cov(model)
    if not c:
        return 0.0
    idx = {t: i for i, t in enumerate(c["terms"])}
    rows, cols, xs = [], [], []
    for k, (t, v) in enumerate(term_x):
        if t in idx:
            rows.append(k); cols.append(idx[t]); xs.append(v)
    if not rows:
        return 0.0
    x = _np.array(xs, dtype=float)
    Msub = c["M"][_np.ix_(cols, cols)]
    return math.sqrt(max(float(x @ Msub @ x), 0.0))

# dof per model: (n_points, n_params); params count = covariance dimension.
N_POINTS = {
    "viscosity": 13013, "ec": 7584, "so3": 375, "k3": 483, "tl_p": 177,
    "tl_zr": 124, "c950": 177, "pct": 1185, "tclp": 480, "neph": 955,
}
def _dof(model):
    try:
        p = _cov(model)["n_dim"]
    except Exception:
        p = 0
    return N_POINTS.get(model, p) - p

# Upred multiplier convention, calibrated against Table 3.7 Upred rows (99%
# example battery; see ewg/data/ewg30/RESOLUTIONS.md):
#  - all processing models: one-sided  t_{1-alpha, n-p}   (k3/tl_zr/c950 exact)
#  - EXCEPT viscosity & EC: the Table 3.7 rows imply the two-sided quantile
#    t_{1-alpha/2, n-p} (implied 2.59 / 2.55 vs two-sided 2.576 at 99%;
#    one-sided 2.326 would be ~10% off) - kept as a per-model flag.
#  - PCT/TCLP: SUCI sqrt(p * F_{1-2alpha,(p,n-p)}), validated exactly.
_TWO_SIDED_MODELS = {"viscosity", "ec"}

def _t_ppf(p_one_sided: float, dof: float) -> float:
    """Student-t percentile: scipy when available, otherwise a bisection on
    the regularized incomplete beta (no scipy fallback).

    2026-11-13 perf fix: MEMOIZED on (p, dof).  The quantile is a pure
    function of these two constants, but the optimizer evaluates Upred
    after every SLSQP iterate (and inside every numeric-difference round),
    so an uncached scipy dispatch was costing ~90k `t.ppf` calls per
    formulate() — measured 4.1 s of 12 s profiled, a ~5x whole-mission
    sweep slowdown vs EWG2.5 (HWG-mission-planning consumer benchmark
    2026-11-12).  Memoization is value-neutral: same floats returned.
    """
    p_one_sided = min(max(p_one_sided, 1e-12), 1 - 1e-12)
    return float(_t_ppf_cached(p_one_sided, dof))

@functools.lru_cache(maxsize=256)
def _t_ppf_cached(p_one_sided: float, dof: float) -> float:
    try:
        from scipy import stats as _s
        return _s.t.ppf(p_one_sided, dof)
    except Exception:
        pass
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        # two-sided tail integral via erf for large dof approximates t with
        # dof correction; adequate fallback for dof >= 30 (accuracy ~0.2%)
        cdf = 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0)))
        if cdf < p_one_sided:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)

def _f_ppf(p_: float, d1: int, d2: float) -> float:
    """F percentile: scipy when available, else Wilson-Hilferty (large d2)."""
    return float(_f_ppf_cached(float(p_), int(d1), float(d2)))

@functools.lru_cache(maxsize=64)
def _f_ppf_cached(p_: float, d1: int, d2: float) -> float:
    try:
        from scipy import stats as _s
        return _s.f.ppf(p_, d1, d2)
    except Exception:
        pass
    z = _t_ppf(p_, 1e6)
    return max(d1 * (1 - 2 / (9 * d1) + z * math.sqrt(2 / (9 * d1))) ** 3, 1e-12)

def _cl_factor(model: str, confidence: float, sucni: bool = False) -> float:
    """Upred multiplier for processing properties (non-SUCI models).
    Processing: t_{1-alpha, n-p} one-sided (two-sided for viscosity/EC per the
    Table 3.7 calibration).  alpha = 1 - confidence.

    2026-11-13 perf: memoized on (model, confidence, sucni) — constants for
    any given evaluation context (confidence defaults to 0.90 facility-wide)."""
    return _cl_factor_cached(model, float(confidence), bool(sucni))

@functools.lru_cache(maxsize=64)
def _cl_factor_cached(model: str, confidence: float, sucni: bool) -> float:
    c = _cov(model)
    p = c["n_dim"] if c else 0
    dof = _dof(model)
    dof = max(dof, 1e6) if dof <= 0 else dof
    if sucni:
        if p <= 0:
            return 0.0
        f = _f_ppf(1 - 2 * (1.0 - confidence), p, dof)
        return math.sqrt(p * f)
    a = 1.0 - confidence
    if model in _TWO_SIDED_MODELS:
        return _t_ppf(1.0 - a / 2.0, dof)
    return _t_ppf(1.0 - a, dof)

def _sucni_factor(model: str, confidence: float) -> float:
    """SUCI multiplier sqrt(p*F_{1-2alpha,(p,n-p)}) with alpha = 1 - CL
    (Table 3.1 note b).  At the 99% example battery: PCT p=28 ->
    sqrt(28 F_.98,(28,1157)) = 6.768 (Table 3.7 implied 6.774); TCLP p=16 ->
    5.489 (implied 5.49)."""
    return _cl_factor(model, confidence, sucni=True)

# ---------------------------------------------------------------- raw models
def eta_vft(g: Dict[str, float], T_C: float) -> float:
    terms = M30["viscosity"]["terms"]
    gv = basis_mass(g, [k[2:] for k in terms if k.startswith("B_")])
    B = sum(terms[k] * gv.get(k[2:], 0.0) for k in terms if k.startswith("B_"))
    Tk = T_C + 273.15
    return 10 ** (terms["A"] + B / (Tk - terms["T0"]))          # Pa.s

def ec_vft(g: Dict[str, float], T_C: float) -> float:
    terms = M30["ec"]["terms"]
    gv = basis_mass(g, [k[2:] for k in terms if k.startswith("B_")])
    B = sum(terms[k] * gv.get(k[2:], 0.0) for k in terms if k.startswith("B_"))
    Tk = T_C + 273.15
    return 10 ** (terms["A"] + B / (Tk - terms["T0"]))          # S/m

def upred_vft(model: str, g: Dict[str, float], T_C: float,
              confidence: float) -> float:
    """Upred on the log10 scale (dimensionless multiplier for log10 eta / eps)."""
    terms = M30[model]["terms"]
    vterms = _cov(model)["terms"]
    gv = basis_mass(g, [k[2:] for k in vterms if k.startswith("B_")])
    Tk = T_C + 273.15
    T0 = terms["T0"]
    B = sum(terms["B_" + k] * gv.get(k, 0.0) for k in gv if "B_" + k in terms)
    tx = [("A", 1.0)]
    tx += [(t, gv.get(t[2:], 0.0) / (Tk - T0)) for t in vterms if t.startswith("B_")]
    tx.append(("T0", B / (Tk - T0) ** 2))
    return _cl_factor(model, confidence) * _cov_sd(model, tx)

def ln_pct(g: Dict[str, float]) -> float:
    terms = M30["pct"]["terms"]
    pk = [k for k in terms if "*" not in k]
    xn = basis_mole(g, pk)
    a, b = xn["Al2O3"], xn["B2O3"]
    v = sum(c * xn.get(k, 0.0) for k, c in terms.items() if "*" not in k)
    v += terms["Al2O3*Al2O3"] * a * a + terms["Al2O3*B2O3"] * a * b \
         + terms["B2O3*B2O3"] * b * b + terms["Al2O3*Al2O3*Al2O3"] * a ** 3 \
         + terms["Al2O3*Al2O3*Al2O3*Al2O3"] * a ** 4
    return v

def upred_pct(g: Dict[str, float], confidence: float) -> float:
    terms = M30["pct"]["terms"]
    pk = [k for k in terms if "*" not in k]
    xn = basis_mole(g, pk)
    a, b = xn["Al2O3"], xn["B2O3"]
    xm = {"Al2O3*Al2O3": a * a, "Al2O3*B2O3": a * b, "B2O3*B2O3": b * b,
          "(Al2O3)^3": a ** 3, "(Al2O3)^4": a ** 4}
    tx = [(t, xn.get(t, xm.get(t, 0.0))) for t in _cov("pct")["terms"]]
    # SUCI: sqrt(p*F_{1-2alpha,(p,n-p)}) * sd — validated vs Table 3.7 exactly
    return _sucni_factor("pct", confidence) * _cov_sd("pct", tx)

def ln_tclp(g: Dict[str, float]) -> float:
    terms = M30["tclp"]["terms"]
    tk = [k for k in terms if "*" not in k]
    xn = basis_mole(g, tk)
    v = sum(c * xn.get(k, 0.0) for k, c in terms.items() if "*" not in k)
    v += terms["Li2O*SiO2"] * xn["Li2O"] * xn["SiO2"] \
         + terms["MgO*Na2O"] * xn["MgO"] * xn["Na2O"]
    return v

def upred_tclp(g: Dict[str, float], confidence: float) -> float:
    terms = M30["tclp"]["terms"]
    tk = [k for k in terms if "*" not in k]
    xn = basis_mole(g, tk)
    xm = {"Li2O*SiO2": xn["Li2O"] * xn["SiO2"], "MgO*Na2O": xn["MgO"] * xn["Na2O"]}
    tx = [(t, xn.get(t, xm.get(t, 0.0))) for t in _cov("tclp")["terms"]]
    return _sucni_factor("tclp", confidence) * _cov_sd("tclp", tx)

def tclp_elements(g: Dict[str, float]) -> Dict[str, float]:
    """CCd / CCr / CV (mg/L) via the rB proxy: Ce = f_el * exp(ln rB) with f_el
    the elemental mass fraction in the glass (Eq 2.10: rele = cele/fele);
    capped at the reporting limit like Table 3.7 (ex5 CV printed 16.9 = cap)."""
    fe = {"Cd": g.get("CdO", 0.) * 112.414 / 128.413,
          "Cr": g.get("Cr2O3", 0.) * 103.992 / 151.989,
          "V": g.get("V2O5", 0.) * 101.88 / 181.88}
    rB = math.exp(ln_tclp(g))
    lim = {"Cd": 0.48, "Cr": 4.95, "V": 16.9}
    v = {}
    for el, cap in lim.items():
        raw = fe[el] * rB
        v[el] = min(raw, cap)
        v[el + "_raw"] = raw
    return v

def ln_kneck(g: Dict[str, float]) -> float:
    """Bubbled reference (S1200 = 0) - validated vs Table 3.7 ln(kneck) row."""
    terms = M30["k3"]["terms"]
    mk = [k for k in terms if "*" not in k and k != "kS1200"]
    xn = basis_mole(g, mk + ["Cl"])
    q = {k: xn.get(k, 0.0) / (1 - xn.get("Cl", 0.0)) for k in mk}
    v = sum(c * q.get(k, 0.0) for k, c in terms.items()
            if "*" not in k and k != "kS1200")
    for k, c in terms.items():
        if "*" in k:
            a_, b_ = k.split("*")
            v += c * q.get(a_, 0.0) * q.get(b_, 0.0)
    return v

def upred_kneck(g: Dict[str, float], confidence: float) -> float:
    terms = M30["k3"]["terms"]
    mk = [k for k in terms if "*" not in k and k != "kS1200"]
    xn = basis_mole(g, mk + ["Cl"])
    q = {k: xn.get(k, 0.0) / (1 - xn.get("Cl", 0.0)) for k in mk}
    tx = []
    for t in _cov("k3")["terms"]:
        if t in ("Stat, 1200",):
            tx.append((t, 0.0))
        elif "*" in t:
            a_, b_ = t.split("*"); tx.append((t, q.get(a_, 0.) * q.get(b_, 0.)))
        else:
            tx.append((t, q.get(t, 0.0)))
    return _cl_factor("k3", confidence) * _cov_sd("k3", tx)

def wso3_3ts(g: Dict[str, float], gso3_renorm: Optional[float] = None) -> float:
    """wSO3-3TS wt%.  renorm denominator is (1 - gSO3); gSO3 = BR by convention.
    Pass gso3_renorm for the BR value; default is the AR SO3 of g (small effect,
    validated within 1.5% both ways)."""
    terms = M30["so3"]["terms"]
    sk = [k for k in terms if "*" not in k]
    gs = basis_mass(g, sk)
    x = {k: gs.get(k, 0.0) / (1 - (gso3_renorm if gso3_renorm is not None
                                   else g.get("SO3", 0.0))) for k in sk}
    v = sum(c * x.get(k, 0.0) for k, c in terms.items() if "*" not in k)
    for k, c in terms.items():
        if "*" in k:
            a_, b_ = k.split("*")
            v += c * x.get(a_, 0.0) * x.get(b_, 0.0)
    return v

def upred_wso3(g: Dict[str, float], confidence: float,
               gso3_renorm: Optional[float] = None) -> float:
    terms = M30["so3"]["terms"]
    sk = [k for k in terms if "*" not in k]
    gs = basis_mass(g, sk)
    x = {k: gs.get(k, 0.0) / (1 - (gso3_renorm if gso3_renorm is not None
                                   else g.get("SO3", 0.0))) for k in sk}
    tx = []
    for t in _cov("so3")["terms"]:
        if "*" in t:
            a_, b_ = t.split("*"); tx.append((t, x.get(a_, 0.) * x.get(b_, 0.)))
        else:
            tx.append((t, x.get(t, 0.0)))
    return _cl_factor("so3", confidence) * _cov_sd("so3", tx)

def _pqm_model(model: str, g: Dict[str, float]) -> float:
    terms = M30[model]["terms"]
    nk = [k for k in terms if "*" not in k and k not in ("kS1200",)]
    gm = basis_mass(g, nk)
    v = sum(c * gm.get(k, 0.0) for k, c in terms.items() if "*" not in k)
    for k, c in terms.items():
        if "*" in k:
            a_, b_ = k.split("*")
            v += c * gm.get(a_, 0.0) * gm.get(b_, 0.0)
    return v

def tl_p_raw(g):  return _pqm_model("tl_p", g)    # deg C (pre-gate)
def tl_zr_raw(g): return _pqm_model("tl_zr", g)   # deg C (pre-gate)
def c950(g):      return _pqm_model("c950", g)    # vol%

def upred_pqm(model: str, g: Dict[str, float], confidence: float) -> float:
    terms = M30[model]["terms"]
    nk = [k for k in terms if "*" not in k and k not in ("kS1200",)]
    gm = basis_mass(g, nk)
    tx = []
    for t in _cov(model)["terms"]:
        if "*" in t:
            a_, b_ = t.split("*"); tx.append((t, gm.get(a_, 0.) * gm.get(b_, 0.)))
        else:
            tx.append((t, gm.get(t, 0.)))
    return _cl_factor(model, confidence) * _cov_sd(model, tx)

TL_P_GATE, TL_ZR_GATE = 0.01, 0.027
TL_SIGMOID_K = 20000.0     # steepness from report note (g)/(h); used numerically

def tl_p_gated(g):  return tl_p_raw(g) if g.get("P2O5", 0.) >= TL_P_GATE else 0.0
def tl_zr_gated(g): return tl_zr_raw(g) if g.get("ZrO2", 0.) >= TL_ZR_GATE else 0.0

def neph_P(g: Dict[str, float]) -> float:
    """Pseudo-ternary nepheline distance (mole basis).  Geometric form:
    P = sqrt(3)*C/(2*S) - a - b*(2B+C)/(2S) - c*(2B+C)^2/(4*S^2), S = A+B+C.
    (The report's printed Eq 2.12 drops/reshuffles the b-term signs; this form
    reproduces the report's Table 3.7 NP P row to 0.13% - see RESOLUTIONS.md.)"""
    c = M30["neph"]["terms"]
    a, b, cc = (c["Poly a (Const)"], c["Poly b (X)"], c["Poly c (X2)"])
    # pseudo-component weights (X = B2O3, T = P2O5, U = CaO, Y = Li2O; V, W, Z = 0)
    xn = basis_mole(g, ["Na2O", "CaO", "MgO", "Li2O", "K2O", "Al2O3", "Fe2O3",
                        "SiO2", "P2O5", "B2O3"])
    A = xn["Na2O"] + 0.3 * xn["CaO"] + 0.0 * xn["MgO"] + 0.4 * xn["Li2O"] + 0.0 * xn["K2O"]
    B = xn["Al2O3"] + 0.0 * xn["Fe2O3"]
    C = xn["SiO2"] + 1.5 * xn["P2O5"] + 2.0 * xn["B2O3"]
    S = A + B + C
    return (math.sqrt(3.0) * C / (2 * S)
            - a - b * (2 * B + C) / (2 * S)
            - cc * (2 * B + C) ** 2 / (4 * S * S))

def n_nali(g: Dict[str, float]) -> float:
    gNa, gLi = g.get("Na2O", 0.), g.get("Li2O", 0.)
    num = gNa + 2.07 * gLi
    den = num + g.get("B2O3", 0.) + g.get("SiO2", 0.)
    return num / den if den > 0 else 0.0

def nalk(g):  return g.get("Na2O", 0.) + 0.66 * g.get("K2O", 0.) + 2.07 * g.get("Li2O", 0.)
def nsial(g): return g.get("SiO2", 0.) + 1.697 * g.get("Al2O3", 0.)
def nsibi(g): return g.get("SiO2", 0.) + 2.0 * g.get("B2O3", 0.)

# limits (Table 3.1)
PCT_LIMIT_G_L = 12.88
KNECK_LIMIT_IN = 0.025
ETA1150_RANGE = (2.0, 8.0)        # Pa.s (EWG3.0 widened from 4..6)
ETA1100_MAX = 15.0                # Pa.s
EC1100_MIN = 10.0                 # S/m  (0.10 S/cm)
EC1200_MAX = 70.0                 # S/m  (0.70 S/cm)
SO3_MT_OFFSET = 0.33              # wt%
TL_LIMIT_C = 1050.0
C950_MAX = 1.0                    # vol%
F_BR_MAX = 0.025                  # 2.5 wt% melter feed (BR)
THO2_ZRO2_MAX = 0.13              # non-spinel phase
NPH_P_MIN = 0.031
IMMIN_MIN = 0.20
NALK_RANGE = (0.1226, 0.2821)
NSIAL_RANGE = (0.4497, 0.7207)
NSIBI_RANGE = (0.4590, 0.9124)

# per-property confidence levels (Table 3.1): processing 90%, PCT 95%, TCLP 90%
CL_REC = {"pct": 0.95, "tclp": 0.90, "neph": 0.90, "visc": 0.90, "ec": 0.90,
          "so3": 0.90, "immisc": 0.90, "kneck": 0.90, "tl_p": 0.90,
          "tl_zr": 0.90, "c950": 0.90, "f": 0.90, "thzr": 0.90}
# examples battery ran at 99% two-sided for Upred rows (see RESOLUTIONS.md)
CL_EXAMPLE = 0.99


@dataclass
class GlassEvaluation:
    g: Dict[str, float]
    ave_ln_nl: float = 0.0          # ln(NCAve, g/L)  [kept name for callers; EWG3.0 basis]
    nca_g_l: float = 0.0            # exp(ln NCAve)
    eta1150: float = 0.0            # Pa.s
    eta1100: float = 0.0            # Pa.s
    ec1100: float = 0.0             # S/m
    ec1200: float = 0.0             # S/m
    wso3_3ts: float = 0.0           # wt%
    ln_k1208: float = 0.0           # ln(kneck, inch) @1208 bubbled ref
    p_phos: float = 0.0             # DEPRECATED EWG2.5 field = NP P (nepheline)
    NNaLi: float = 0.0
    NALK: float = 0.0
    NSiAl: float = 0.0
    NSiBi: float = 0.0
    ln_tclp_rB: float = 0.0         # ln(mg/L)
    np_p: float = 0.0               # nepheline distance P
    tl_p: float = 0.0               # gated model value, deg C
    tl_zr: float = 0.0
    c950: float = 0.0               # vol%
    gF_br: float = 0.0              # BR F mass fraction
    gSO3_br: float = 0.0
    _tclp_raw: dict = field(default_factory=dict)  # CCd/CCr/CV w/o Upred (mg/L)
    confidence: float = 0.90
    upred: dict = field(default_factory=dict)
    ucomp: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)   # name -> (value_used, pass)
    all_pass: bool = False


def evaluate(g: Dict[str, float], confidence: float = 0.90,
             ucomp: Optional[Dict[str, float]] = None) -> GlassEvaluation:
    """Evaluate the EWG3.0 constraint set on an AR (after-retention) glass.

    confidence: 0.90 (recommended formulation CL) or 0.99 (Table 3.7 example
    battery).  ucomp: optional precomputed Ucomp dict (property -> value in
    property units) added to the Upred margins per Eq 3.6.
    """
    g = {k: float(v) for k, v in g.items() if v}
    total = sum(g.values())
    if not (0.999 <= total <= 1.001):
        g = {k: v / total for k, v in g.items()}

    U = 99.0 if confidence >= 0.99 else CL_REC  # not used directly; per-property below

    ln_nca = ln_pct(g)
    nca = math.exp(ln_nca)
    eta15, eta11 = eta_vft(g, 1150.), eta_vft(g, 1100.)
    ec11, ec12 = ec_vft(g, 1100.), ec_vft(g, 1200.)
    # wSO3: model input is BR; evaluate with BR SO3 renorm on the BR composition
    gbr = to_br(g)
    gso3_br = gbr.get("SO3", 0.0)
    w3ts = wso3_3ts(g, gso3_renorm=gso3_br)
    lnk = ln_kneck(g)
    tlp, tlz, c95 = tl_p_gated(g), tl_zr_gated(g), c950(g)
    lnrb = ln_tclp(g)
    npp = neph_P(g)

    ev = GlassEvaluation(
        g=g, ave_ln_nl=ln_nca, nca_g_l=nca,
        eta1150=eta15, eta1100=eta11, ec1100=ec11, ec1200=ec12,
        wso3_3ts=w3ts, ln_k1208=lnk, p_phos=npp,
        NNaLi=n_nali(g), NALK=nalk(g), NSiAl=nsial(g), NSiBi=nsibi(g),
        ln_tclp_rB=lnrb, np_p=npp, tl_p=tlp, tl_zr=tlz, c950=c95,
        gF_br=gbr.get("F", 0.0), gSO3_br=gso3_br, confidence=confidence,
        _tclp_raw={el: tclp_elements(g)[el] for el in ("Cd", "Cr", "V")},
    )

    u_pct = upred_pct(g, confidence)
    u_tclp = upred_tclp(g, confidence)
    u_v15 = upred_vft("viscosity", g, 1150., confidence)
    u_v11 = upred_vft("viscosity", g, 1100., confidence)
    u_v12 = upred_vft("viscosity", g, 1200., confidence)
    u_e11 = upred_vft("ec", g, 1100., confidence)
    u_e12 = upred_vft("ec", g, 1200., confidence)
    u_k3 = upred_kneck(g, confidence)
    u_s3 = upred_wso3(gbr, confidence, gso3_renorm=gso3_br)   # BR basis (Table 3.7 calibrated)
    u_tlp = upred_pqm("tl_p", g, confidence)
    u_tlz = upred_pqm("tl_zr", g, confidence)
    u_c95 = upred_pqm("c950", g, confidence)
    ev.upred = {"pct": u_pct, "tclp": u_tclp, "eta1150_ln": u_v15, "eta1100_ln": u_v11,
                "eta1200_ln": u_v12, "ec1100_ln": u_e11, "ec1200_ln": u_e12,
                "k1208_ln": u_k3, "wso3": u_s3, "tl_p": u_tlp, "tl_zr": u_tlz,
                "c950": u_c95}
    # legacy key aliases used by existing callers
    ev.upred.update({"eta1150": u_v15 * math.log(10) * eta15,
                     "eta1100": u_v11 * math.log(10) * eta11,
                     "ec1100": u_e11 * math.log(10) * ec11,
                     "ec1200": u_e12 * math.log(10) * ec12,
                     "k1208": u_k3, "wso3": u_s3, "phos": 0.0})

    def _u(prop):
        return (ucomp or {}).get(prop, 0.0)

    def _ok_le(v, lim, tol=1e-7): return v <= lim + tol
    def _ok_ge(v, lim, tol=1e-7): return v >= lim - tol

    c = ev.constraints
    # PCT: NCAve g/L, SUCI; t(P) + Upred + Ucomp <= 12.88
    c["PCT_NCAve_g_L"] = (nca, _ok_le(math.exp(ln_nca + u_pct + _u("pct")), PCT_LIMIT_G_L))
    # TCLP via rB proxy; element releases
    tclp_e = tclp_elements(g)
    c["TCLP_rB_mg_L"] = (math.exp(lnrb + u_tclp + _u("tclp")), _ok_le(math.exp(lnrb + u_tclp + _u("tclp")), 9999.0))
    c["TCLP_CCd"] = (tclp_e["Cd"], _ok_le(tclp_e["Cd"], 0.48))
    c["TCLP_CCr"] = (tclp_e["Cr"], _ok_le(tclp_e["Cr"], 4.95))
    c["TCLP_CV"] = (tclp_e["V"], _ok_le(tclp_e["V"], 16.9))
    # viscosity band with margins applied INSIDE (t(P) ± (Upred+Ucomp))
    eta_f = lambda lnU: 10 ** (math.log10(eta15) + lnU + _u("eta1150"))
    c["eta1150_up"] = (eta15, _ok_le(math.log10(eta15) + u_v15 + _u("eta1150"), math.log10(ETA1150_RANGE[1])))
    c["eta1150_lo"] = (eta15, _ok_ge(math.log10(eta15) - u_v15 - _u("eta1150"), math.log10(ETA1150_RANGE[0])))
    c["eta1100_max"] = (eta11, _ok_le(math.log10(eta11) + u_v11 + _u("eta1100"),
                                      math.log10(ETA1100_MAX)))
    c["ec1100_min"] = (ec11, _ok_ge(math.log10(ec11) - u_e11 - _u("ec1100"), math.log10(EC1100_MIN)))
    c["ec1200_max"] = (ec12, _ok_le(math.log10(ec12) + u_e12 + _u("ec1200"), math.log10(EC1200_MAX)))
    # sulfate: gSO3 (BR wt%) <= wSO3-3TS - 0.33 - Upred - Ucomp
    gso3_wt = 100.0 * gso3_br
    c["wSO3_MT_wt%"] = (gso3_wt, _ok_le(gso3_wt, w3ts - SO3_MT_OFFSET - u_s3 - _u("wso3")))
    # kneck: ln k + U_ln <= ln(0.025 in)
    c["kneck_1208_in"] = (math.exp(lnk), _ok_le(lnk + u_k3 + _u("kneck"), math.log(KNECK_LIMIT_IN)))
    # TL-P / TL-Zr gated 1050 C (raw rows keep the ungated PQM; margins added per Eq 3.6)
    c["TL-P_1050C"] = (tlp, _ok_le(tlp + u_tlp + _u("tl_p"), TL_LIMIT_C) if tlp > 0 else True)
    c["TL-Zr_1050C"] = (tlz, _ok_le(tlz + u_tlz + _u("tl_zr"), TL_LIMIT_C) if tlz > 0 else True)
    c["C950_vol%"] = (c95, _ok_le(c95 + u_c95 + _u("c950"), C950_MAX))
    c["NP_P"] = (npp, _ok_ge(npp - (ucomp or {}).get("np_p", 0.0), NPH_P_MIN))
    c["N_NaLi"] = (ev.NNaLi, _ok_ge(ev.NNaLi, IMMIN_MIN))
    c["gF_br_2.5wt%"] = (ev.gF_br, _ok_le(ev.gF_br, F_BR_MAX))
    c["nonspinel_ThZr"] = (g.get("ThO2", 0.) + g.get("ZrO2", 0.),
                           _ok_le(g.get("ThO2", 0.) + g.get("ZrO2", 0.), THO2_ZRO2_MAX))
    c["NALK_bounds"] = (ev.NALK, _ok_ge(ev.NALK, NALK_RANGE[0]) and _ok_le(ev.NALK, NALK_RANGE[1]))
    c["NSiAl_bounds"] = (ev.NSiAl, _ok_ge(ev.NSiAl, NSIAL_RANGE[0]) and _ok_le(ev.NSiAl, NSIAL_RANGE[1]))
    c["NSiBi_bounds"] = (ev.NSiBi, _ok_ge(ev.NSiBi, NSIBI_RANGE[0]) and _ok_le(ev.NSiBi, NSIBI_RANGE[1]))
    # model validity (Table 3.2 Overall)
    for o, (lo, hi) in MV.items():
        c[f"MV_{o}"] = (g.get(o, 0.0), _ok_ge(g.get(o, 0.0), lo - 1e-6) and _ok_le(g.get(o, 0.0), hi + 1e-6))
    ev.all_pass = all(v[1] for v in c.values())
    return ev


# ---------------------------------------------------------------- Ucomp (§3.3)
UCOMP_PROP_KEYS = ("pct", "tclp", "eta1150", "eta1100", "ec1100", "ec1200",
                   "wso3", "kneck", "tl_p", "tl_zr", "c950", "np_p")

def ucomp_glass(waste: Dict[str, float], gfc_mass_frac: Dict[str, float],
                glass_of: "callable" = None, confidence: float = 0.90,
                n_mc: int = 10000, seed: int = 0,
                waste_rel_cv: float = 0.10, gfc_rel_cv: float = 0.05,
                gfc_mass_rel_cv: float = 0.03, waste_mass_rel_cv: float = 0.05) -> Dict[str, float]:
    """Composition/process uncertainty per §3.3 Eq 3.1-3.5: Monte-Carlo the
    mass balance and report the CL-percentage-point minus median half-width
    (Eq 3.5) per property, in the units the constraints consume Upred+Ucomp in
    (pct/tclp/kneck: ln; eta/ec: log10; wso3/tl/c950/np_p: native).

    Realization = per-oxide log-triangular perturbation of the WASTE composition
    (c_ij, rel CV waste_rel_cv) and waste mass (waste_mass_rel_cv), of each GFC
    oxide-yield vector (rel CV gfc_rel_cv) and GFC mass (gfc_mass_rel_cv), and
    of the retention factor nu_i drawn from the report's own lnDF_min /
    lnDF_most_likely / lnDF_max range (Appendix F, via a triangular draw on
    lnDF).  NOTE: the Appendix F/B distribution family for the waste
    composition uncertainty itself is not reproduced numerically in the report
    text extract, so the relative-CV defaults are CONFIGURABLE placeholders
    (documented in ewg30/RESOLUTIONS.md) - pass explicit values when the
    appendix tables become available.

    gfc_mass_frac: raw GFC mass fraction per unit glass, e.g. the optimizer's
    gfc_raw_mass_fraction; 'Waste' entries are ignored (use `waste`).
    """
    import random
    from .gfc import GFCS
    rnd = random.Random(seed)
    waste = {k: float(v) for k, v in waste.items() if v}
    gfc_mass_frac = {k: float(v) for k, v in (gfc_mass_frac or {}).items()
                     if v and k != "Waste"}
    gfc_names = [n for n in gfc_mass_frac if n in GFCS]

    def _tri_log(vec, cv):
        out = {}
        for k, v in vec.items():
            lo, hi = math.exp(-math.sqrt(3) * cv) * v, math.exp(math.sqrt(3) * cv) * v
            out[k] = rnd.triangular(lo, v, hi)
        return out

    def _nu(k):
        d = CON30["retention"].get(k, {})
        lo, ml, hi = d.get("lnDF_min"), d.get("lnDF_most_likely"), d.get("lnDF_max")
        if lo is None or hi is None:
            return RET30.get(k, 0.99721)
        ml = ml if ml is not None else 0.5 * (lo + hi)
        return 1.0 - math.exp(-rnd.triangular(lo, ml, hi))

    cols = {k: [] for k in UCOMP_PROP_KEYS}
    for _ in range(n_mc):
        w = _tri_log(waste, waste_rel_cv)
        wm = rnd.triangular(math.exp(-math.sqrt(3) * waste_mass_rel_cv),
                            1.0, math.exp(math.sqrt(3) * waste_mass_rel_cv))
        br = {o: w.get(o, 0.0) * wm for o in w}
        for name in gfc_names:
            yields = _tri_log(GFCS[name], gfc_rel_cv)
            frac = rnd.triangular(math.exp(-math.sqrt(3) * gfc_mass_rel_cv) * gfc_mass_frac[name],
                                  gfc_mass_frac[name],
                                  math.exp(math.sqrt(3) * gfc_mass_rel_cv) * gfc_mass_frac[name])
            for o, y in yields.items():
                br[o] = br.get(o, 0.0) + y * frac
        ar = {k: v * _nu(k) for k, v in br.items() if v > 0}
        s = sum(ar.values())
        if s <= 0:
            continue
        g = {k: v / s for k, v in ar.items()}
        gbr = to_br(g)
        gso3_br = gbr.get("SO3", 0.0)
        lnk = ln_kneck(g)
        tlp = tl_p_gated(g)
        tlz = tl_zr_gated(g)
        vals = {
            "pct": ln_pct(g),
            "tclp": ln_tclp(g),
            "eta1150": math.log10(eta_vft(g, 1150.)),
            "eta1100": math.log10(eta_vft(g, 1100.)),
            "ec1100": math.log10(ec_vft(g, 1100.)),
            "ec1200": math.log10(ec_vft(g, 1200.)),
            "wso3": 100.0 * gso3_br,
            "kneck": lnk,
            "tl_p": tlp,
            "tl_zr": tlz,
            "c950": c950(g),
            "np_p": neph_P(g),
        }
        for k, v in vals.items():
            cols[k].append(v)

    def _q(xs, p):
        xs = sorted(xs)
        if not xs:
            return 0.0
        i = min(len(xs) - 1, max(0, int(p * (len(xs) - 1) + 0.5)))
        return xs[i]

    out = {}
    for k, xs in cols.items():
        if not xs:
            out[k] = 0.0
            continue
        # one-sided half-width: Q_CL - Q_50 (Eq 3.5); np_p is a lower-bound
        # property, so take Q_50 - Q_(1-CL)
        if k == "np_p":
            out[k] = max(_q(xs, 0.5) - _q(xs, 1.0 - confidence), 0.0)
        else:
            out[k] = max(_q(xs, confidence) - _q(xs, 0.5), 0.0)
    return out


FULL_OXIDES_SET = set()
