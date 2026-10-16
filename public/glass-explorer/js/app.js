/**
 * app.js — Glass Property Explorer UI controller.
 *
 * Two modes:
 *   FEED  — sliders drive the full GlassNet chain: feed oxides → WL →
 *           recipe → exact physics-identity glass → 13 properties.
 *   GLASS — sliders drive glass oxides directly through head C (the
 *           website copy) AND the published formulation engine.
 *
 * Both modes overlay the NN prediction with the published
 * formulation (VFT η/κ, PCT NL, ...) so visitors watch the surrogate track
 * the physics. All charts are inline SVG (no libraries, no build step).
 */
'use strict';

const COMMON_OXIDES = ['SiO2', 'Na2O', 'B2O3', 'Al2O3', 'Li2O', 'Fe2O3', 'CaO', 'ZnO', 'ZrO2', 'P2O5'];
const GFC_DISPLAY = ['Silica', 'BoricAcid', 'Na2CO3', 'Li2CO3', 'Kyanite', 'Wollastonite', 'Zircon', 'Zincite', 'Cr2O3', 'V2O5'];

const PROP_ROWS = [
  { col: 'eta1150_Pa_s',   label: 'Viscosity η @1150°C', unit: 'Pa·s',   limit: '4 – 6',     fmt: 3 },
  { col: 'eta1100_Pa_s',   label: 'Viscosity η @1100°C', unit: 'Pa·s',   limit: '≤ 15',      fmt: 3 },
  { col: 'ec1100_S_per_cm',label: 'Conductivity κ @1100°C', unit: 'S/cm', limit: '≥ 0.1',     fmt: 3 },
  { col: 'ec1200_S_per_cm',label: 'Conductivity κ @1200°C', unit: 'S/cm', limit: '≤ 0.7',     fmt: 3 },
  { col: 'pct_NL_g_per_m2',label: 'PCT release (NL)',    unit: 'g/m²',   limit: '≤ 6.44',    fmt: 3 },
  { col: 'k1208_in',       label: 'K-3 corrosion',       unit: 'in',     limit: '≤ 0.04',    fmt: 4 },
  { col: 'wSO3_MT_wt_pct', label: 'Sulfate (MT basis)',  unit: 'wt%',    limit: '—',         fmt: 3 },
  { col: 'p_phosphate',    label: 'Phosphate sep. risk', unit: 'P(fail)',limit: '≤ 0.24',    fmt: 3 },
  { col: 'N_NaLi',         label: 'Immiscibility N(NaLi)',unit: '',      limit: '≥ 0.20',    fmt: 3 },
  { col: 'NALK',           label: 'N(ALK)',              unit: '',       limit: '.138–.274', fmt: 3 },
  { col: 'NSiAl',          label: 'N(SiAl)',             unit: '',       limit: '.457–.724', fmt: 3 },
];

let MODEL = null, PROPS = null, MANIFEST = null;
let MODE = 'feed';
let state = { feed: {}, glass: {}, cn: 0.75, wasteKg: 5e5 };
const DEFAULT_FEED = { SiO2: 2, Al2O3: 28, Na2O: 30, Fe2O3: 7, B2O3: 0.5, CaO: 1, ZrO2: 1, P2O5: 1, K2O: 1, MgO: 0.5, SO3: 0.5, F: 0.3, Li2O: 0.5 };
const DEFAULT_GLASS = {
  // dataset mean glass (3,503 §6.2 campaigns) — ON the training manifold, so
  // Glass mode opens with realistic ~5.7 Pa·s melt and responds smoothly.
  // (An arbitrary "soda-lime-ish" default sits far off the manifold where the
  // property head extrapolates to unphysical values.)
  SiO2: 33.68, Na2O: 22.83, Al2O3: 18.74, B2O3: 13.26, Fe2O3: 2.54,
  CaO: 1.32, ZrO2: 1.29, Li2O: 0.83, V2O5: 0.82, Cr2O3: 0.76,
  Bi2O3: 0.46, ZnO: 0.49, UO3: 0.55, P2O5: 0.64, SO3: 0.31,
  F: 0.22, MnO: 0.24, NiO: 0.21, PbO: 0.13, Cl: 0.15, K2O: 0.19,
  ThO2: 0.12, RE2O3: 0.05, BaO: 0.01, SrO: 0.07,
};

const $ = (id) => document.getElementById(id);

// ---------------- SVG helpers (sandbox pattern) ----------------
const SVGNS = 'http://www.w3.org/2000/svg';
function svgEl(tag, attrs, parent) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
}
function svgFrame(host, W, H, pad) {
  host.innerHTML = '';
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%' });
  host.appendChild(svg);
  return { svg, W, H, cw: W - pad.l - pad.r, ch: H - pad.t - pad.b, pad };
}

// ---------------- data plumbing ----------------
function feedVec() {
  const v = new Float64Array(57);
  MANIFEST.oxides.forEach((o, i) => { v[i] = Math.max(state.feed[o] || 0, 0); });
  const tot = v.reduce((s, x) => s + x, 0);
  if (tot > 0) for (let i = 0; i < 57; i++) v[i] = (v[i] / tot) * 100;
  return v;
}
function glassVec() {
  const v = new Float64Array(57);
  MANIFEST.oxides.forEach((o, i) => { v[i] = Math.max(state.glass[o] || 0, 0); });
  const tot = v.reduce((s, x) => s + x, 0);
  if (tot > 0) for (let i = 0; i < 57; i++) v[i] = (v[i] / tot) * 100;
  return v;
}
function glassDict(g) {
  const d = {};
  MANIFEST.oxides.forEach((o, i) => { if (g[i] > 1e-9) d[o] = g[i] / 100; });
  return d;
}

