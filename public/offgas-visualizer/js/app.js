/* Off-gas capture visualizer — UI wiring (client-side only).
 * Requires window.OG_BASIS (js/data.js) and OG_ENGINE (js/engine.js).
 *
 * DOM policy: the stage cards and their sliders are built ONCE at load.
 * Input events recompute the engine and update EXISTING text nodes and
 * tables (refresh()).  Never rebuild the rail on an input event —
 * destroying a range input mid-drag snaps it back to its default and
 * the slider appears locked. */
"use strict";

const B = window.OG_BASIS;
const E = window.OG_ENGINE;

/* ------------------------------------------------ stage definitions ---- */
/* Slider seeds come from the facility model's SME data (units/*.yaml). */
const STAGE_DEFS = [
  { id: "sbs", title: "SBS Scrubber", cond: "quench → 100 °F, saturated; −35 in WC",
    groups: [
      ["particulate", "Particulate (glass dust)", 90, 3],
      ["HCl", "HCl", 30, 3],
      ["HF", "HF", 20, 3],
      ["SO2", "SO₂", 30, 3],
      ["NO", "NO", 2, 3],
      ["NO2", "NO₂", 2, 3],
      ["Hg", "Mercury (Hg)", 1, 3],
      ["semivolatile", "Semivolatiles (Tc, Cs, I, Br, Se, Li)", 3, 3],
    ] },
  { id: "wesp", title: "WESP (wet electrostatic precipitator)", cond: "→ 100 °F; 300 SCFM air injection",
    groups: [
      ["particulate", "Particulate", 98, 3],
      ["HCl", "HCl", 1.5, 3],
      ["HF", "HF", 1.5, 3],
      ["SO2", "SO₂", 1.5, 3],
      ["NO", "NO", 1, 3],
      ["NO2", "NO₂", 1, 3],
      ["Hg", "Mercury (Hg)", 1, 3],
      ["semivolatile", "Semivolatiles", 50, 3],
    ] },
  { id: "heme", title: "HEME Demister", cond: "droplet separator; no re-saturation",
    groups: [
      ["mist", "Droplets (mist)", 3, 3],
      ["particulate", "Particulate", 50, 3],
    ] },
  { id: "hepa", title: "HEPA Filter", cond: "10⁴ particulate DF at 900 SCFM design",
    groups: [
      ["particulate", "Particulate", 10000, 5],
    ] },
  { id: "carbon", title: "Carbon Bed", cond: "activated carbon, Hg adsorption; 8 in WC",
    groups: [
      ["Hg", "Mercury (Hg)", 1000, 5],
    ] },
  { id: "mordenite", title: "Silver Mordenite", cond: "AgI chemisorption; 4 in WC",
    groups: [
      ["I2", "Iodine (I₂)", 1000, 5],
    ] },
  { id: "sco", title: "SCO (selective catalytic oxidation)", cond: "650 °F; 4 in WC; O₂ excess",
    groups: [
      ["removal", "CO / H₂ / CH₃CN conversion", 0.95, 0.001, 1.0, "%"],
    ] },
  { id: "scr", title: "SCR (selective catalytic reduction)", cond: "NOx abatement; 4 in WC; NH₃ reagent",
    groups: [
      ["removal", "NOx removal", 0.95, 0.001, 1.0, "%"],
      ["nh3_slip", "NH₃ slip", 25, 0, 200, "ppmv"],
    ] },
];
// non-composition stages, rendered as pass-through cards
const PASS_DEFS = [
  { id: "heater", title: "Reheat Heater", cond: "+36 °F above dew point" },
  { id: "fan1", title: "Fan 1", cond: "35 in WC boost" },
  { id: "hx", title: "Regenerative HX + Reheat 2", cond: "→ 650 °F" },
  { id: "fan2", title: "Fan 2 + Stack", cond: "lift to 102 kPa exhaust" },
];
const SNAP_KEY = { heater: "heater_out", fan1: "fan1_out", hx: "hx_cold_out", fan2: "stack" };
const SNAP = (B.stage_states || {});

