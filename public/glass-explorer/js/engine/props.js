/**
 * props.js — published glass property models (JS port).
 *
 * Ported 1:1 from the audited Python implementation
 * (the production property-model source), which reproduces the
 * paper's Tables 3-5/3-6 to published precision. Every model evaluates on
 * its OWN renormalized basis — never one shared full-composition vector:
 *
 *   PCT ln[NL]  : 11 modeled terms + Others = 1 − Σ(11)  (full lump)
 *   VFT η / EC  : 15 B-components + Others = 1 − Σ(15); T in Kelvin,
 *                 log10(p) = A + B/(T − T0), B = Σ Bᵢ·gᵢ
 *   Sulfate     : PQMM terms (no TiO2), SO3-free renorm, MT = 3TS − 0.33 wt%
 *   K-3 ln[k]   : 16 terms + Others, (SO3+Cl)-free renorm
 *   Phosphate   : logistic on 6 terms + full-lump Others (Table 2-12, no
 *                 intercept)
 *   N_NaLi      : (gNa2O + 2.07·gLi2O)/(gNa2O + 2.07·gLi2O + gB2O3 + gSiO2)
 *
 * Upred one-sided prediction-uncertainty margins use the Appendix-C
 * coefficient covariance matrices (exported in the manifest):
 *   η/ε : x = [1, g_i/(T−T0)…, B/(T−T0)²], var = x'Σx, U = z·sd·ln10·p
 *   PCT : var = x'Σ(C-1)x + RMSEpress², U = exp(lnNL + z·sd) − NL
 *   K-3 : z·sqrt(x'Σ(C-5)x) in ln units
 *   SO3 : z·sqrt(x'Σ(C-4)x) on the SO3-free basis (wt% scale)
 *
 * Inputs: g = {oxide: mass fraction} — sums to 1, 'Others' key ignored.
 * Browser: window.GlassProps; Node: module.exports.
 */
'use strict';