// ---------------- main recompute + render ----------------
function recompute() {
  let r;
  if (MODE === 'feed') {
    r = MODEL.predict(feedVec(), { cnTarget: state.cn, wasteKg: state.wasteKg });
  } else {
    const g = glassVec();
    const props = MODEL.predictPropsFromGlass(g);
    r = { glass: g, props, wl: null, recipe: null, flags: MODEL.flags(props) };
  }
  const glassDictFull = {};
  for (let i = 0; i < 57; i++) glassDictFull[MANIFEST.oxides[i]] = r.glass[i] / 100;
  const pub = PROPS.evaluate(glassDictFull);

  renderMetrics(r, pub);
  renderVftChart(r, pub);
  renderPropTable(r, pub);
  renderNetworkPanel(r);
  renderInsightTab();
}

// ---------------- metric cards ----------------
function renderMetrics(r, pub) {
  const host = $('metricRow');
  const allPass = pub.eta1150 >= 4 && pub.eta1150 <= 6 && pub.eta1100 <= 15 &&
    pub.ec1100 >= 0.1 && pub.ec1200 <= 0.7 && pub.NL <= 6.4368 &&
    pub.k1208 <= 0.04 && pub.p_phos <= 0.24 && pub.NNaLi >= 0.2;
  const cards = [];
  if (MODE === 'feed') {
    cards.push({ label: 'Waste loading', value: (r.wl * 100).toFixed(1) + '%', sub: 'of glass from the waste', cls: '' });
    const glassT = (state.wasteKg / Math.max(r.wl, 1e-6)) / 1000;
    cards.push({ label: 'Glass from batch', value: glassT.toFixed(1) + ' t', sub: `${state.wasteKg.toLocaleString()} kg waste oxide`, cls: '' });
    let rawTotal = 0;
    for (let k = 0; k < 10; k++) rawTotal += r.recipe[k] / MODEL.gfcYields[MODEL.gfcNames[k]];
    cards.push({ label: 'Raw GFC powder', value: (rawTotal * glassT).toFixed(1) + ' t', sub: 'as-fired formers', cls: '' });
  }
  cards.push({
    label: 'η @1150°C (published)', value: pub.eta1150.toFixed(2),
    sub: `NN: ${r.props.eta1150_Pa_s.toFixed(2)} Pa·s`,
    cls: (pub.eta1150 >= 4 && pub.eta1150 <= 6) ? 'pass' : 'fail',
  });
  cards.push({
    label: 'κ @1100°C (published)', value: pub.ec1100.toFixed(3),
    sub: `NN: ${r.props.ec1100_S_per_cm.toFixed(3)} S/cm`,
    cls: pub.ec1100 >= 0.1 ? 'pass' : 'fail',
  });
  cards.push({
    label: 'PCT release', value: pub.NL.toFixed(2),
    sub: `NN: ${r.props.pct_NL_g_per_m2.toFixed(2)} g/m²`,
    cls: pub.NL <= 6.4368 ? 'pass' : 'fail',
  });
  cards.push({ label: 'Acceptance', value: allPass ? 'PASS' : 'FAIL', sub: 'published acceptance limits', cls: allPass ? 'pass' : 'fail' });
  host.innerHTML = cards.map((c) => `
    <div class="metric ${c.cls}">
      <div class="m-label">${c.label}</div>
      <div class="m-value">${c.value}</div>
      <div class="m-sub">${c.sub}</div>
    </div>`).join('');
}

