"""Tensor backend for the EWG3.0 margin set (branch tensor-backend).

Reproduces the exact 24 SLSQP constraints built by optimize.formulate's
cfun() closures plus the Table 3.2 MV bounds as ONE vectorized NumPy
computation with an ANALYTIC Jacobian, replacing:

  (a) the per-closure fan-out (each of 24 closures re-derived the same
      property stack and every closure was re-called inside scipy's
      numeric constraint Jacobian),
  (b) the finite-difference Jacobian ((n+1) full P.evaluate() calls per
      iterate per constraint vector).

Technique: forward-mode automatic differentiation on the 49-oxide basis
(numpy gradient rows over g), then the analytic chain rule through the
linear mixing map  g = (x @ M) / sum(x @ M):

    dg_i / dx_a = (M[a,i] - g_i * msum_a) / s,   msum_a = sum_i M[a,i]

so  dmargin/dx = dmargin/dg @ dg/dx  (a (49 x n) matmul).  Every model
(PQM/VFT/nepheline polynomial) and its Upred covariance form
sqrt(f' Sigma f) is differentiated through the same dual numbers, so one
dual sweep yields margins AND the full n-column Jacobian at roughly the
cost of a single P.evaluate() call.

Parity: tests compare margins against the closure path (<1e-12 rel) and
the Jacobian against central finite differences on x.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import properties as P
from .gfc import GFC_NAMES


# ---------------------------------------------------------------- dual class
class D:
    """Dual number: float value + gradient row (numpy array) or None."""
    __slots__ = ("v", "d")

    def __init__(self, v, d=None):
        self.v = float(v)
        self.d = d

    # arithmetic ---------------------------------------------------------
    def __add__(self, o):
        if isinstance(o, D):
            if self.d is None and o.d is None:
                return D(self.v + o.v)
            if self.d is None:
                return D(self.v + o.v, o.d)
            if o.d is None:
                return D(self.v + o.v, self.d)
            return D(self.v + o.v, self.d + o.d)
        return D(self.v + o, self.d)

    __radd__ = __add__

    def __sub__(self, o):
        if isinstance(o, D):
            if self.d is None and o.d is None:
                return D(self.v - o.v)
            if self.d is None:
                return D(self.v - o.v, -o.d)
            if o.d is None:
                return D(self.v - o.v, self.d)
            return D(self.v - o.v, self.d - o.d)
        return D(self.v - o, self.d)

    def __rsub__(self, o):
        if isinstance(o, D):
            return o.__sub__(self)
        return D(o - self.v, None if self.d is None else -self.d)

    def __mul__(self, o):
        if isinstance(o, D):
            if self.d is None and o.d is None:
                return D(self.v * o.v)
            if self.d is None:
                return D(self.v * o.v, self.v * o.d)
            if o.d is None:
                return D(self.v * o.v, o.v * self.d)
            return D(self.v * o.v, self.v * o.d + o.v * self.d)
        if o == 0.0:
            return D(0.0)
        return D(self.v * o, None if self.d is None else self.d * o)

    __rmul__ = __mul__

    def __truediv__(self, o):
        if isinstance(o, D):
            if o.d is None or (o.d == 0).all():
                return self * (1.0 / o.v)
            return self * D(1.0 / o.v, -o.d / (o.v * o.v))
        return self * (1.0 / o)

    def __rtruediv__(self, o):
        if isinstance(o, D):
            return o.__truediv__(self)
        return D(o / self.v, None if self.d is None else -self.d / (self.v * self.v))

    def __neg__(self):
        return D(-self.v, None if self.d is None else -self.d)

    def __pow__(self, p):  # constant exponent only
        if p == 0:
            return D(1.0)
        v2 = self.v ** p if self.v >= 0 or float(p).is_integer() else \
            self.v ** p if abs(self.v) > 0 else 0.0
        if abs(self.v) < 1e-300:
            return D(0.0, None if self.d is None else np.zeros_like(self.d))
        return D(v2, None if self.d is None else
                 p * self.v ** (p - 1.0) * self.d)


def _exp(a):
    if isinstance(a, D):
        e = math.exp(a.v)
        return D(e, None if a.d is None else e * a.d)
    return D(math.exp(a))


def _log(a):
    if isinstance(a, D):
        return D(math.log(a.v), None if a.d is None else a.d / a.v)
    return D(math.log(a))


_LN10 = math.log(10.0)
_INV_LN10 = 1.0 / _LN10


def _log10(a):
    return _log(a) * _INV_LN10


def _pow10(a: D) -> D:
    return _exp(a * _LN10)


# ---------------------------------------------------------------- backend
class MarginEval:
    """Vectorized margins + analytic Jacobian for one waste/GFC mix map."""

    def __init__(self, Mrows: np.ndarray, confidence: float = 0.90,
                 ucomp: Optional[Dict[str, float]] = None):
        from .optimize import FULL_OXIDES
        self.M = np.asarray(Mrows, dtype=float)          # n x GN
        self.n = self.M.shape[0]
        self.OX = list(FULL_OXIDES)
        self.GN = len(self.OX)
        self.OI = {o: i for i, o in enumerate(self.OX)}
        self.msum = self.M.sum(axis=1)
        self.confidence = confidence
        self.ucomp = dict(ucomp or {})
        self._cov = {m: P._cov(m) for m in
                     ("pct", "tclp", "k3", "so3", "tl_p", "tl_zr", "c950",
                      "viscosity", "ec")}
        self._clf = {}
        self._wcache: Dict[tuple, np.ndarray] = {}

    # -- helpers ----------------------------------------------------------
    def _uc(self, key: str) -> float:
        return float(self.ucomp.get(key, 0.0))

    def _cl(self, model: str, sucni=False) -> float:
        """Upred multiplier, memoized (constant per MarginEval)."""
        key = (model, bool(sucni))
        if key not in self._clf:
            self._clf[key] = (P._sucni_factor(model, self.confidence)
                              if sucni else P._cl_factor(model, self.confidence))
        return self._clf[key]

    # -- named feature rows ------------------------------------------------
    def _feat_rows(self, names: List[str], br: bool) -> np.ndarray:
        """Weight rows (len(names) x GN) mapping g (or br=g/ret) -> features.
        'Others'/'Other' rows are the residual; 'LN2O3' rows are the
        lanthanide fold.  Rows depend only on (names, br) -> cached."""
        key = (tuple(names), br)
        cached = self._wcache.get(key)
        if cached is not None:
            return cached
        OI = self.OI
        W = np.zeros((len(names), self.GN))
        for i, name in enumerate(names):
            if name in ("Others", "Other"):
                continue
            if name == "LN2O3":
                for o in P.LANTHANIDES:
                    if o in OI:
                        W[i, OI[o]] = 1.0
                if br:
                    # br LN fold: each lanthanide divided by its own retention
                    for o in P.LANTHANIDES:
                        if o in OI:
                            W[i, OI[o]] = 1.0 / (P.RET30.get(o, 0.99721) or 0.99721)
            elif name in OI:
                W[i, OI[name]] = 1.0 if not br else \
                    1.0 / (P.RET30.get(name, 0.99721) or 0.99721)
        res = [i for i, nm in enumerate(names) if nm not in ("Others", "Other")]
        if len(res) < len(names):
            ir = [i for i, nm in enumerate(names) if nm in ("Others", "Other")][0]
            if not br:
                # AR basis: sum(g) == 1 identically on the x-manifold, so the
                # residual 1 - sum(named) equals sum over uncovered oxides;
                # the row below is then BOTH the value and the gradient.
                covered = np.zeros(self.GN, dtype=bool)
                for i in res:
                    nm = names[i]
                    if nm == "LN2O3":
                        for o in P.LANTHANIDES:
                            if o in self.OI:
                                covered[self.OI[o]] = True
                    elif nm in self.OI:
                        covered[self.OI[nm]] = True
                W[ir] = (~covered).astype(float)
            else:
                # BR basis: sum(br) != 1 (retention deflates the glass), so
                # the residual is the affine 1 - sum(named br): built as a
                # dual in _feats; zero row here.
                W[ir] = 0.0
        self._wcache[key] = W
        return W

    def _feats(self, g, G, names: List[str], br=False, denom: float = 1.0
               ) -> Dict[str, D]:
        W = self._feat_rows(names, br)
        vals = W @ g / denom
        cols = W @ G.T / denom
        feats = {nm: D(vals[i], cols[i]) for i, nm in enumerate(names)}
        for rname in ("Others", "Other"):
            if rname not in names:
                continue
            if br:
                # residual(br) = max(1 - sum(named br), 0) as an affine dual
                nsum = D(0.0)
                for nm in names:
                    if nm not in ("Others", "Other"):
                        nsum = nsum + feats[nm]
                resd = D(1.0) - nsum
                if resd.v <= 0.0:
                    resd = D(0.0, np.zeros(nsum.d.shape[0] if nsum.d is not None
                                           else 0))
                feats[rname] = resd
            else:
                if feats[rname].v <= 0.0:
                    # clamped residual: frozen subgradient, x-space row
                    feats[rname] = D(0.0, np.zeros(self.n))
        return feats

    # ------------------------------------------------------------------
    def margins(self, x: np.ndarray) -> np.ndarray:
        return self._sweep(x)[0]

    def jac(self, x: np.ndarray) -> np.ndarray:
        return self._sweep(x)[1]

    def margins_and_jac(self, x: np.ndarray):
        return self._sweep(x)

    # ------------------------------------------------------------------
    def _sweep(self, x: np.ndarray):
        x = np.asarray(x, dtype=float)
        s = float(x @ self.msum)
        g = (x @ self.M) / s
        G = (self.M - np.outer(self.msum, g)) / s     # dg/dx (n x GN)

        OI, GN = self.OI, self.GN
        n = self.n

        def gm(o: str) -> D:
            """AR mass fraction of a single oxide (dual)."""
            i = OI.get(o)
            return D(g[i], G[:, i]) if i is not None else D(0.0)

        # mole basis (normalized over ALL oxides; lanthanides folded into a
        # single LN2O3 lump at MW 336.48, as basis_mole does)
        MW_LN = P.MW.get("LN2O3", 336.48)
        lan_set = [o for o in P.LANTHANIDES]
        nonlan = [k for k, o in enumerate(self.OX) if o not in lan_set]
        MWv = np.zeros(GN)
        for k in nonlan:
            MWv[k] = 1.0 / P.MW.get(self.OX[k], 60.084)
        # u'-vector: non-lan oxides keep g_k/MW_k; lan mass flows only via
        # the LN lump at MW_LN
        u = g * MWv
        u_ln_val = float(g[[OI[o] for o in lan_set if o in OI]].sum()) / MW_LN \
            if any(o in OI for o in lan_set) else 0.0
        Ug = float(u.sum()) - float(u[[OI[o] for o in lan_set if o in OI]].sum()) \
            + u_ln_val
        # gradient wrt g of u'-features: non-lan k: e_k/MW_k;
        # LN lump: (1/MW_LN) * sum_lan e_i
        du_ln = np.zeros(GN)
        for o in lan_set:
            if o in OI:
                du_ln[OI[o]] = 1.0 / MW_LN
        # xn for non-lan features
        xn = np.zeros(GN)
        dxn_g = np.zeros((GN, GN))       # wrt g, per non-lan oxide
        U2 = Ug * Ug
        dUg_dg = MWv + du_ln          # LU lump contributes 1/MW_LN per lan
        for k in nonlan:
            xn[k] = u[k] / Ug
            # d(u_k)/dg_j = MWv_k * δ_kj ; dxn[k] = (MWv_k U e_k - u_k dU)/U²
            row = -u[k] * dUg_dg
            row[k] += MWv[k] * Ug
            dxn_g[k] = row / U2
        # LN lump mole feature
        xn_ln = u_ln_val / Ug
        dxn_ln_g = (du_ln * Ug - u_ln_val * dUg_dg) / U2 if du_ln.any() else None

        def md(names: List[str]) -> Dict[str, D]:
            """Named mole features; each is xn[oxide]; 'LN2O3' is the folded
            lanthanide lump (MW 336.48); residual names ('Others') =
            1 - sum(named, excluding residual), matching basis_mole's
            `out['Others'] = 1 - sum(out.values())`."""
            out: Dict[str, D] = {}
            rowsum = np.zeros(n)           # sum of NON-residual named rows
            vsum = 0.0
            for nm in names:
                if nm in ("Others", "Other"):
                    continue
                if nm == "LN2O3":
                    if dxn_ln_g is not None:
                        dd = D(xn_ln, dxn_ln_g @ G.T)
                    else:
                        dd = D(0.0, np.zeros(n))
                    out[nm] = dd
                    rowsum = rowsum + dd.d
                    vsum += dd.v
                    continue
                i = OI.get(nm)
                if i is None:
                    out[nm] = D(0.0, np.zeros(n))
                else:
                    out[nm] = D(xn[i], dxn_g[i] @ G.T)
                    rowsum = rowsum + out[nm].d
                    vsum += xn[i]
            for nm in names:
                if nm in out:
                    continue
                # residual = 1 - sum(named): value clamped at 0 like
                # basis_mole; gradient row = -sum(named rows)
                res = 1.0 - vsum
                if res <= 0.0 and nm in ("Others", "Other"):
                    out[nm] = D(0.0, np.zeros(n))
                else:
                    out[nm] = D(max(res, 0.0), -rowsum)
            return out

        conf = self.confidence

        # ---------------- PCT model + Upred ----------------
        tm = P.M30["pct"]["terms"]
        pk = [k for k in tm if "*" not in k]
        xnp = md(pk)
        a, b = xnp["Al2O3"], xnp["B2O3"]
        ln_nca = D(0.0)
        for k, c in tm.items():
            if "*" not in k:
                ln_nca = ln_nca + c * xnp[k]
        ln_nca = (ln_nca + tm["Al2O3*Al2O3"] * (a * a) + tm["Al2O3*B2O3"] * (a * b)
                  + tm["B2O3*B2O3"] * (b * b) + tm["Al2O3*Al2O3*Al2O3"] * a ** 3
                  + tm["Al2O3*Al2O3*Al2O3*Al2O3"] * a ** 4)
        if getattr(self, "debug", False):
            self.dbg_xn = dict(xnp)
        cp = self._cov["pct"]
        if cp:
            fvals = np.zeros(len(cp["terms"]))
            fcols = np.zeros((len(cp["terms"]), n))
            xm = {"Al2O3*Al2O3": a * a, "Al2O3*B2O3": a * b,
                  "B2O3*B2O3": b * b, "(Al2O3)^3": a ** 3, "(Al2O3)^4": a ** 4}
            for i, t in enumerate(cp["terms"]):
                dd = xnp.get(t, xm.get(t, D(0.0)))
                fvals[i] = dd.v
                fcols[i] = dd.d if dd.d is not None else 0.0
            u_pct = _cov_sd(cp, fvals, fcols) * self._cl("pct", True)
        else:
            u_pct = D(0.0)

        # ---------------- VFT (viscosity / EC) ----------------
        def vft(model: str, T_C: float):
            terms = P.M30[model]["terms"]
            Tk = T_C + 273.15
            T0 = terms["T0"]
            bnames = [k[2:] for k in terms if k.startswith("B_")]
            gv = self._feats(g, G, bnames)
            B = D(0.0)
            for k, c in terms.items():
                if k.startswith("B_"):
                    B = B + c * gv[k[2:]]
            dt = Tk - T0
            return gv, B, dt

        def upred_vft(model: str, T_C: float, gv, B: D, dt: float) -> D:
            c = self._cov[model]
            if not c:
                return D(0.0)
            Tk = T_C + 273.15
            T0 = P.M30[model]["terms"]["T0"]
            dt2 = dt * dt
            fvals = np.zeros(len(c["terms"]))
            fcols = np.zeros((len(c["terms"]), n))
            dB = B.d if B.d is not None else np.zeros(n)
            for i, t in enumerate(c["terms"]):
                if t == "A":
                    fvals[i] = 1.0
                elif t == "T0":
                    fvals[i] = B.v / dt2
                    fcols[i] = dB / dt2
                elif t.startswith("B_"):
                    dd = gv.get(t[2:], D(0.0))
                    fvals[i] = dd.v / dt
                    fcols[i] = (dd.d if dd.d is not None else np.zeros(n)) / dt
            return _cov_sd(c, fvals, fcols) * self._cl(model, False)

        gv15, B15, dt15 = vft("viscosity", 1150.)
        gv11, B11, dt11 = vft("viscosity", 1100.)
        gve11, Be11, dte11 = vft("ec", 1100.)
        gve12, Be12, dte12 = vft("ec", 1200.)
        eta15 = _pow10(P.M30["viscosity"]["terms"]["A"] + B15 / dt15)
        eta11 = _pow10(P.M30["viscosity"]["terms"]["A"] + B11 / dt11)
        ec11 = _pow10(P.M30["ec"]["terms"]["A"] + Be11 / dte11)
        ec12 = _pow10(P.M30["ec"]["terms"]["A"] + Be12 / dte12)
        u_v15 = upred_vft("viscosity", 1150., gv15, B15, dt15)
        u_v11 = upred_vft("viscosity", 1100., gv11, B11, dt11)
        u_e11 = upred_vft("ec", 1100., gve11, Be11, dte11)
        u_e12 = upred_vft("ec", 1200., gve12, Be12, dte12)

        # ---------------- TCLP ----------------
        tm = P.M30["tclp"]["terms"]
        tk = [k for k in tm if "*" not in k]
        xt = md(tk)
        ln_tclp = D(0.0)
        for k, c in tm.items():
            if "*" not in k:
                ln_tclp = ln_tclp + c * xt[k]
        ln_tclp = ln_tclp + tm["Li2O*SiO2"] * (xt["Li2O"] * xt["SiO2"]) \
            + tm["MgO*Na2O"] * (xt["MgO"] * xt["Na2O"])
        rB = _exp(ln_tclp)
        ct = self._cov["tclp"]
        if ct:
            fvals = np.zeros(len(ct["terms"]))
            fcols = np.zeros((len(ct["terms"]), n))
            xm = {"Li2O*SiO2": xt["Li2O"] * xt["SiO2"],
                  "MgO*Na2O": xt["MgO"] * xt["Na2O"]}
            for i, t in enumerate(ct["terms"]):
                dd = xt.get(t, xm.get(t, D(0.0)))
                fvals[i] = dd.v
                fcols[i] = dd.d if dd.d is not None else 0.0
            u_tclp = _cov_sd(ct, fvals, fcols) * self._cl("tclp", True)
        else:
            u_tclp = D(0.0)
        rawCd = gm("CdO") * (112.414 / 128.413) * rB
        rawCr = gm("Cr2O3") * (103.992 / 151.989) * rB
        rawV = gm("V2O5") * (101.88 / 181.88) * rB
        CCd = rawCd if rawCd.v < 0.48 else D(0.48)
        CCr = rawCr if rawCr.v < 4.95 else D(4.95)
        CV = rawV if rawV.v < 16.9 else D(16.9)

        # ---------------- K-3 neck growth ----------------
        tm = P.M30["k3"]["terms"]
        mk = [k for k in tm if "*" not in k and k != "kS1200"]
        xk = md(mk + ["Cl"])
        # q_k = xn_k / (1 - xn_Cl): Cl is variable -> keep dual denominator
        cl_d = xk["Cl"]
        one_m_cl = D(1.0) - cl_d
        qd = {k: xk[k] / one_m_cl for k in xk if k != "Cl"}
        lnk = D(0.0)
        for k, c in tm.items():
            if "*" not in k and k != "kS1200":
                lnk = lnk + c * qd[k]
        for k, c in tm.items():
            if "*" in k:
                o1, o2 = k.split("*")
                lnk = lnk + c * qd.get(o1, D(0.0)) * qd.get(o2, D(0.0))
        ck = self._cov["k3"]
        if ck:
            fvals = np.zeros(len(ck["terms"]))
            fcols = np.zeros((len(ck["terms"]), n))
            for i, t in enumerate(ck["terms"]):
                if t == "Stat, 1200":
                    fvals[i] = 0.0
                elif "*" in t:
                    o1, o2 = t.split("*")
                    f1, f2 = qd.get(o1, D(0.0)), qd.get(o2, D(0.0))
                    fvals[i] = f1.v * f2.v
                    d1 = f1.d if f1.d is not None else np.zeros(n)
                    d2 = f2.d if f2.d is not None else np.zeros(n)
                    fcols[i] = f1.v * d2 + f2.v * d1
                else:
                    dd = qd.get(t, D(0.0))
                    fvals[i] = dd.v
                    fcols[i] = dd.d if dd.d is not None else np.zeros(n)
            u_k3 = _cov_sd(ck, fvals, fcols) * self._cl("k3", False)
        else:
            u_k3 = D(0.0)

        # ---------------- wSO3-3TS (forward: AR basis; Upred: BR basis) ---
        gso3_br = self._feats(g, G, ["SO3"], br=True)["SO3"]
        tm = P.M30["so3"]["terms"]
        sk = [k for k in tm if "*" not in k]
        gs_ar = self._feats(g, G, sk)
        one_m_gs = D(1.0) - gso3_br
        xd = {k: gs_ar[k] / one_m_gs for k in sk}
        w3ts = D(0.0)
        for k, c in tm.items():
            if "*" not in k:
                w3ts = w3ts + c * xd[k]
        for k, c in tm.items():
            if "*" in k:
                o1, o2 = k.split("*")
                w3ts = w3ts + c * xd.get(o1, D(0.0)) * xd.get(o2, D(0.0))
        cs = self._cov["so3"]
        if cs:
            gs_br = self._feats(g, G, sk, br=True)
            xd_br = {k: gs_br[k] / one_m_gs for k in sk}
            fvals = np.zeros(len(cs["terms"]))
            fcols = np.zeros((len(cs["terms"]), n))
            for i, t in enumerate(cs["terms"]):
                if "*" in t:
                    o1, o2 = t.split("*")
                    f1, f2 = xd_br.get(o1, D(0.0)), xd_br.get(o2, D(0.0))
                    fvals[i] = f1.v * f2.v
                    d1 = f1.d if f1.d is not None else np.zeros(n)
                    d2 = f2.d if f2.d is not None else np.zeros(n)
                    fcols[i] = f1.v * d2 + f2.v * d1
                else:
                    dd = xd_br.get(t, D(0.0))
                    fvals[i] = dd.v
                    fcols[i] = dd.d if dd.d is not None else np.zeros(n)
            u_s3 = _cov_sd(cs, fvals, fcols) * self._cl("so3", False)
        else:
            u_s3 = D(0.0)

        # ---------------- PQM trio (tl_p / tl_zr / c950) ----------------
        def pqm(model: str):
            tm = P.M30[model]["terms"]
            nk = [k for k in tm if "*" not in k and k not in ("kS1200",)]
            gd = self._feats(g, G, nk)
            v = D(0.0)
            for k, c in tm.items():
                if "*" not in k:
                    v = v + c * gd.get(k, D(0.0))
            for k, c in tm.items():
                if "*" in k:
                    o1, o2 = k.split("*")
                    v = v + c * gd.get(o1, D(0.0)) * gd.get(o2, D(0.0))
            c = self._cov[model]
            u = D(0.0)
            if c:
                fvals = np.zeros(len(c["terms"]))
                fcols = np.zeros((len(c["terms"]), n))
                for i, t in enumerate(c["terms"]):
                    if "*" in t:
                        o1, o2 = t.split("*")
                        f1, f2 = gd.get(o1, D(0.0)), gd.get(o2, D(0.0))
                        fvals[i] = f1.v * f2.v
                        d1 = f1.d if f1.d is not None else np.zeros(n)
                        d2 = f2.d if f2.d is not None else np.zeros(n)
                        fcols[i] = f1.v * d2 + f2.v * d1
                    else:
                        dd = gd.get(t, D(0.0))
                        fvals[i] = dd.v
                        fcols[i] = dd.d if dd.d is not None else np.zeros(n)
                u = _cov_sd(c, fvals, fcols) * self._cl(model, False)
            return v, u

        tlp, u_tlp = pqm("tl_p")
        tlz, u_tlz = pqm("tl_zr")
        c95, u_c95 = pqm("c950")

        # ---------------- nepheline P (mole basis) ----------------
        cn = P.M30["neph"]["terms"]
        pa, pb, pc = cn["Poly a (Const)"], cn["Poly b (X)"], cn["Poly c (X2)"]
        xnn = md(["Na2O", "CaO", "MgO", "Li2O", "K2O", "Al2O3", "Fe2O3",
                  "SiO2", "P2O5", "B2O3"])
        A_ = xnn["Na2O"] + 0.3 * xnn["CaO"] + 0.0 * xnn["MgO"] + 0.4 * xnn["Li2O"]
        B_ = xnn["Al2O3"]
        C_ = xnn["SiO2"] + 1.5 * xnn["P2O5"] + 2.0 * xnn["B2O3"]
        S_ = A_ + B_ + C_
        twoBC = 2.0 * B_ + C_
        npp = (math.sqrt(3.0) * C_ / (2.0 * S_) - D(pa)
               - pb * twoBC / (2.0 * S_) - pc * twoBC * twoBC / (4.0 * S_ * S_))

        # ---------------- simple ratios / sums ----------------
        gNa, gLi = gm("Na2O"), gm("Li2O")
        num_ = gNa + 2.07 * gLi
        den_ = num_ + gm("B2O3") + gm("SiO2")
        nnali = num_ / den_ if den_.v > 0 else D(0.0)
        NALK = gm("Na2O") + 0.66 * gm("K2O") + 2.07 * gm("Li2O")
        NSiAl = gm("SiO2") + 1.697 * gm("Al2O3")
        NSiBi = gm("SiO2") + 2.0 * gm("B2O3")
        gF_br = self._feats(g, G, ["F"], br=True)["F"]
        thzr = gm("ThO2") + gm("ZrO2")

        nca = _exp(ln_nca)
        U = self._uc
        if getattr(self, "debug", False):
            self.dbg = {k: v for k, v in dict(
                u_pct=u_pct, ln_nca=ln_nca, u_tclp=u_tclp, ln_tclp=ln_tclp,
                u_k3=u_k3, lnk=lnk, u_s3=u_s3, w3ts=w3ts, gso3_br=gso3_br,
                tlp=tlp, tlz=tlz, c95=c95, u_tlp=u_tlp, u_tlz=u_tlz,
                u_c95=u_c95, u_v15=u_v15, u_v11=u_v11, u_e11=u_e11,
                u_e12=u_e12, npp=npp, eta15=eta15, eta11=eta11,
                ec11=ec11, ec12=ec12).items()}
        out_v: List[float] = []
        grads: List[np.ndarray] = []
        z = np.zeros(n)

        def push(dd: D):
            if isinstance(dd, D):
                out_v.append(dd.v)
                grads.append(dd.d if dd.d is not None else z)
            else:
                out_v.append(float(dd))
                grads.append(None)

        # margins in cfun order ------------------------------------------------
        push(D(P.PCT_LIMIT_G_L) * _exp(-(u_pct + D(U("pct")))) - nca)
        push(D(4.95) - CCr * _exp(u_tclp))
        push(D(0.48) - CCd * _exp(u_tclp))
        push(D(16.9) - CV * _exp(u_tclp))
        push(_log10(eta15) - u_v15 - D(U("eta1150")) - D(math.log10(P.ETA1150_RANGE[0])))
        push(D(math.log10(P.ETA1150_RANGE[1])) - (_log10(eta15) + u_v15 + D(U("eta1150"))))
        push(D(math.log10(P.ETA1100_MAX)) - (_log10(eta11) + u_v11 + D(U("eta1100"))))
        push(_log10(ec11) - u_e11 - D(U("ec1100")) - D(math.log10(P.EC1100_MIN)))
        push(D(math.log10(P.EC1200_MAX)) - (_log10(ec12) + u_e12 + D(U("ec1200"))))
        push((w3ts - D(P.SO3_MT_OFFSET) - u_s3 - D(U("wso3"))) - gso3_br * 100.0)
        push(D(math.log(P.KNECK_LIMIT_IN)) - (lnk + u_k3 + D(U("kneck"))))
        # gated TL margins (constant 1.0 when ungated, matching cfun)
        push(D(P.TL_LIMIT_C) - (tlp + u_tlp + D(U("tl_p")))
             if g[OI["P2O5"]] >= P.TL_P_GATE else 1.0)
        push(D(P.TL_LIMIT_C) - (tlz + u_tlz + D(U("tl_zr")))
             if g[OI["ZrO2"]] >= P.TL_ZR_GATE else 1.0)
        push(D(P.C950_MAX) - (c95 + u_c95 + D(U("c950"))))
        push(npp - D(U("np_p")) - D(P.NPH_P_MIN))
        push(nnali - D(P.IMMIN_MIN))
        push(NALK - D(P.NALK_RANGE[0]))
        push(D(P.NALK_RANGE[1]) - NALK)
        push(NSiAl - D(P.NSIAL_RANGE[0]))
        push(D(P.NSIAL_RANGE[1]) - NSiAl)
        push(NSiBi - D(P.NSIBI_RANGE[0]))
        push(D(P.NSIBI_RANGE[1]) - NSiBi)
        push(D(P.THO2_ZRO2_MAX) - thzr)
        push(D(P.F_BR_MAX) - gF_br)

        # ---------------- MV bounds (Table 3.2 Overall, AR mass basis) -------
        from .optimize import FULL_OXIDES as _FO
        mv_rows = []
        for i, o in enumerate(self.OX):
            if o in P.MV or o == "RE2O3":
                lo, hi = P.MV.get(o, (0.0, 0.0289)) if o != "RE2O3" else \
                    P.MV.get("LN2O3", (0.0, 0.0289))
                mv_rows.append((o, lo, hi))
        for o, lo, hi in mv_rows:
            gi = gm(o)
            push(gi - D(lo))
            push(D(hi) - gi)

        vals = np.array(out_v, dtype=float)
        J = np.zeros((len(grads), n))
        for i, gr in enumerate(grads):
            if gr is not None:
                J[i] = gr          # dual rows are already in x-space (n)
        return vals, J


def _cov_sd(c, fvals: np.ndarray, fcols: np.ndarray) -> D:
    """Upred sd = sqrt(f' Sigma f) as a dual.

    sd = sqrt(f . (Sigma f));  d(sd) = (Sigma f . df) / sd.
    """
    Ms = c["M"]
    if fvals.size != Ms.shape[0]:
        raise RuntimeError("cov feature vector length mismatch: "
                           f"{fvals.size} vs {Ms.shape[0]}")
    r = Ms @ fvals
    q = float(fvals @ r)
    sd = math.sqrt(max(q, 0.0))
    if fcols is None or not fcols.any() or sd <= 0:
        return D(sd, None)
    return D(sd, (r @ fcols) / sd)
