/**
 * glassnet.js — GlassNet 3-head MLP inference in the browser (no libraries).
 *
 * Architecture (GlassNet production training repo, trained 2026-10-15):
 *   trunk:       59 -> 256 -> 256   (Linear, SiLU, Dropout ×2; eval = identity)
 *   head A (WL): 256 -> 64 -> 1
 *   head B (rec): (256+1) -> 128 -> 128 -> 10
 *   head C (prop):57 -> 256 -> 256 -> 128 -> 13
 *
 * Inputs are quantile-transformed to Gaussian — a faithful port of sklearn's
 * QuantileTransformer (normal output), including its two-sided interpolation
 * for duplicated quantiles and its sigma-clip.  Φ⁻¹ comes from an exported
 * scipy-computed grid (uniform in z; linear interpolation error ≤ 1e-7).
 * Head-C outputs are de-standardized then back-transformed (log1p / log10).
 *
 * Glass composition is NOT a network output: it is assembled analytically
 * via the verified physics identity  glass_i = WL·feed_i + Σ xₖ·eₖ[i]·100,
 * so Σ glass = 100 wt% and Σ xₖ = 1−WL hold EXACTLY for any network output.
 *
 * Blob layout (tools/export_model.py), back-to-back little-endian:
 *   f32 per layer (W row-major rows×cols, then b rows) for keys
 *     trunk.0, trunk.3, head_wl.0, head_wl.3, head_recipe.0, head_recipe.3,
 *     head_recipe.6, head_props.0, head_props.3, head_props.6, head_props.9
 *   f64 qt quantiles (nq × 59, column j at offset j·nq), qt references (nq),
 *   f64 ppf grid u-nodes (ppfN, ascending), f64 clip (2),
 *   f64 glass center (57), glass scale (57), prop center (13), prop scale (13).
 * Manifest carries: layer dims, ppf {z0, dz, n}, oxide/GFC/prop names, etc.
 *
 * Browser: <script src> sets window.GlassNet; Node: module.exports.
 */
'use strict';