// ---------------- η(T)/κ(T) chart ----------------
function renderVftChart(r, pub) {
  const host = $('vftChart');
  const W = 640, H = 260, pad = { l: 46, r: 14, t: 14, b: 30 };
  const f = svgFrame(host, W, H, pad);
  const gd = glassDict(r.glass);

  // published curves at 900–1300 °C
  const T0 = 900, T1 = 1300, N = 80;
  const etaPts = [], ecPts = [];
  for (let i = 0; i <= N; i++) {
    const T = T0 + (i * (T1 - T0)) / N;
    etaPts.push([T, PROPS.etaAt(gd, T)]);
    ecPts.push([T, PROPS.ecAt(gd, T)]);
  }
  // log10 y-axis covering both curves + NN points
  let lo = Math.log10(0.05), hi = Math.log10(200);
  const xOf = (T) => f.pad.l + ((T - T0) / (T1 - T0)) * f.cw;
  const yOf = (v) => f.pad.t + (1 - (Math.log10(Math.max(v, 1e-3)) - lo) / (hi - lo)) * f.ch;

  // gridlines: decades
  for (let e = -1; e <= 2; e++) {
    const v = Math.pow(10, e);
    if (v < 0.05 || v > 200) continue;
    const y = yOf(v);
    f.svg.appendChild(svgEl('line', { x1: f.pad.l, x2: f.pad.l + f.cw, y1: y, y2: y, stroke: 'rgba(148,180,220,0.12)', 'stroke-width': 1 }));
    const t = svgEl('text', { x: f.pad.l - 6, y: y + 3, 'text-anchor': 'end' });
    t.textContent = v >= 1 ? String(v) : '0.' + '0'.repeat(-e - 1) + (v * Math.pow(10, -e + 1) >= 1 ? '' : '0') + Math.round(v * Math.pow(10, -e));
    f.svg.appendChild(t);
  }
  // x ticks
  for (const T of [900, 1000, 1100, 1200, 1300]) {
    const x = xOf(T);
    f.svg.appendChild(svgEl('line', { x1: x, x2: x, y1: f.pad.t, y2: f.pad.t + f.ch, stroke: 'rgba(148,180,220,0.08)', 'stroke-width': 1 }));
    const t = svgEl('text', { x, y: f.pad.t + f.ch + 16, 'text-anchor': 'middle' });
    t.textContent = T + '°C';
    f.svg.appendChild(t);
  }
  // 4–6 Pa·s acceptance band at 1150 region (full width, subtle)
  f.svg.appendChild(svgEl('rect', {
    x: f.pad.l, y: yOf(6), width: f.cw, height: yOf(4) - yOf(6),
    fill: 'rgba(52,211,153,0.07)', stroke: 'rgba(52,211,153,0.25)', 'stroke-dasharray': '3 3',
  }));
  const bandT = svgEl('text', { x: f.pad.l + f.cw - 4, y: yOf(6) + 11, 'text-anchor': 'end', 'font-size': 9 });
  bandT.textContent = 'η 4–6 Pa·s band';
  f.svg.appendChild(bandT);

  // published curves
  const path = (pts, yF) => pts.map((p, i) => (i ? 'L' : 'M') + xOf(p[0]).toFixed(1) + ' ' + yF(p[1]).toFixed(1)).join(' ');
  f.svg.appendChild(svgEl('path', { d: path(etaPts, yOf), fill: 'none', stroke: 'var(--pub)', 'stroke-width': 2 }));
  f.svg.appendChild(svgEl('path', { d: path(ecPts, yOf), fill: 'none', stroke: 'var(--pub)', 'stroke-width': 2, 'stroke-dasharray': '6 4', opacity: 0.75 }));

  // NN point predictions (head C) at the three process temperatures
  for (const [col, T, sym] of [['eta1150_Pa_s', 1150, 0], ['eta1100_Pa_s', 1100, 1], ['ec1100_S_per_cm', 1100, 2], ['ec1200_S_per_cm', 1200, 3]]) {
    const v = r.props[col];
    svgEl('circle', { cx: xOf(T), cy: yOf(v), r: 4.5, class: 'nn-marker' }, f.svg);
  }
  // labels for NN points
  const nnT = svgEl('text', { x: xOf(1150), y: yOf(r.props.eta1150_Pa_s) - 9, 'text-anchor': 'middle', fill: 'var(--nn)', 'font-size': 9 });
  nnT.textContent = `NN ${r.props.eta1150_Pa_s.toFixed(2)}`;
  f.svg.appendChild(nnT);

  const axT = svgEl('text', { x: f.pad.l + f.cw / 2, y: H - 2, 'text-anchor': 'middle', class: 'axis-title' });
  axT.textContent = 'temperature (°C) — log scale y: Pa·s and S/cm';
  f.svg.appendChild(axT);
}

// ---------------- property table ----------------
function renderPropTable(r, pub) {
  const tb = $('propTable').querySelector('tbody');
  const pubMap = {
    eta1150_Pa_s: pub.eta1150, eta1100_Pa_s: pub.eta1100,
    ec1100_S_per_cm: pub.ec1100, ec1200_S_per_cm: pub.ec1200,
    pct_NL_g_per_m2: pub.NL, k1208_in: pub.k1208,
    wSO3_MT_wt_pct: pub.wso3_mt, p_phosphate: pub.p_phos,
    N_NaLi: pub.NNaLi, NALK: pub.NALK, NSiAl: pub.NSiAl,
  };
  const checks = {
    eta1150_Pa_s: (v) => v >= 4 && v <= 6, eta1100_Pa_s: (v) => v <= 15,
    ec1100_S_per_cm: (v) => v >= 0.1, ec1200_S_per_cm: (v) => v <= 0.7,
    pct_NL_g_per_m2: (v) => v <= 6.4368, k1208_in: (v) => v <= 0.04,
    p_phosphate: (v) => v <= 0.24, N_NaLi: (v) => v >= 0.2,
  };
  let html = '';
  for (const row of PROP_ROWS) {
    const nn = r.props[row.col];
    const pv = pubMap[row.col];
    if (pv === undefined || !isFinite(pv)) continue;
    const ck = checks[row.col];
    const ok = ck ? ck(pv) : null;
    const rel = Math.abs(nn - pv) / Math.max(Math.abs(pv), 1e-9);
    html += `<tr>
      <td>${row.label} <span class="unit">${row.unit}</span></td>
      <td class="num">${fmt(nn, row.fmt)}</td>
      <td class="num">${fmt(pv, row.fmt)}</td>
      <td class="limit">${row.limit}</td>
      <td class="status ${ok === null ? '' : (ok ? 'pass' : 'fail')}">${ok === null ? '—' : (ok ? 'PASS' : 'FAIL')}</td>
    </tr>`;
  }
  tb.innerHTML = html;
}
function fmt(v, d) {
  if (!isFinite(v)) return '—';
  if (v !== 0 && (Math.abs(v) < 1e-3 || Math.abs(v) >= 1e5)) return v.toExponential(2);
  return v.toFixed(d);
}