const DEFAULTS = {};
for (const d of STAGE_DEFS)
  for (const g of d.groups) DEFAULTS[d.id + "::" + g[0]] = g[2];

const feedGS = B.feed_state.total_g_s;

/* ------------------------------------------------------ slider values ---- */
function val(key) {
  const el = document.getElementById("sl-" + key);
  if (!el) return DEFAULTS[key];
  const v = Number(el.value);
  return el.dataset.kind === "logdf" ? Math.pow(10, v) : v;
}
function prettyDF(df) {
  if (df >= 1000) return df.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (df > 0.999 && df < 1.001) return "1 (pass-through)";
  return df.toFixed(2);
}
function fmt(x, d = 2) {
  if (x === undefined || x === null || isNaN(x)) return "—";
  if (x === 0) return "0";
  if ((x >= 1000 || x < 0.01) && x > 0) return x.toExponential(d);
  return x.toLocaleString(undefined, { maximumFractionDigits: d });
}

const P_OUT = { sbs: 91.3614, wesp: 90.1160 };
function cfgFromSliders() {
  const dfsOf = (id) => {
    const o = {};
    for (const g of STAGE_DEFS.find(d => d.id === id).groups) o[g[0]] = val(id + "::" + g[0]);
    return o;
  };
  return {
    runtime_d: B.meta.runtime_d,
    mol_per_scfm: B.meta.mol_per_scfm,
    air_n2_fraction: B.meta.air_n2_fraction,
    wesp_air_scfm: B.wesp_air_scfm,
    mw: E.MW_DEFAULT,
    stack_T_F: SNAP.stack ? SNAP.stack.T_F : undefined,
    stages: {
      sbs: { dfs: dfsOf("sbs"), T_F_out: 100, P_out_kPa: P_OUT.sbs },
      wesp: { dfs: dfsOf("wesp"), T_F_out: 100, P_out_kPa: P_OUT.wesp },
      heme: { dfs: dfsOf("heme"), T_F_out: 100 },
      heater: { dF_F: 36 },
      hepa: { particulate_df: val("hepa::particulate") },
      carbon: { dfs: dfsOf("carbon"), T_F_out: 159 },
      mordenite: { dfs: dfsOf("mordenite"), T_F_out: 159 },
      sco: { removal: val("sco::removal"), species: ["CO", "H2", "CH3CN"] },
      scr: { removal: val("scr::removal"), nh3_slip_ppmv: val("scr::nh3_slip"), stoich: 1.0 },
    },
  };
}

/* --------------------------------------------------- build once (DOM) ---- */
const ORDER = ["sbs", "heater", "wesp", "heme", "hepa", "fan1", "carbon",
               "mordenite", "hx", "sco", "scr", "fan2"];

function addSliderDF(box, id, key, label, defv, hi) {
  const row = document.createElement("div");
  row.className = "sl";
  const full = id + "::" + key;
  const hi2 = Math.log10(hi || 1e5);
  row.innerHTML = `<label>${label}</label>
    <input type="range" id="sl-${full}" data-kind="logdf"
           min="0" max="${hi2}" step="${(hi2 / 2000).toFixed(4)}"
           value="${Math.log10(Math.max(defv, 1)).toFixed(4)}">
    <span class="val" id="vl-${full}"></span>`;
  const inp = row.querySelector("input");
  const upd = () => {
    row.querySelector(".val").textContent = prettyDF(Math.pow(10, Number(inp.value)));
  };
  inp.addEventListener("input", () => { upd(); refresh(); });
  upd();
  box.appendChild(row);
}