(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory();
  else root.GlassProps = factory();
})(typeof self !== 'undefined' ? self : this, function () {

  function create(PM, covRaw) {
    // PM = manifest.prop_models, covRaw = manifest.covariance
    const pctLin = PM.pct.lin, pctQuad = PM.pct.quad, pctModeled = PM.pct.modeled;
    const visc = PM.vft_visc, ec = PM.vft_ec;
    const so3Lin = PM.so3.lin, so3Cross = PM.so3.cross, so3Offset = PM.so3.mt_offset;
    const k3Lin = PM.k3.lin, k3Sq = PM.k3.sq, k3Cross = PM.k3.cross;
    const pLin = PM.phos.lin, pCross = PM.phos.cross;
    const Z = PM.z_ci;          // 1.645 — one-sided 95% z
    const rmsePress = PM.pct.rmse_press;

    // ------- covariance matrices (term order from the JSON) -----------
    const cov = {};
    for (const name of Object.keys(covRaw || {})) {
      const terms = Object.keys(covRaw[name]);
      const n = terms.length;
      const M = new Array(n);
      for (let i = 0; i < n; i++) {
        const row = covRaw[name][terms[i]];
        M[i] = row.slice(0, n);
        for (let j = 0; j < n; j++) M[i][j] = parseFloat(M[i][j]);
      }
      cov[name] = { terms, idx: new Map(terms.map((t, i) => [t, i])), M };
    }

    // sd = sqrt(x'Σx) restricted to terms present in the matrix.
    // x is a map term -> value; missing terms contribute 0.
    function covSd(model, xMap) {
      const c = cov[model];
      if (!c) return 0;
      const { idx, M } = c;
      const keys = [], vals = [], cols = [];
      for (const [k, v] of Object.entries(xMap)) {
        const i = idx.get(k);
        if (i !== undefined) { keys.push(v); cols.push(i); }
      }
      const n = cols.length;
      if (!n) return 0;
      let tot = 0;
      for (let a = 0; a < n; a++) {
        let rowSum = 0;
        for (let b = 0; b < n; b++) rowSum += M[cols[a]][cols[b]] * keys[b];
        tot += keys[a] * rowSum;
      }
      return tot > 0 ? Math.sqrt(tot) : 0;
    }

    // 'Al2O3xAl2O3' style quad labels evaluated on a basis dict
    function quadVal(basis, term) {
      if (term.indexOf('x') === -1) return basis[term] || 0;
      const parts = term.split('x');
      if (parts.length === 2 && parts[0] in basis && parts[1] in basis) {
        return basis[parts[0]] * basis[parts[1]];
      }
      return 0;
    }

    // ---------------- per-model bases ----------------
    function basisPct(g) {
      const gm = {};
      for (const k of pctModeled) gm[k] = g[k] || 0;
      gm.Others = 1;
      for (const k of pctModeled) gm.Others -= gm[k];
      return gm;
    }

    function basisVft(g) {
      const terms = Object.keys(visc.B).filter((k) => k !== 'Others');
      const gv = {};
      for (const k of terms) gv[k] = g[k] || 0;
      gv.Others = 1;
      for (const k of terms) gv.Others -= gv[k];
      return gv;
    }

    function basisSo3(g) {
      // Sulfate basis: PQMM terms + residual Others, with SO3 REMOVED from
      // the lump (Python: gs['Others'] = 1 − Σ(terms) − gSO3); the SO3-free
      // renorm x = gs/(1−gSO3) then happens inside evaluate/upred.
      const terms = Object.keys(so3Lin).filter((k) => k !== 'Others');
      const gs = {};
      for (const k of terms) gs[k] = g[k] || 0;
      gs.Others = 1;
      for (const k of terms) gs.Others -= gs[k];
      gs.Others -= g.SO3 || 0;
      return gs;
    }

    function basisK3(g) {
      // K-3 basis: 16 terms + residual Others, with SO3 AND Cl removed from
      // the lump (Python: gk['Others'] = 1 − Σ(terms) − gSO3 − gCl);
      // the (SO3+Cl)-free renorm happens inside evaluate/upred.
      const terms = Object.keys(k3Lin).filter((k) => k !== 'Others');
      const gk = {};
      for (const k of terms) gk[k] = g[k] || 0;
      gk.Others = 1;
      for (const k of terms) gk.Others -= gk[k];
      gk.Others -= g.SO3 || 0;
      gk.Others -= g.Cl || 0;
      return gk;
    }

    // ---------------- VFT family ----------------
    function vftB(model, gv) {
      let B = 0;
      for (const k of Object.keys(model.B)) B += model.B[k] * (gv[k] || 0);
      return B;
    }
    function etaAt(g, T_C) {
      const gv = basisVft(g);
      const B = vftB(visc, gv);
      return Math.pow(10, visc.A + B / (T_C + 273.15 - visc.T0));
    }
    function ecAt(g, T_C) {
      const gv = basisVft(g);
      const B = vftB(ec, gv);
      return Math.pow(10, ec.A + B / (T_C + 273.15 - ec.T0));
    }

    // ---------------- Upred margins ----------------
    // η/ε: coefficient-covariance form (Appendix C-2/C-3)
    function upredVft(model, g, T_C) {
      const gv = basisVft(g);
      const TmT0 = T_C + 273.15 - model.T0;
      const B = vftB(model, gv);
      const x = { A: 1 };
      for (const k of Object.keys(model.B)) x[k] = (gv[k] || 0) / TmT0;
      x.T0 = B / (TmT0 * TmT0);
      const sd = covSd(model === visc ? 'visc' : 'ec', x);
      const p = Math.pow(10, model.A + B / TmT0);
      return Z * sd * Math.LN10 * p;
    }

    function pctNL(gm) {
      let v = 0;
      for (const k of Object.keys(pctLin)) v += pctLin[k] * (gm[k] || 0);
      for (const k of Object.keys(pctQuad)) {
        const [a, b] = k.split('x');
        v += pctQuad[k] * (gm[a] || 0) * (gm[b] || 0);
      }
      return v; // ave ln[NL]
    }

    function upredPct(g, nlv) {
      const gm = basisPct(g);
      const x = {};
      for (const k of pctModeled) x[k] = gm[k] || 0;
      x.Others = gm.Others;
      x['Al2O3xAl2O3'] = gm.Al2O3 * gm.Al2O3;
      x['Al2O3xCaO'] = gm.Al2O3 * gm.CaO;
      const sdModel = covSd('pct', x);
      const sd = Math.sqrt(sdModel * sdModel + rmsePress * rmsePress);
      const NL = Math.exp(nlv);
      return Math.exp(nlv + Z * sd) - NL;
    }

    function upredSo3(g) {
      const gso3 = g.SO3 || 0;
      const gs = basisSo3(g);
      const denom = 1 - gso3;
      const x = {};
      for (const k of Object.keys(so3Lin)) {
        x[k] = denom > 0 ? (gs[k] || 0) / denom : 0;
      }
      x['B2O3xCaO'] = x.B2O3 * x.CaO;
      x['Al2O3xNa2O'] = x.Al2O3 * x.Na2O;
      x['CaOxSiO2'] = x.CaO * x.SiO2;
      return Z * covSd('so3', x);
    }

    function upredK3(g) {
      const gk = basisK3(g);
      const denom = 1 - (g.SO3 || 0) - (g.Cl || 0);
      const x = { 'S0/1': 0 };
      for (const k of Object.keys(k3Lin)) x[k] = denom > 0 ? (gk[k] || 0) / denom : 0;
      x['Fe2O3xFe2O3'] = x.Fe2O3 * x.Fe2O3;
      x['Na2OxCr2O3'] = x.Na2O * x.Cr2O3;
      x['TiO2xNa2O'] = x.TiO2 * x.Na2O;
      x['SiO2xMgO'] = x.SiO2 * x.MgO;
      return Z * covSd('k3', x);
    }

    // ---------------- full evaluation ----------------
    // g: {oxide: mass fraction (sums to 1)}. Returns property values in
    // the same units the paper reports them.
    function evaluate(gIn) {
      let g = gIn;
      const tot = Object.values(gIn).reduce((s, v) => s + v, 0);
      if (Math.abs(tot - 1) > 1e-3) {
        g = {};
        for (const [k, v] of Object.entries(gIn)) g[k] = v / tot;
      }

      // PCT
      const gm = basisPct(g);
      const nlv = pctNL(gm);
      const NL = Math.exp(nlv);

      // VFT η & EC
      const eta1150 = etaAt(g, 1150), eta1100 = etaAt(g, 1100);
      const ec1100 = ecAt(g, 1100), ec1200 = ecAt(g, 1200);

      // Sulfate 3TS (SO3-free PQMM basis), MT = 3TS − 0.33
      const gso3 = g.SO3 || 0;
      const gsBasis = basisSo3(g);
      const sdenom = 1 - gso3;
      let so3 = 0;
      for (const k of Object.keys(so3Lin)) {
        so3 += so3Lin[k] * (sdenom > 0 ? (gsBasis[k] || 0) / sdenom : 0);
      }
      for (const k of Object.keys(so3Cross)) {
        const [a, b] = k.split('x');
        const xa = sdenom > 0 ? (gsBasis[a] || 0) / sdenom : 0;
        const xb = sdenom > 0 ? (gsBasis[b] || 0) / sdenom : 0;
        so3 += so3Cross[k] * xa * xb;
      }

      // K-3 ln[k1208]
      const gk = basisK3(g);
      const kdenom = 1 - gso3 - (g.Cl || 0);
      let lnk = 0;
      for (const k of Object.keys(k3Lin)) lnk += k3Lin[k] * (kdenom > 0 ? (gk[k] || 0) / kdenom : 0);
      for (const k of Object.keys(k3Sq)) {
        const [a, b] = k.split('x');
        const xa = kdenom > 0 ? (gk[a] || 0) / kdenom : 0;
        const xb = kdenom > 0 ? (gk[b] || 0) / kdenom : 0;
        lnk += k3Sq[k] * xa * xb;
      }
      for (const k of Object.keys(k3Cross)) {
        const [a, b] = k.split('x');
        const xa = kdenom > 0 ? (gk[a] || 0) / kdenom : 0;
        const xb = kdenom > 0 ? (gk[b] || 0) / kdenom : 0;
        lnk += k3Cross[k] * xa * xb;
      }
      const k1208 = Math.exp(lnk);

      // Phosphate logistic (6 terms + full-lump Others, no intercept)
      const pTerms = ['CaO', 'Li2O', 'Na2O', 'P2O5', 'SiO2', 'RE2O3'];
      const gp = {};
      for (const k of pTerms) gp[k] = g[k] || 0;
      gp.Others = 1;
      for (const k of pTerms) gp.Others -= gp[k];
      let logit = 0;
      for (const k of Object.keys(pLin)) logit += pLin[k] * (gp[k] || 0);
      for (const k of Object.keys(pCross)) {
        const [a, b] = k.split('x');
        logit += pCross[k] * (gp[a] || 0) * (gp[b] || 0);
      }
      const p_phos = 1 / (1 + Math.exp(-logit));

      // Simple ratios
      const gNa = g.Na2O || 0, gLi = g.Li2O || 0, gB = g.B2O3 || 0, gSi = g.SiO2 || 0;
      const num = gNa + 2.07 * gLi;
      const NNaLi = (num + gB + gSi) > 0 ? num / (num + gB + gSi) : 0;
      const NALK = gNa + 0.66 * (g.K2O || 0) + 2.07 * gLi;
      const NSiAl = gSi + 1.697 * (g.Al2O3 || 0);

      // Upred margins
      const upred = {
        pct: upredPct(g, nlv),
        eta1150: upredVft(visc, g, 1150),
        eta1100: upredVft(visc, g, 1100),
        ec1100: upredVft(ec, g, 1100),
        ec1200: upredVft(ec, g, 1200),
        k1208: upredK3(g),
        wso3: upredSo3(g),
      };

      return {
        NL, ave_ln_nl: nlv,
        eta1150, eta1100, ec1100, ec1200,
        wso3_3ts: so3, wso3_mt: so3 - so3Offset,
        k1208, ln_k1208: lnk,
        p_phos: p_phos, NNaLi, NALK, NSiAl,
        upred,
      };
    }

    return {
      evaluate,
      etaAt, ecAt,
      basisPct, basisVft, basisSo3, basisK3,
      upredVft, upredPct, upredSo3, upredK3,
    };
  }

  return { create };
});