// ---------------- network outputs panel ----------------
function renderNetworkPanel(r) {
  const host = $('networkPanel');
  if (MODE === 'feed') {
    // recipe bars + glass composition
    const rec = MODEL.gfcNames.map((g, k) => [g, r.recipe[k]]).sort((a, b) => b[1] - a[1]);
    const max = Math.max(...rec.map((x) => x[1]), 1e-9);
    let html = '<div class="recipe-bars">';
    for (const [g, v] of rec) {
      if (v < 1e-4) continue;
      const rawKg = (v / MODEL.gfcYields[g]) * (state.wasteKg / Math.max(r.wl, 1e-6));
      html += `<div class="recipe-bar"><span>${g}</span>
        <span class="rb-track"><span class="rb-fill" style="width:${(v / max * 100).toFixed(1)}%"></span></span>
        <span class="rb-val">${(v * 100).toFixed(2)}%</span></div>`;
    }
    html += '</div>';
    const tops = MANIFEST.oxides.map((o, i) => [o, r.glass[i]]).filter((x) => x[1] > 0.05).sort((a, b) => b[1] - a[1]).slice(0, 12);
    html += '<div class="glass-comp" style="margin-top:0.8rem">';
    for (const [o, v] of tops) html += `<div><span>${o}</span><span class="gv">${v.toFixed(2)} wt%</span></div>`;
    html += '</div>';
    host.innerHTML = html;
  } else {
    // Glass mode: only the assembled composition (no recipe)
    const tops = MANIFEST.oxides.map((o, i) => [o, r.glass[i]]).filter((x) => x[1] > 0.05).sort((a, b) => b[1] - a[1]);
    let html = '<div class="glass-comp">';
    for (const [o, v] of tops) html += `<div><span>${o}</span><span class="gv">${v.toFixed(2)} wt%</span></div>`;
    html += '</div><p class="caption">Glass-mode sliders set the melt composition directly — head C (the property network) and the published formulations read it as-is. Feed mode instead derives this composition through the full network chain.</p>';
    host.innerHTML = html;
  }
}

// ---------------- insight tabs ----------------
let ACTIVE_TAB = 'flow';
function renderInsightTab() {
  const host = $('tabBody');
  if (MODE === 'glass') {
    host.innerHTML = '<p class="caption">Network-internals views are available in Feed mode (they trace the full chain from waste composition). In Glass mode head C runs directly on your sliders.</p>';
    return;
  }
  const feed = feedVec();
  if (ACTIVE_TAB === 'flow') renderFlow(host, feed);
  else if (ACTIVE_TAB === 'consensus') renderConsensus(host, feed);
  else if (ACTIVE_TAB === 'drivers') renderDrivers(host, feed);
  else renderMap(host, feed);
}