function addSliderLinear(box, id, key, label, defv, lo, hi, unit, stepOverride) {
  const row = document.createElement("div");
  row.className = "sl";
  const full = id + "::" + key;
  const step = stepOverride || (hi - lo) / 999;
  row.innerHTML = `<label>${label}</label>
    <input type="range" id="sl-${full}" min="${lo}" max="${hi}" step="${step}" value="${defv}">
    <span class="val" id="vl-${full}"></span>`;
  const inp = row.querySelector("input");
  const upd = () => {
    const v = Number(inp.value);
    row.querySelector(".val").textContent =
      unit === "%" ? (v * 100).toFixed(1) + " %" : v + " ppmv";
  };
  inp.addEventListener("input", () => { upd(); refresh(); });
  upd();
  box.appendChild(row);
}

function buildStageCard(def) {
  const el = document.createElement("div");
  el.className = "stage open";
  el.dataset.id = def.id;
  el.innerHTML = `
    <div class="stage-head">
      <span class="stage-title">${def.title} <span class="caret">▾</span></span>
      <span class="stage-cond">${def.cond}</span>
      <span class="stage-flow" id="flow-${def.id}"></span>
    </div>
    <div class="stage-body">
      <div class="muted" style="margin-bottom:6px">Decontamination factor —
        DF = m<sub>in</sub>/m<sub>captured</sub>; DF 1 is pass-through.</div>
      <div class="sliders"></div>
      <div class="muted" id="cap-${def.id}" style="margin-top:6px"></div>
    </div>`;
  const box = el.querySelector(".sliders");
  for (const [key, label, defv, lo, hi, unit] of def.groups) {
    if (unit === "%") addSliderLinear(box, def.id, key, label, defv, lo, hi, "%");
    else if (unit === "ppmv") addSliderLinear(box, def.id, key, label, defv, lo, hi, "ppmv", 1);
    else addSliderDF(box, def.id, key, label, defv, lo === 5 ? 1e5 : 1e5);
  }
  el.querySelector(".stage-title").addEventListener("click", () => el.classList.toggle("open"));
  return el;
}

function buildPassCard(def) {
  const el = document.createElement("div");
  el.className = "stage";
  el.dataset.id = def.id;
  el.innerHTML = `
    <div class="stage-head">
      <span class="stage-title">${def.title}</span>
      <span class="stage-cond">${def.cond}${SNAP[SNAP_KEY[def.id]] ? " · " + Math.round(SNAP[SNAP_KEY[def.id]].T_F) + " °F" : ""}</span>
      <span class="stage-flow muted" id="flow-${def.id}">no composition change</span>
    </div>`;
  return el;
}

function build() {
  const rail = document.getElementById("train");

  // feed card
  const feed = document.createElement("div");
  feed.className = "stage open";
  feed.dataset.id = "melter";
  feed.innerHTML = `
    <div class="stage-head">
      <span class="stage-title">Melter Off-Gas <span class="caret">▾</span></span>
      <span class="stage-cond">700 °F · 100.1 kPa · incl. 200 SCFM melter air</span>
      <span class="stage-flow" id="flow-melter">${fmt(feedGS, 1)} g/s</span>
    </div>
    <div class="stage-body">
      <div class="muted">Campaign-mean feed after the melter (${B.meta.tag}
        c${B.meta.campaign_idx}, 5 t/d basis): ${B.feed.length} tracked species. Top-8 by mass:</div>
      <div style="font-family:var(--mono);font-size:12px;color:var(--accent);margin-top:4px">
        ${B.feed.slice(0, 8).map(r => `${r.sp} ${fmt(r.g_s, 2)}`).join(" · ")}
      </div>
    </div>`;
  feed.querySelector(".stage-title").addEventListener("click", () => feed.classList.toggle("open"));
  rail.appendChild(feed);

  for (const id of ORDER) {
    const def = STAGE_DEFS.find(d => d.id === id);
    rail.appendChild(def ? buildStageCard(def) : buildPassCard(PASS_DEFS.find(p => p.id === id)));
  }
}

