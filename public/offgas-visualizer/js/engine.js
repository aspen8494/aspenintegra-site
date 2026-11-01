/**
 * Off-gas train computation engine (pure, no DOM).
 *
 * Walks the campaign-mean melter off-gas stream through the train:
 *   MELTER → SBS → WESP (+300 SCFM air) → HEME → HEATER → HEPA → FAN1
 *          → CARBON BED → MORDENITE → HX/HEATER2 → SCO → SCR (+NH3) → STACK
 *
 * Capture convention (same as the facility model):
 *   DF = m_in / m_captured  → captured fraction = 1 − 1/DF. DF = 1 passes.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.OG_ENGINE = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // Semivolatile group of the wet stages (Tc, Cs, I, Br, Se, Li carriers).
  const SEMI = new Set(['Tc2O7', 'CsOH', 'I2', 'Br2', 'SeO2', 'LiBO2']);

  const MW_DEFAULT = {
    H2O: 18.015, N2: 28.014, O2: 31.998, NO: 30.006, NO2: 46.006,
    CO: 28.010, CO2: 44.009, CH3CN: 41.052, HCl: 36.461, HF: 20.006,
    SO2: 64.066, SO3: 80.064, Hg: 200.592, I2: 253.808, H3BO3: 61.831,
    Na2O: 61.979, SiO2: 60.084, Al2O3: 101.961, B2O3: 69.620, CaO: 56.077,
    K2O: 94.196, Fe2O3: 159.687, Cr2O3: 151.990, P2O5: 283.919,
    NiO: 74.692, UO3: 286.028, ThO2: 264.036, MgO: 40.304, ZnO: 81.380,
    TiO2: 79.866, Li2O: 29.879, MnO2: 86.937, ZrO2: 123.222,
    Tc2O7: 263.004, CsOH: 149.912, Cs2O: 281.810, SeO2: 110.958,
    LiBO2: 49.754, Br2: 159.808, NH3: 17.031, RuO4: 211.054,
    Cl2: 70.906, SrO: 103.619, BaO: 153.326
  };
  function mwOf(sp, MW) { return (MW && MW[sp]) || MW_DEFAULT[sp] || 100.0; }

  // Species → wet-stage category ('' means pass-through at that stage).
  function categoryOf(sp, ph) {
    if (ph === 'cr') return 'particulate';       // glass-dust entrainment
    if (sp === 'HCl') return 'HCl';
    if (sp === 'HF') return 'HF';
    if (sp === 'SO2') return 'SO2';
    if (sp === 'NO') return 'NO';
    if (sp === 'NO2') return 'NO2';
    if (sp === 'Hg') return 'Hg';
    if (SEMI.has(sp)) return 'semivolatile';
    return null;
  }

  function cloneRows(species) {
    return species.filter(s => s.mol_s > 0)
      .map(s => ({ sp: s.sp, ph: s.ph || 'g', mol_s: s.mol_s }));
  }

  /**
   * @param {Object} feed melter off-gas: {species:[{sp,ph,mol_s}], T_F}
   * @param {Object} cfg  stage configuration + basis constants (see app.js)
   * @returns {stages, stack, stack_total_g_s, stack_T_F}
   */
  function computeTrain(feed, cfg) {
    const MW = cfg.mw;
    const runtime_s = cfg.runtime_d * 86400;
    const stages = [];
    const cur = cloneRows(feed.species);
    let T_F = feed.T_F;

    const snap = () => cur.reduce((a, r) => a + r.mol_s * mwOf(r.sp, MW), 0);

    // capture by category; returns {species: g/s captured}
    // outlet-gas re-saturation: H2O(g) held at psat(T)/P; overflow → sink
    // psat via Magnus (valid ±1% at 20–100 °C steam-table class)
    function psatKPa(T_F) {
      const C = (T_F - 32) * 5 / 9;
      return 0.6112 * Math.exp(17.62 * C / (243.12 + C));
    }
    function waterResat(T_F, P_kPa, led) {
      if (!(P_kPa > 0)) return 0;
      const x = psatKPa(T_F) / P_kPa;
      const tot = cur.reduce((a, r) => a + r.mol_s, 0);
      const row = cur.find(r => r.sp === 'H2O');
      const have = row ? row.mol_s : 0;
      const allow = x / (1 - x) * (tot - have);
      const cond = have - allow;
      if (cond > 1e-12) {                       // over-saturated → condense
        if (row) row.mol_s -= cond;
        led.H2O = (led.H2O || 0) + cond * mwOf('H2O', MW);
      } else {                                  // under-saturated → evaporate
        const top = allow - have;
        if (top > 1e-12) {
          if (row) row.mol_s += top;
          else cur.push({ sp: 'H2O', ph: 'g', mol_s: top });
        }
      }
      return cond;
    }

    function captureCat(cat, df) {
      if (!(df > 1)) return {};
      const led = {};
      for (const row of cur) {
        const cat2 = row.ph === 'cr' ? 'particulate' : categoryOf(row.sp, row.ph);
        if (cat2 !== cat) continue;
        const cap = row.mol_s * (1 - 1 / df);
        row.mol_s -= cap;
        if (cap > 0) led[row.sp] = (led[row.sp] || 0) + cap * mwOf(row.sp, MW);
      }
      return led;
    }

    function captureDFs(dfs, mist) {
      // dfs: {cat: DF}. 'mist' captures liquid-phase ('l'/'aq') species.
      const led = {};
      if (mist && mist > 1) {
        for (const row of cur) {
          if (row.ph === 'l' || row.ph === 'aq') {
            const cap = row.mol_s * (1 - 1 / mist);
            row.mol_s -= cap;
            if (cap > 0) led[row.sp] = (led[row.sp] || 0) + cap * mwOf(row.sp, MW);
          }
        }
      }
      for (const cat in dfs) {
        if (cat === 'mist') continue;
        const c = captureCat(cat, dfs[cat]);
        for (const sp in c) led[sp] = (led[sp] || 0) + c[sp];
      }
      return led;
    }

    function pushStage(id, label, cond, led, T_after) {
      stages.push({
        id, label, cond,
        g_s_total: snap(),
        capture_g_s: led || {},
        T_F: (T_after !== undefined) ? T_after : undefined
      });
    }

    // 1 — SBS scrubber
    {
      const led = captureDFs(cfg.stages.sbs.dfs);
      T_F = cfg.stages.sbs.T_F_out;
      // outlet gas re-saturates at the bath condition; excess H2O → liquor
      const water = waterResat(T_F, cfg.stages.sbs.P_out_kPa, led);
      pushStage('sbs', 'SBS Scrubber', 'quench → 100 °F, saturated', led, T_F);
      void water;
    }

    // 2 — WESP: air addition + capture
    {
      const n = cfg.wesp_air_scfm * cfg.mol_per_scfm;
      for (const sp of ['N2', 'O2']) {
        const frac = sp === 'N2' ? cfg.air_n2_fraction : 1 - cfg.air_n2_fraction;
        const row = cur.find(r => r.sp === sp);
        if (row) row.mol_s += n * frac;
        else cur.push({ sp, ph: 'g', mol_s: n * frac });
      }
      const led = captureDFs(cfg.stages.wesp.dfs);
      T_F = cfg.stages.wesp.T_F_out;
      waterResat(T_F, cfg.stages.wesp.P_out_kPa, led);
      pushStage('wesp', 'WESP', 'wet ESP → 100 °F; +300 SCFM air', led, T_F);
    }

    // 3 — HEME demister: droplets (mist) + residual particulate
    {
      const led = captureDFs(cfg.stages.heme.dfs, cfg.stages.heme.dfs.mist);
      pushStage('heme', 'HEME Demister', 'droplet separator', led, T_F);
    }

    // 4 — reheat heater
    {
      T_F += cfg.stages.heater.dF_F;
      pushStage('heater', 'Reheat Heater', '+' + cfg.stages.heater.dF_F + ' °F above dew point', {}, T_F);
    }

    // 5 — HEPA
    {
      const led = captureCat('particulate', cfg.stages.hepa.particulate_df);
      pushStage('hepa', 'HEPA Filter', DFnote(cfg.stages.hepa.particulate_df), led, T_F);
    }

    // 6 — fan 1
    pushStage('fan1', 'Fan 1', '35 in WC boost (sensible-heat rise)', {}, T_F);

    // 7 — carbon bed (Hg)
    {
      const led = captureDFs(cfg.stages.carbon.dfs);
      pushStage('carbon', 'Carbon Bed', 'Hg adsorption on activated carbon', led, T_F);
    }

    // 8 — mordenite (I2)
    {
      const led = captureDFs(cfg.stages.mordenite.dfs);
      pushStage('mordenite', 'Silver Mordenite', 'I₂ chemisorption (AgI)', led, T_F);
    }

    // 9 — regenerative HX cold pass + heater 2 up to 650 °F
    {
      T_F = 650;
      pushStage('hx', 'Regenerative HX + Reheat', 'HX cold pass → 650 °F', {}, T_F);
    }

    // 10 — SCO
    {
      const sc = cfg.stages.sco;
      const eff = sc.removal;
      const led = {}; const prod = { CO2: 0, H2O: 0, N2: 0 };
      let o2_used = 0;
      for (const row of cur) {
        if (!sc.species.includes(row.sp)) continue;
        const cap = row.mol_s * eff;
        if (cap <= 0) continue;
        row.mol_s -= cap;
        led[row.sp] = (led[row.sp] || 0) + cap * mwOf(row.sp, MW);
        if (row.sp === 'CO') { prod.CO2 += cap; o2_used += 0.5 * cap; }
        if (row.sp === 'H2') prod.H2O += cap / 2;
        if (row.sp === 'CH3CN') { prod.CO2 += 2 * cap; prod.N2 += cap / 2; prod.H2O += 1.5 * cap; o2_used += 2 * cap; }
      }
      for (const sp in prod) {
        if (prod[sp] <= 0) continue;
        const row = cur.find(r => r.sp === sp);
        if (row) row.mol_s += prod[sp];
        else cur.push({ sp, ph: 'g', mol_s: prod[sp] });
      }
      const oRow = cur.find(r => r.sp === 'O2');
      if (oRow && o2_used > 0) oRow.mol_s -= o2_used;   // oxidation air bleed O2
      pushStage('sco', 'SCO', '650 °F catalyst — CO/C₂H₃N/H₂ oxidation', led, T_F);
    }

    // 11 — SCR: NOx abatement with NH3
    {
      const sc = cfg.stages.scr;
      const eff = sc.removal;
      const nox = cur.filter(r => r.sp === 'NO' || r.sp === 'NO2')
        .reduce((a, r) => a + r.mol_s, 0);
      const removed = nox * eff;
      const led = {};
      const nRow = cur.find(r => r.sp === 'N2');
      const oRow = cur.find(r => r.sp === 'O2');
      const wRow = cur.find(r => r.sp === 'H2O');
      let o2_used = 0, h2o_made = 0;
      for (const row of cur) {
        if (row.sp !== 'NO' && row.sp !== 'NO2') continue;
        const cap = row.mol_s * eff;
        row.mol_s -= cap;
        led[row.sp] = (led[row.sp] || 0) + cap * mwOf(row.sp, MW);
        // flue-gas NOx reduction: 4NO+4NH3+O2 → 4N2+6H2O ; 6NO2+8NH3 → 6N2+12H2O
        if (row.sp === 'NO') { o2_used += 0.25 * cap; h2o_made += 1.5 * cap; }
        else { h2o_made += 2 * cap; }
      }
      if (removed > 0) {
        if (nRow) nRow.mol_s += removed;   // NO_N + NH3_N → N2 (1 N2 per NOx mol)
        else cur.push({ sp: 'N2', ph: 'g', mol_s: removed });
        if (o2_used > 0 && oRow) oRow.mol_s -= o2_used;
        if (h2o_made > 0) {
          if (wRow) wRow.mol_s += h2o_made;
          else cur.push({ sp: 'H2O', ph: 'g', mol_s: h2o_made });
        }
      }
      // NH3: dosed at stoich × NOx-N; the fixed slip ppmv rides out unreacted
      const totalOutMol = cur.reduce((a, r) => a + r.mol_s, 0);
      const slip = sc.nh3_slip_ppmv * 1e-6 * totalOutMol;
      const nhRow = cur.find(r => r.sp === 'NH3');
      if (nhRow) nhRow.mol_s += slip;
      else cur.push({ sp: 'NH3', ph: 'g', mol_s: slip });
      led._nh3_dosed_g_s = removed * sc.stoich * mwOf('NH3', MW);
      pushStage('scr', 'SCR', DFnote(eff, 'NOx', `${sc.nh3_slip_ppmv} ppmv NH₃ slip`), led, T_F);
    }

    // 12 — HX hot pass + fan 2 (lift to stack pressure)
    if (cfg.stack_T_F !== undefined) T_F = cfg.stack_T_F;
    pushStage('stack', 'Stack', 'fan 2 → 102 kPa exhaust', {}, T_F);

    // campaign-integrated capture ledger
    for (const st of stages) {
      st.capture_kg_campaign = {};
      for (const sp in st.capture_g_s)
        st.capture_kg_campaign[sp] = st.capture_g_s[sp] * runtime_s / 1000.0;
    }

    const totalMol = cur.reduce((a, r) => a + r.mol_s, 0);
    const totalGS = snap();
    const stack = cur
      .filter(r => r.mol_s > 0)
      .map(r => ({
        sp: r.sp, ph: r.ph, mol_s: r.mol_s,
        mol_pct: r.mol_s / totalMol * 100,
        g_s: r.mol_s * mwOf(r.sp, MW),
        mass_pct: r.mol_s * mwOf(r.sp, MW) / totalGS * 100
      }))
      .sort((a, b) => b.g_s - a.g_s);

    return { stages, stack, stack_total_g_s: totalGS, stack_T_F: T_F };
  }

  function DFnote(df, of, extra) {
    const bits = [];
    if (df !== undefined) bits.push((of ? of + ' ' : '') + (typeof df === 'number' ? df.toFixed(df >= 100 ? 0 : 2) : df) + ' removal');
    if (extra) bits.push(extra);
    return bits.join(', ') || 'pass-through';
  }

  /** Total mass to sinks (kg per campaign) across stages. */
  function totalCaptureKg(res) {
    const t = {};
    for (const st of res.stages)
      for (const sp in st.capture_kg_campaign) {
        if (sp === '_nh3_dosed_g_s') continue;
        t[sp] = (t[sp] || 0) + st.capture_kg_campaign[sp];
      }
    return t;
  }

  return { computeTrain, categoryOf, SEMI, mwOf, MW_DEFAULT, totalCaptureKg };
}));