// --- signal flow: strongest inputs → active neurons → heads ---
function renderFlow(host, feed) {
  const r = MODEL.predict(feed, { cnTarget: state.cn, wasteKg: state.wasteKg });
  const W = 900, H = 300, pad = { l: 70, r: 120, t: 20, b: 16 };
  const f = svgFrame(host, W, H, pad);
  const xIn = f.pad.l, xH1 = f.pad.l + 200, xH2 = f.pad.l + 420, xOut = f.pad.l + f.cw;

  // top inputs by |z| (transformed input magnitude)
  const inOrder = Array.from(r.input).map((v, i) => [i, Math.abs(v)]).sort((a, b) => b[1] - a[1]).slice(0, 8);
  // top h1 / h2 activations
  const h1Top = Array.from(r.h1).map((v, i) => [i, Math.abs(v)]).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const h2Top = Array.from(r.h2).map((v, i) => [i, Math.abs(v)]).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const y = (i, n, h) => f.pad.t + ((i + 0.5) / n) * h;
  const nIn = inOrder.length, nH1 = h1Top.length, nH2 = h2Top.length;

  // edges input→h1 and h1→h2 (weight × downstream activation leverage)
  const W1 = MODEL.L['trunk.0'], W2 = MODEL.L['trunk.3'];
  const h1Map = new Map(h1Top.map(([j], loc) => [j, loc]));
  const h2Map = new Map(h2Top.map(([j], loc) => [j, loc]));
  const maxW = [1e-12, 1e-12];
  const edges1 = [], edges2 = [];
  for (const [iLoc, i] of inOrder.entries()) {
    for (const [jLoc, j] of h1Top.entries()) {
      const w = W1.f[j * W1.cols + i] * Math.abs(r.h1[j]);
      edges1.push([iLoc, jLoc, w]); maxW[0] = Math.max(maxW[0], Math.abs(w));
    }
  }
  for (const [iLoc, i] of h1Top.entries()) {
    for (const [jLoc, j] of h2Top.entries()) {
      const w = W2.f[j * W2.cols + i] * Math.abs(r.h2[j]);
      edges2.push([iLoc, jLoc, w]); maxW[1] = Math.max(maxW[1], Math.abs(w));
    }
  }
  for (const [a, b, w] of edges1) {
    svgEl('line', {
      x1: xIn + 8, y1: y(a, nIn, f.ch), x2: xH1 - 8, y2: y(b, nH1, f.ch),
      stroke: w >= 0 ? 'rgba(103,232,249,0.5)' : 'rgba(248,113,113,0.45)',
      'stroke-width': 0.5 + 2.5 * Math.abs(w) / maxW[0], opacity: 0.25 + 0.5 * Math.abs(w) / maxW[0],
    }, f.svg);
  }
  for (const [a, b, w] of edges2) {
    svgEl('line', {
      x1: xH1 + 8, y1: y(a, nH1, f.ch), x2: xH2 - 8, y2: y(b, nH2, f.ch),
      stroke: w >= 0 ? 'rgba(103,232,249,0.5)' : 'rgba(248,113,113,0.45)',
      'stroke-width': 0.5 + 2.2 * Math.abs(w) / maxW[1], opacity: 0.2 + 0.45 * Math.abs(w) / maxW[1],
    }, f.svg);
  }

  // input nodes + labels
  const maxZ = Math.max(...inOrder.map(([, v]) => v));
  for (const [iLoc, i] of inOrder.entries()) {
    const yy = y(iLoc, nIn, f.ch);
    const isOx = i < 57;
    svgEl('circle', {
      cx: xIn, cy: yy, r: 5 + 6 * inOrder[iLoc][1] / maxZ,
      fill: 'var(--nn)', stroke: 'var(--bg)', 'stroke-width': 1, opacity: 0.9,
    }, f.svg);
    const t = svgEl('text', { x: xIn - 10, y: yy + 3, 'text-anchor': 'end' });
    t.textContent = isOx ? MANIFEST.oxides[i] : (i === 57 ? 'C:N' : 'log₁₀ kg');
    f.svg.appendChild(t);
  }
  // hidden nodes
  const a1Max = Math.max(...h1Top.map(([, v]) => v), 1e-9);
  for (const [loc, [j, v]] of h1Top.entries()) {
    svgEl('circle', { cx: xH1, cy: y(loc, nH1, f.ch), r: 4 + 5 * v / a1Max, fill: '#7dd3fc', opacity: 0.85 }, f.svg);
  }
  const a2Max = Math.max(...h2Top.map(([, v]) => v), 1e-9);
  for (const [loc, [j, v]] of h2Top.entries()) {
    svgEl('circle', { cx: xH2, cy: y(loc, nH2, f.ch), r: 4 + 5 * v / a2Max, fill: '#a5b4fc', opacity: 0.85 }, f.svg);
  }
  // head nodes
  const wlY = f.pad.t + f.ch * 0.28, recY = f.pad.t + f.ch * 0.72;
  for (const [loc, j] of h2Top.entries()) {
    const yy = y(loc, nH2, f.ch);
    const wlW = Math.abs(MODEL.L['head_wl.0'].f.reduce((s, _v, idx) => s, 0)); // placeholder, computed below
    svgEl('line', { x1: xH2 + 8, y1: yy, x2: xOut - 90, y2: wlY, stroke: 'rgba(52,211,153,0.35)', 'stroke-width': 1 }, f.svg);
    svgEl('line', { x1: xH2 + 8, y1: yy, x2: xOut - 90, y2: recY, stroke: 'rgba(245,158,11,0.35)', 'stroke-width': 1 }, f.svg);
  }
  svgEl('circle', { cx: xOut - 80, cy: wlY, r: 7, fill: 'var(--ok)', opacity: 0.9 }, f.svg);
  svgEl('circle', { cx: xOut - 80, cy: recY, r: 7, fill: 'var(--pub)', opacity: 0.9 }, f.svg);
  const wlT = svgEl('text', { x: xOut - 66, y: wlY + 4 });
  wlT.textContent = `WL = ${(r.wl * 100).toFixed(1)}%`; wlT.setAttribute('class', 'wl-label');
  f.svg.appendChild(wlT);
  const recT = svgEl('text', { x: xOut - 66, y: recY - 6 });
  recT.textContent = 'recipe head →'; recT.setAttribute('font-size', 9);
  f.svg.appendChild(recT);
  const topRec = MODEL.gfcNames.map((g, k) => [g, r.recipe[k]]).sort((a, b) => b[1] - a[1]).slice(0, 3);
  const recV = svgEl('text', { x: xOut - 66, y: recY + 10 });
  recV.setAttribute('font-size', 9);
  recV.textContent = topRec.map(([g, v]) => `${g} ${(v * 100).toFixed(1)}`).join(' · ');
  f.svg.appendChild(recV);

  // layer captions
  for (const [x, s] of [[xIn, 'inputs (59)'], [xH1, 'hidden 1 (256)'], [xH2, 'hidden 2 (256)']]) {
    const t = svgEl('text', { x, y: f.pad.t - 6, 'text-anchor': 'middle', class: 'axis-title' });
    t.textContent = s; f.svg.appendChild(t);
  }
  const note = document.createElement('p');
  note.className = 'tab-note';
  note.textContent = 'Live signal path for YOUR composition: node size = |activation|, edge width = |weight × downstream activation| (teal = excitatory, red = inhibitory). The trunk feeds both the waste-loading head and the recipe head.';
  host.appendChild(note);
}