/* ------------------------------------------------------ live refresh ---- */
function refresh() {
  const res = E.computeTrain(
    { species: B.feed.map(s => ({ sp: s.sp, ph: s.ph, mol_s: s.mol_s })), T_F: B.feed_state.T_F },
    cfgFromSliders());

  let prev = feedGS;
  for (const st of res.stages) {
    const flowEl = document.getElementById("flow-" + st.id);
    const capEl = document.getElementById("cap-" + st.id);
    if (flowEl && st.id !== "stack") {
      flowEl.innerHTML = `▲ ${fmt(st.g_s_total, 1)} g/s ` +
        `<span class="muted">(${fmt(st.g_s_total / prev * 100 - 100, 1)}% of inlet)</span>`;
    }
    if (capEl) {
      const caps = Object.entries(st.capture_g_s)
        .filter(([sp]) => sp !== "_nh3_dosed_g_s")
        .sort((a, b) => b[1] - a[1]).slice(0, 4)
        .map(([sp, g]) => `${sp} ${fmt(g)} g/s`).join(" · ");
      const nh3 = st.capture_g_s._nh3_dosed_g_s;
      capEl.textContent =
        (caps ? "→ sink: " + caps : "") +
        (caps && nh3 ? " · " : "") +
        (nh3 ? "NH₃ dosed " + fmt(nh3) + " g/s reagent" : "");
    }
    if (st.g_s_total > 0) prev = st.g_s_total;
  }

  renderStack(res);
}

/* ------------------------------------------------------------ stack ---- */
const STACK_COLORS = ["#4fd1c5", "#5b8def", "#f6a34a", "#e06c9f", "#9f7be5",
                      "#3fb86f", "#c0523f", "#778faa", "#2a9d8f"];

function renderStack(res) {
  const tot = res.stack_total_g_s;
  const top = res.stack.slice(0, 8);
  const bar = top.map((r, i) =>
    `<div style="width:${r.g_s / tot * 100}%;background:${STACK_COLORS[i % STACK_COLORS.length]}"
      title="${r.sp} ${r.mass_pct.toFixed(2)} mass %"></div>`).join("");
  document.getElementById("stack-summary").innerHTML = `
    <div class="stack-bar">${bar}</div>
    <div class="stack-legend">${top.map((r, i) =>
      `<span class="dot" style="background:${STACK_COLORS[i % STACK_COLORS.length]}"></span>${r.sp}`).join(" &nbsp; ")}</div>`;

  const tb = document.querySelector("#stack-table tbody");
  const rt_s = B.meta.runtime_d * 86400;
  tb.innerHTML = res.stack.map(r => `
    <tr><td>${r.sp}${r.ph === "cr" ? " 🔹" : ""}</td><td>${fmt(r.g_s)}</td>
    <td>${r.mol_pct.toFixed(3)}</td><td>${r.mass_pct.toFixed(3)}</td>
    <td>${fmt(r.g_s * rt_s / 1000, 1)}</td></tr>`).join("");

  document.getElementById("stack-note").textContent =
    `Total ${fmt(tot, 1)} g/s at ${Math.round(res.stack_T_F)} °F · ` +
    `model reference ${fmt(B.stack_ref_state.total_g_s, 1)} g/s at ${Math.round(B.stack_ref_state.T_F)} °F`;

  const t = E.totalCaptureKg(res);
  const rows = Object.entries(t).sort((a, b) => b[1] - a[1]).slice(0, 12);
  document.querySelector("#capture-table tbody").innerHTML =
    rows.map(([sp, kg]) => `<tr><td>${sp}</td><td>${fmt(kg, 1)}</td></tr>`).join("") ||
    '<tr><td colspan="2" class="muted">none</td></tr>';
}

/* ---------------------------------------------------------------- init ---- */
document.getElementById("basis-line").textContent =
  `Scenario ${B.meta.tag} · campaign ${B.meta.campaign_idx} · glass ${B.meta.glass_t.toFixed(1)} t ` +
  `(${B.meta.glass_tpd_resolved.toFixed(2)} t/d hold-rate basis) · runtime ${B.meta.runtime_d.toFixed(1)} d · ` +
  `${B.meta.canisters.toFixed(0)} canisters`;

build();
refresh();

document.title = "Off-Gas Capture Visualizer — " + B.meta.tag;