(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory();
  else root.GlassNet = factory();
})(typeof self !== 'undefined' ? self : this, function () {

  // ---------------- layer view over the buffer ----------------------
  function Mat(buf, off, rows, cols) {
    this.rows = rows; this.cols = cols;
    this.f = new Float32Array(buf, off, rows * cols);
    this.bOff = off + rows * cols * 4;
    this.b = new Float32Array(buf, this.bOff, rows);
    this.end = this.bOff + rows * 4;
  }

  const silu = (x) => (x >= 0 ? x / (1 + Math.exp(-x)) : (Math.exp(x) / (1 + Math.exp(x))) * x);

  // y = act(W·x + b), W row-major (row r = destination unit)
  function affine(W, x, y, act) {
    const f = W.f;
    for (let r = 0; r < W.rows; r++) {
      let s = W.b[r];
      const or_ = r * W.cols;
      for (let c = 0; c < W.cols; c++) s += f[or_ + c] * x[c];
      y[r] = act ? act(s) : s;
    }
  }

  // ---------------- np.interp (piecewise-linear, clamped) -----------
  // xp must be ascending. numpy semantics: interior ties return the fp of
  // the LAST tied node, so the left clamp must be STRICT (x < xp[0]) —
  // feed tables have long runs of duplicated quantiles (zero oxides) where
  // an inclusive clamp silently picks the wrong reference. Above range
  // clamps to fp[n-1] (== last tie, so inclusive is fine).
  function interp(x, xp, fp) {
    const n = xp.length;
    if (x < xp[0]) return fp[0];
    if (x >= xp[n - 1]) return fp[n - 1];
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      const m = (lo + hi) >>> 1;
      if (xp[m] <= x) lo = m; else hi = m;
    }
    const t = (x - xp[lo]) / (xp[hi] - xp[lo]);
    return fp[lo] + t * (fp[hi] - fp[lo]);
  }

  // ---------------- model ----------------
  class Model {
    constructor(buf, manifest) {
      const M = manifest;
      this.oxides = M.oxides;               // 57 input-order oxide names
      this.oxIdx = new Map(this.oxides.map((o, i) => [o, i]));
      this.propCols = M.net.prop_cols;       // 13 property column names
      this.propTransforms = M.net.prop_transforms;
      this.gfcNames = M.gfc.names;           // 10 GFCs (Silica = index 5)
      this.E = M.gfc.E;                      // 10 × 57 normalized oxide splits
      this.gfcYields = M.gfc.yields;
      this.acceptance = M.prop_models.limits;

      // ---- layers (f32) ----
      let off = 0;
      this.L = {};
      for (const key of Object.keys(M.net.layers)) {
        const dims = M.net.layers[key];
        this.L[key] = new Mat(buf, off, dims.rows, dims.cols);
        off = this.L[key].end;
      }

      // ---- quantile transformer tables (f64) ----
      const nq = M.net.qt_quantiles_shape[0];
      this.qtCols = [];
      for (let j = 0; j < 59; j++) {
        this.qtCols.push(new Float64Array(buf, off + j * nq * 8, nq));
      }
      off += 59 * nq * 8;
      this.refs = new Float64Array(buf, off, nq); off += nq * 8;

      // negated reversed copies for the two-sided tie interpolation
      // (sklearn: np.interp(-X, -quantiles[::-1], -references_[::-1]))
      this.revQ = this.qtCols.map((q) => {
        const r = new Float64Array(nq);
        for (let i = 0; i < nq; i++) r[i] = -q[nq - 1 - i];
        return r;
      });
      this.revRefs = new Float64Array(nq);
      for (let i = 0; i < nq; i++) this.revRefs[i] = -this.refs[nq - 1 - i];

      // ---- clip bounds (f64, written BEFORE the ppf grid) then ppf grid ----
      const clip = new Float64Array(buf, off, 2); off += 16;
      this.clipLo = clip[0]; this.clipHi = clip[1];
      const ppf = M.net.ppf;
      this.ppfU = new Float64Array(buf, off, ppf.n); off += ppf.n * 8;
      this.ppfZ0 = ppf.z0; this.ppfDz = ppf.dz; this.ppfN = ppf.n;

      // ---- scalers (f64) ----
      const f64 = (n) => { const a = new Float64Array(buf, off, n); off += n * 8; return a; };
      this.gCenter = f64(57); this.gScale = f64(57);
      this.pCenter = f64(13); this.pScale = f64(13);

      // ---- scratch ----
      this._x = new Float64Array(59);
      this._h1 = new Float64Array(256); this._h2 = new Float64Array(256);
      this._wlh = new Float64Array(64); this._wl1 = new Float64Array(1);
      this._recin = new Float64Array(257);
      this._r1 = new Float64Array(128); this._r2 = new Float64Array(128);
      this._logits = new Float64Array(10);
      this._g57 = new Float64Array(57);
      this._p1 = new Float64Array(256); this._p2 = new Float64Array(256);
      this._p3 = new Float64Array(128); this._pout = new Float64Array(13);
    }

    // Φ⁻¹(u) via the exported scipy grid: linear in z between u-nodes.
    // Nodes are uniform in z, so the interpolation error is uniformly tiny
    // (verified < 1e-7 against scipy.stats.norm.ppf in the parity suite).
    normPpf(u) {
      const U = this.ppfU;
      if (u <= U[0]) return this.ppfZ0;
      if (u >= U[this.ppfN - 1]) return this.ppfZ0 + (this.ppfN - 1) * this.ppfDz;
      let lo = 0, hi = this.ppfN - 1;
      while (hi - lo > 1) {
        const m = (lo + hi) >>> 1;
        if (U[m] <= u) lo = m; else hi = m;
      }
      const t = (u - U[lo]) / (U[hi] - U[lo]);
      return this.ppfZ0 + (lo + t) * this.ppfDz;
    }

    // sklearn QuantileTransformer(output='normal') transform, in place on a
    // 59-row. Faithful to sklearn's _transform_col:
    //   u = 0.5·(interp(x, q, refs) − interp(−x, −q↓, −r↓))   (tie-safe)
    //   z = Φ⁻¹(u), then clip to the exported sigma bounds
    // Bounds flags replicate sklearn exactly: X arrives as float32 (the f32
    // cast in buildInputs) and numpy's NEP-50 keeps `X + 1e-7` in FLOAT32 —
    // the addition rounds back to X for magnitudes ≳ 0.7, so a value EQUAL
    // to the last quantile does NOT fire the upper flag (verified vs sklearn
    // on a preset SiO2 edge case: f64 comparison clips whole-σ wrongly).
    // JS: fround the sum, then compare in f64.
    _qtTransform(x) {
      const nq = this.refs.length;
      for (let j = 0; j < 59; j++) {
        const q = this.qtCols[j];
        const xv = x[j];
        if (Math.fround(xv - 1e-7) < q[0]) { x[j] = this.clipLo; continue; }
        if (Math.fround(xv + 1e-7) > q[nq - 1]) { x[j] = this.clipHi; continue; }
        const u = 0.5 * (interp(xv, q, this.refs)
          - interp(-xv, this.revQ[j], this.revRefs));
        let z = this.normPpf(u);
        if (z < this.clipLo) z = this.clipLo; else if (z > this.clipHi) z = this.clipHi;
        x[j] = z;
      }
    }

    // oxide wt% vector (57, model order) + cn + log10(waste kg) -> input row.
    // Math.fround replicates production's np.float32 cast EXACTLY — the
    // float32 rounding is not cosmetic: it snaps values onto duplicated
    // quantile nodes (zero-oxide runs), which changes the interpolation
    // interval and thus the transformed z by up to ~0.2σ.  Verified against
    // sklearn in tests/parity.js.
    buildInputs(feedWtPct, cnTarget, wasteKg) {
      const x = new Float64Array(59);
      for (let i = 0; i < 57; i++) x[i] = Math.fround(feedWtPct[i]);
      x[57] = Math.fround(cnTarget);
      x[58] = Math.fround(Math.log10(Math.max(wasteKg, 1e-3)));
      this._qtTransform(x);
      return x;
    }

    // trunk activations: h1 = SiLU(W1·x+b1); h2 = W2·h1+b2 RAW.
    // mlp([59,256,256]) = [Linear, SiLU, Dropout, Linear] — the final
    // Linear has NO activation after it (torch: act only when i < len−2;
    // state_dict keys trunk.0/trunk.3 make this visible). insights.py reads
    // h2 = lin2(h1) directly. Applying SiLU here silently corrupts WL.
    trunk(x, h1, h2) {
      h1 = h1 || this._h1; h2 = h2 || this._h2;
      affine(this.L['trunk.0'], x, h1, silu);
      affine(this.L['trunk.3'], h1, h2, null);
      return h2;
    }

    // full chain: feed -> WL -> recipe -> physics-identity glass -> props
    // feedWtPct: array-like(57) in model oxide order, renormalized to 100
    // by the caller.  opts: {cnTarget=0.75, wasteKg=1e5}
    predict(feedWtPct, opts) {
      const o = opts || {};
      const cnTarget = o.cnTarget === undefined ? 0.75 : o.cnTarget;
      const wasteKg = o.wasteKg === undefined ? 1e5 : o.wasteKg;
      const x = this.buildInputs(feedWtPct, cnTarget, wasteKg);

      this.trunk(x);
      affine(this.L['head_wl.0'], this._h2, this._wlh, silu);
      affine(this.L['head_wl.3'], this._wlh, this._wl1, null);
      const wl = this._wl1[0];

      // recipe head on (h2 ⊕ wl)
      this._recin.set(this._h2);
      this._recin[256] = wl;
      affine(this.L['head_recipe.0'], this._recin, this._r1, silu);
      affine(this.L['head_recipe.3'], this._r1, this._r2, silu);
      affine(this.L['head_recipe.6'], this._r2, this._logits, null);

      // sigmoid(+ε)-renormalized decode: Σ xₖ = 1−WL exactly, xₖ ≥ 0
      const recipe = new Float64Array(10);
      let sum = 0;
      for (let k = 0; k < 10; k++) { recipe[k] = 1 / (1 + Math.exp(-this._logits[k])) + 1e-4; sum += recipe[k]; }
      for (let k = 0; k < 10; k++) recipe[k] = (recipe[k] / sum) * (1 - wl);

      // exact physics identity: glass_i = WL·feed_i + Σ xₖ·eₖ[i]·100
      const glass = new Float64Array(57);
      for (let i = 0; i < 57; i++) glass[i] = wl * feedWtPct[i];
      for (let k = 0; k < 10; k++) {
        const xk = recipe[k], row = this.E[k];
        for (let i = 0; i < 57; i++) glass[i] += xk * row[i] * 100.0;
      }

      const props = this.predictPropsFromGlass(glass);
      return {
        wl, recipe, glass, props,
        flags: this.flags(props),
        input: x, h1: this._h1, h2: this._h2,
      };
    }

    // glass wt% (57) -> 13 properties.  Glass mode + property curves use
    // this; per-column transforms are inverted at the end.
    predictPropsFromGlass(glassWtPct) {
      for (let i = 0; i < 57; i++) {
        this._g57[i] = (glassWtPct[i] - this.gCenter[i]) / this.gScale[i];
      }
      affine(this.L['head_props.0'], this._g57, this._p1, silu);
      affine(this.L['head_props.3'], this._p1, this._p2, silu);
      affine(this.L['head_props.6'], this._p2, this._p3, silu);
      affine(this.L['head_props.9'], this._p3, this._pout, null);
      const out = {};
      for (let j = 0; j < 13; j++) {
        const c = this.propCols[j];
        let v = this._pout[j] * this.pScale[j] + this.pCenter[j];
        const mode = this.propTransforms[c];
        if (mode === 'log1p') v = Math.expm1(v);
        else if (mode === 'log10') v = Math.pow(10, v);
        out[c] = v;
      }
      return out;
    }

    // acceptance flags at the published raw limits (dataset flag basis)
    flags(props) {
      const f = {};
      for (const c of Object.keys(this.acceptance)) {
        const lim = this.acceptance[c];
        const v = props[c];
        if (v === undefined) { f[c] = null; continue; }
        f[c] = (lim[0] === null || v >= lim[0]) && (lim[1] === null || v <= lim[1]);
      }
      return f;
    }

    // MC-dropout consensus: n stochastic passes with dropout ACTIVE at
    // inference.  Dropout sits on the post-SiLU hidden activations (torch
    // nn.Dropout after each activation, as in models.py's mlp()), kept
    // values scaled by 1/(1−p) (inverted dropout = train-mode semantics).
    // Each pass redraws masks — the trunk is recomputed per pass, matching
    // the Python consensus() which re-runs forward_wl per sample.
    // Returns {wl[], eta1150[], xSilica[]} samples.
    consensus(feedWtPct, opts) {
      const o = opts || {};
      const cnTarget = o.cnTarget === undefined ? 0.75 : o.cnTarget;
      const wasteKg = o.wasteKg === undefined ? 1e5 : o.wasteKg;
      const n = o.n === undefined ? 50 : o.n;
      const p = 0.05;               // training dropout rate
      const scale = 1 / (1 - p);

      let seed = (o.seed === undefined ? 123456789 : o.seed) >>> 0;
      const rand = () => {           // xorshift32
        seed ^= seed << 13; seed >>>= 0;
        seed ^= seed >>> 17;
        seed ^= seed << 5;  seed >>>= 0;
        return seed / 4294967296;
      };
      const drop = (src) => {
        const m = new Float64Array(src.length);
        for (let i = 0; i < src.length; i++) m[i] = rand() < p ? 0 : src[i] * scale;
        return m;
      };

      const wlArr = [], etaArr = [], silArr = [];
      const x = this.buildInputs(feedWtPct, cnTarget, wasteKg);
      const h1 = new Float64Array(256), h2 = new Float64Array(256);
      const wlh = new Float64Array(64), wl1 = new Float64Array(1);
      const recin = new Float64Array(257);
      const r1 = new Float64Array(128), r2 = new Float64Array(128), lg = new Float64Array(10);
      const p1 = new Float64Array(256), p2 = new Float64Array(256);
      const p3 = new Float64Array(128), po = new Float64Array(13);
      const g57 = new Float64Array(57);

      for (let s = 0; s < n; s++) {
        affine(this.L['trunk.0'], x, h1, silu);
        const h1d = drop(h1);           // dropout after trunk layer 1 act
        affine(this.L['trunk.3'], h1d, h2, silu);
        const h2d = h2;                  // trunk output: Linear LAST, no dropout
        affine(this.L['head_wl.0'], h2d, wlh, silu);
        affine(this.L['head_wl.3'], drop(wlh), wl1, null);
        const wl = wl1[0];
        wlArr.push(wl);

        recin.set(h2d); recin[256] = wl;
        affine(this.L['head_recipe.0'], recin, r1, silu);
        affine(this.L['head_recipe.3'], drop(r1), r2, silu);
        affine(this.L['head_recipe.6'], drop(r2), lg, null);
        let sum = 0; const xr = new Float64Array(10);
        for (let k = 0; k < 10; k++) { xr[k] = 1 / (1 + Math.exp(-lg[k])) + 1e-4; sum += xr[k]; }
        for (let k = 0; k < 10; k++) xr[k] = (xr[k] / sum) * (1 - wl);
        silArr.push(xr[5]); // Silica = gfcNames[5]

        const glass = new Float64Array(57);
        for (let i = 0; i < 57; i++) glass[i] = wl * feedWtPct[i];
        for (let k = 0; k < 10; k++) {
          const xk = xr[k], row = this.E[k];
          for (let i = 0; i < 57; i++) glass[i] += xk * row[i] * 100.0;
        }
        for (let i = 0; i < 57; i++) g57[i] = (glass[i] - this.gCenter[i]) / this.gScale[i];
        affine(this.L['head_props.0'], g57, p1, silu);
        affine(this.L['head_props.3'], drop(p1), p2, silu);
        affine(this.L['head_props.6'], drop(p2), p3, silu);
        affine(this.L['head_props.9'], drop(p3), po, null);
        // eta1150 = propCols[0]; identity transform in training space
        etaArr.push(po[0] * this.pScale[0] + this.pCenter[0]);
      }
      return { wl: wlArr, eta1150: etaArr, xSilica: silArr };
    }

    // ∂WL/∂input by central finite differences in transformed input space
    // (the net is smooth; h=1e-3 central differences match autograd to
    // well within ranking noise).
    gradient(feedWtPct, opts) {
      const o = opts || {};
      const cnTarget = o.cnTarget === undefined ? 0.75 : o.cnTarget;
      const wasteKg = o.wasteKg === undefined ? 1e5 : o.wasteKg;
      const h = 1e-3;
      const wlAt = (row) => {
        this.trunk(row);
        affine(this.L['head_wl.0'], this._h2, this._wlh, silu);
        affine(this.L['head_wl.3'], this._wlh, this._wl1, null);
        return this._wl1[0];
      };
      const base = this.buildInputs(feedWtPct, cnTarget, wasteKg);
      const grad = new Float64Array(59);
      for (let j = 0; j < 59; j++) {
        const xp = new Float64Array(base), xm = new Float64Array(base);
        xp[j] += h; xm[j] -= h;
        grad[j] = (wlAt(xp) - wlAt(xm)) / (2 * h);
      }
      return { grad, base, oxides: this.oxides };
    }
  }

  return { Model, interp };
});