// --- MC-dropout consensus ---
function renderConsensus(host, feed) {
  const det = MODEL.predict(feed, { cnTarget: state.cn, wasteKg: state.wasteKg });
  const s = MODEL.consensus(feed, { n: 60, cnTarget: state.cn, wasteKg: state.wasteKg });
  const W = 640, H = 200, pad = { l: 46, r: 16, t: 14, b: 26 };
  const f = svgFrame(host, W, H, pad);
  const vals = s.wl.map((v) => v * 100);
  const lo = Math.min(...vals, det.wl * 100), hi = Math.max(...vals, det.wl * 100);
  const span = Math.max(hi - lo, 1e-6);
  const xOf = (v) => f.pad.l + ((v - lo + 0.08 * span) / (span * 1.16)) * f.cw;

  // histogram, 18 bins
  const nb = 18;
  const bins = new Array(nb).fill(0);
  for (const v of vals) {
    const b = Math.min(nb - 1, Math.max(0, Math.floor(((v - lo + 0.08 * span) / (span * 1.16)) * nb)));
    bins[b]++;
  }
  const bmax = Math.max(...bins, 1);
  const bw = f.cw / nb;
  bins.forEach((c, i) => {
    if (!c) return;
    svgEl('rect', {
      x: f.pad.l + i * bw + 1, y: f.pad.t + f.ch - (c / bmax) * f.ch,
      width: bw - 2, height: (c / bmax) * f.ch,
      fill: 'rgba(103,232,249,0.4)', stroke: 'rgba(103,232,249,0.7)', 'stroke-width': 0.7,
    }, f.svg);
  });
  // deterministic WL line
  const dx = xOf(det.wl * 100);
  svgEl('line', { x1: dx, x2: dx, y1: f.pad.t, y2: f.pad.t + f.ch, stroke: 'var(--ok)', 'stroke-width': 2 }, f.svg);
  const dt = svgEl('text', { x: dx + 5, y: f.pad.t + 12, fill: 'var(--ok)' });
  dt.textContent = `reported ${(det.wl * 100).toFixed(1)}%`;
  f.svg.appendChild(dt);
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  const sd = Math.sqrt(vals.reduce((a, v) => a + (v - mean) ** 2, 0) / vals.length);
  const mT = svgEl('text', { x: f.pad.l + f.cw - 4, y: f.pad.t + 12, 'text-anchor': 'end' });
  mT.textContent = `MC-dropout σ = ±${sd.toFixed(2)} wt% · 60 passes`;
  f.svg.appendChild(mT);
  const ax = svgEl('text', { x: f.pad.l + f.cw / 2, y: H - 4, 'text-anchor': 'middle', class: 'axis-title' });
  ax.textContent = 'waste loading (%)';
  f.svg.appendChild(ax);

  const note = document.createElement('p');
  note.className = 'tab-note';
  note.textContent = 'Each pass randomly mutes 5% of the network\'s internal links (dropout in inference mode) and recomputes the full chain. A tight histogram means many independent internal paths agree on this answer; a wide one flags a composition where the net is unsure.';
  host.appendChild(note);
}

// --- drivers: finite-difference ∂WL/∂input ---
function renderDrivers(host, feed) {
  const g = MODEL.gradient(feed, { cnTarget: state.cn, wasteKg: state.wasteKg });
  const pairs = Array.from(g.grad).map((v, i) => ({
    name: i < 57 ? MANIFEST.oxides[i] : (i === 57 ? 'C:N target' : 'log₁₀ kg'),
    v, raw: i < 57 ? feed[i] : null,
  })).filter((p) => p.raw === null || p.raw > 0.01);
  pairs.sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
  const top = pairs.slice(0, 10);
  const W = 640, H = 30 + top.length * 26 + 10;
  const pad = { l: 90, r: 60, t: 8, b: 8 };
  const f = svgFrame(host, W, H, pad);
  const m = Math.max(...top.map((p) => Math.abs(p.v)), 1e-12);
  const mid = f.pad.l + f.cw / 2;
  top.forEach((p, i) => {
    const yy = 20 + i * 26;
    const w = (Math.abs(p.v) / m) * (f.cw / 2 - 10);
    svgEl('rect', {
      x: p.v >= 0 ? mid : mid - w, y: yy, width: Math.max(w, 1), height: 16,
      fill: p.v >= 0 ? 'rgba(248,113,113,0.75)' : 'rgba(96,165,250,0.75)', rx: 2,
    }, f.svg);
    const t = svgEl('text', { x: f.pad.l - 8, y: yy + 12, 'text-anchor': 'end' });
    t.textContent = p.name; f.svg.appendChild(t);
    const v = svgEl('text', { x: p.v >= 0 ? mid + w + 5 : mid - w - 5, y: yy + 12, 'text-anchor': p.v >= 0 ? 'start' : 'end' });
    v.textContent = (p.v >= 0 ? '+' : '') + p.v.toExponential(1);
    f.svg.appendChild(v);
  });
  const z = svgEl('line', { x1: mid, x2: mid, y1: f.pad.t, y2: f.pad.t + f.ch, stroke: 'var(--border-strong)', 'stroke-width': 1 }, f.svg);
  const cap = svgEl('text', { x: mid, y: H - 1, 'text-anchor': 'middle', class: 'axis-title' });
  cap.textContent = '∂WL/∂input in transformed space  (red: raises waste loading, blue: lowers it)';
  f.svg.appendChild(cap);
  const note = document.createElement('p');
  note.className = 'tab-note';
  note.textContent = 'True sensitivity of the waste-loading head to each input, by central finite differences through the network (matches autograd to ranking precision). Only oxides present in your feed are shown.';
  host.appendChild(note);
}

// --- data-space map: PCA of 3503 training feeds + your star ---
function renderMap(host, feed) {
  const pca = MANIFEST.pca;
  const W = 640, H = 380, pad = { l: 46, r: 16, t: 14, b: 30 };
  const f = svgFrame(host, W, H, pad);
  // project feed
  let zs = new Float64Array(57);
  for (let i = 0; i < 57; i++) zs[i] = (feed[i] - pca.mean[i]) / pca.std[i];
  const xy = [0, 0];
  for (let k = 0; k < 2; k++) {
    let s = 0;
    for (let i = 0; i < 57; i++) s += zs[i] * pca.Vt[k][i];
    xy[k] = s;
  }
  // scales from cloud
  let xlo = 1e9, xhi = -1e9, ylo = 1e9, yhi = -1e9;
  for (const p of pca.pts) { xlo = Math.min(xlo, p[0]); xhi = Math.max(xhi, p[0]); ylo = Math.min(ylo, p[1]); yhi = Math.max(yhi, p[1]); }
  const sx = f.cw / (xhi - xlo), sy = f.ch / (yhi - ylo);
  const X = (v) => f.pad.l + (v - xlo) * sx;
  const Y = (v) => f.pad.t + (yhi - v) * sy;
  // cloud colored by eta1150 (thermal-ish: blue low → red high)
  const eLo = Math.min(...pca.eta), eHi = Math.max(...pca.eta);
  pca.pts.forEach((p, i) => {
    const t = (pca.eta[i] - eLo) / Math.max(eHi - eLo, 1e-9);
    svgEl('circle', {
      cx: X(p[0]), cy: Y(p[1]), r: 2,
      fill: `hsl(${(1 - t) * 230}, 70%, ${45 + t * 15}%)`, opacity: 0.55,
    }, f.svg);
  });
  // your star
  svgEl('path', {
    d: starPath(X(xy[0]), Y(xy[1]), 9),
    fill: '#a3e635', stroke: '#0f1c2e', 'stroke-width': 1,
  }, f.svg);
  const st = svgEl('text', { x: X(xy[0]), y: Y(xy[1]) - 12, 'text-anchor': 'middle', fill: '#a3e635', 'font-size': 10, 'font-weight': 700 });
  st.textContent = 'YOUR FEED';
  f.svg.appendChild(st);
  const ax = svgEl('text', { x: f.pad.l + f.cw / 2, y: H - 4, 'text-anchor': 'middle', class: 'axis-title' });
  ax.textContent = `PC1 (${(pca.var[0] * 100).toFixed(0)}% var) × PC2 (${(pca.var[1] * 100).toFixed(0)}%) — colored by training η₁₁₅₀`;
  f.svg.appendChild(ax);
  const note = document.createElement('p');
  note.className = 'tab-note';
  note.textContent = 'All 3,503 training feed compositions projected to their two strongest principal components (color = that blend\'s melt viscosity). A star far outside the cloud means your feed is an extrapolation — treat predictions with caution.';
  host.appendChild(note);
}
function starPath(cx, cy, R) {
  let d = '';
  for (let i = 0; i < 10; i++) {
    const r = i % 2 === 0 ? R : R * 0.45;
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    d += (i ? 'L' : 'M') + (cx + r * Math.cos(a)).toFixed(1) + ' ' + (cy + r * Math.sin(a)).toFixed(1);
  }
  return d + 'Z';
}

// ---------------- sliders ----------------
function buildSliders() {
  const host = $('sliderHost');
  const isFeed = MODE === 'feed';
  const dict = isFeed ? state.feed : state.glass;
  const keys = isFeed ? COMMON_OXIDES : COMMON_OXIDES;
  // For feed mode include a few waste-specific species; for glass mode keep it compact
  const extraFeed = ['K2O', 'MgO', 'SO3', 'F'];
  const list = isFeed ? keys.concat(extraFeed)
    : ['SiO2', 'Na2O', 'Al2O3', 'B2O3', 'Fe2O3', 'ZrO2', 'Li2O', 'CaO',
       'Cr2O3', 'V2O5', 'ZnO', 'P2O5'];
  let html = '';
  for (const o of list) {
    const max = o === 'SiO2' || o === 'Na2O' ? 60 : 40;
    html += `<div class="slider-row${!isFeed ? ' gfc' : ''}" data-ox="${o}">
      <div class="slider-label"><span>${o}</span><span class="val">${(dict[o] || 0).toFixed(2)} wt%</span></div>
      <input type="range" min="0" max="${max}" step="0.05" value="${dict[o] || 0}" data-ox="${o}">
    </div>`;
  }
  if (isFeed) {
    // minor-species editable number list
    const minors = Object.keys(state.feed).filter((o) => !list.includes(o) && state.feed[o] > 0);
    if (minors.length) {
      html += '<details class="adv" style="margin-top:0.6rem"><summary>Minor species in feed</summary>';
      for (const o of minors) {
        html += `<div class="slider-row" data-ox="${o}">
          <div class="slider-label"><span>${o}</span><span class="val">${state.feed[o].toFixed(2)} wt%</span></div>
          <input type="range" min="0" max="5" step="0.01" value="${state.feed[o]}" data-ox="${o}">
        </div>`;
      }
      html += '</details>';
    }
  }
  host.innerHTML = html;
  host.querySelectorAll('input[type=range]').forEach((inp) => {
    inp.addEventListener('input', () => {
      const o = inp.dataset.ox;
      (MODE === 'feed' ? state.feed : state.glass)[o] = parseFloat(inp.value);
      const row = inp.closest('.slider-row');
      row.querySelector('.val').textContent = parseFloat(inp.value).toFixed(2) + ' wt%';
      scheduleUpdate();
    });
  });
  // sum row
  updateSumRow();
}
function updateSumRow() {
  const dict = MODE === 'feed' ? state.feed : state.glass;
  const tot = Object.values(dict).reduce((s, v) => s + Math.max(v, 0), 0);
  $('sumRow').textContent = MODE === 'feed'
    ? `Feed sum: ${tot.toFixed(1)} wt% → renormalized to 100 before the network`
    : `Glass sum: ${tot.toFixed(1)} wt% → renormalized to 100 (balance = oxygen + minor oxides at 0)`;
  $('advHint').textContent = MODE === 'feed'
    ? 'Composition, recipe and properties are batch-size invariant; the mass only scales reported tonnage.'
    : 'Glass mode bypasses heads A/B — CN and waste mass affect nothing here except the mass readouts in feed mode.';
}

// ---------------- presets ----------------
function applyPreset(name) {
  const p = MANIFEST.presets.find((x) => x.name === name);
  if (!p) return;
  state.feed = {};
  // preset feeds are already in wt% (exporter stores dataset feed_pct values)
  for (const [o, v] of Object.entries(p.feed)) state.feed[o] = v;
  state.cn = p.cn;
  $('cnInput').value = p.cn;
  buildSliders();
  scheduleUpdate();
}

// ---------------- events ----------------
let updateTimer = null;
function scheduleUpdate() {
  if (updateTimer) return;
  updateTimer = setTimeout(() => { updateTimer = null; recompute(); }, 60);
}

function setMode(m) {
  MODE = m;
  $('btnFeed').classList.toggle('active', m === 'feed');
  $('btnGlass').classList.toggle('active', m === 'glass');
  $('inputTitle').textContent = m === 'feed' ? 'Waste feed composition' : 'Glass composition';
  $('presets').style.display = m === 'feed' ? '' : 'none';
  $('networkTitle').textContent = m === 'feed' ? 'Network outputs — recipe & glass' : 'Glass composition (head C input)';
  buildSliders();
  recompute();
}

function init() {
  fetch('data/glassnet.json')
    .then((r) => r.json())
    .then(async (manifest) => {
      MANIFEST = manifest;
      const res = await fetch('data/glassnet.bin');
      const buf = await res.arrayBuffer();
      MODEL = new GlassNet.Model(buf, MANIFEST);
      PROPS = GlassProps.create(MANIFEST.prop_models, MANIFEST.covariance);

      // state defaults
      state.feed = { ...DEFAULT_FEED };
      state.glass = { ...DEFAULT_GLASS };
      state.cn = parseFloat($('cnInput').value);
      state.wasteKg = parseFloat($('wasteKgInput').value);

      // presets dropdown
      const sel = $('presetSelect');
      sel.innerHTML = '<option value="">— choose a training feed —</option>' +
        MANIFEST.presets.map((p) => `<option value="${p.name}">${p.name} · η ${p.eta1150} Pa·s</option>`).join('');
      sel.addEventListener('change', () => applyPreset(sel.value));

      $('cnInput').addEventListener('input', () => { state.cn = parseFloat($('cnInput').value) || 0; scheduleUpdate(); });
      $('wasteKgInput').addEventListener('input', () => { state.wasteKg = parseFloat($('wasteKgInput').value) || 1e5; scheduleUpdate(); });

      $('btnFeed').addEventListener('click', () => setMode('feed'));
      $('btnGlass').addEventListener('click', () => setMode('glass'));

      document.querySelectorAll('.tab').forEach((t) => {
        t.addEventListener('click', () => {
          document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
          t.classList.add('active');
          ACTIVE_TAB = t.dataset.tab;
          renderInsightTab();
        });
      });

      setMode('feed');
    })
    .catch((e) => {
      document.body.innerHTML = `<div style="padding:2rem;font-family:sans-serif">
        <h2>Model failed to load</h2><p>${e}</p>
        <p>Serve this folder over HTTP (e.g. <code>python3 -m http.server</code>) — fetch() cannot read file:// URLs.</p></div>`;
    });
}

document.addEventListener('DOMContentLoaded', init);
