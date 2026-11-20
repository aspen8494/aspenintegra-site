// EWG3.0 Formulator — Pyodide-hosted client-side runtime.
// Engine: byte-identical vendored copy of ewg30lite/ewg (repo EWG30_Lite, engine commit f5fff58).
// All assets vendored locally; same-origin fetches only, no third-party CDN.
const APP_VERSION = "1.0";
const INDEX_URL = "pyodide/";
const ENGINE_PREFIX = "engine/ewg/";
const ENGINE_ROOT = "engine/"; // ewg30-fetch-fixed
const ENGINE_FILES = ["__init__.py", "gfc.py", "optimize.py", "properties.py", "tensor_backend.py"];

const statusEl = id => document.getElementById(id);
const fmt = (v, d = 4) => Number(v).toFixed(d);

async function main() {
  const basis = statusEl('basis-line');
  try {
    const { loadPyodide } = window.pyodideModule;
    basis.textContent = "Booting Python (WASM ~35 MB, cached after first load)…";
    const py = await loadPyodide({ indexURL: INDEX_URL });
    basis.textContent = "Loading numpy + scipy…";
    await py.loadPackage(["numpy", "scipy"]);
    basis.textContent = "Fetching EWG3.0 engine…";

    py.runPython("import os\nos.makedirs('/engine/ewg/data/ewg30', exist_ok=True)");
    for (const f of ENGINE_FILES) {
      const txt = await (await fetch(ENGINE_PREFIX + f)).text();
      py.FS.writeFile(`/engine/ewg/${f}`, txt);
    }
    const manifest = await (await fetch(ENGINE_PREFIX + "data_manifest.json")).json();
    for (const f of manifest) {
      const txt = await (await fetch(ENGINE_PREFIX.replace('engine/ewg/', 'engine/') + f)).text();
      py.FS.writeFile(`/engine/${f}`, txt);
    }

    basis.textContent = "Importing engine…";
    await py.runPythonAsync(`
import sys, json
sys.path.insert(0, '/engine')
sys.modules.pop('ewg', None)
import ewg.optimize as _opt
import ewg.gfc as _gfc
FORMULATE = _opt.formulate
FULL_OXIDES = list(_opt.FULL_OXIDES)
EXAMPLE_WASTES = _gfc.EXAMPLE_WASTES
`);

        window.PRESETS = JSON.parse(py.runPython("json.dumps(EXAMPLE_WASTES)"));
    window.FULL_OXIDES = JSON.parse(py.runPython("json.dumps(FULL_OXIDES)"));

    window.EWG_RUN = (waste, conf) =>
      JSON.parse(py.runPython(buildRunner(JSON.stringify(waste), conf)));

    basis.textContent =
      `Engine loaded — vendored byte-identical EWG3.0 stack · solves in your browser, data never leaves this page · v${APP_VERSION}`;
    statusEl('foot').textContent =
      `Engine: EWG30_Lite ewg30lite/ewg (byte-identical vendored copy, engine commit f5fff58) · WASM runtime: Pyodide 0.27.3 · all computation client-side`;
    buildWasteTable('High Al2O3');
    statusEl('run').disabled = false;
  } catch (e) {
    console.error(e);
    basis.textContent = "Engine failed to load: " + (e.message || e);
  }
}

function buildRunner(wasteJson, conf) {
  return `
import json, numpy as np
_res = FORMULATE(json.loads('${wasteJson}'), confidence=${conf})
_ev = _res['evaluation']
def _t(o):
    if isinstance(o, np.ndarray): return o.tolist()
    try: return float(o)
    except Exception: return str(o)
_cons = {}
for k, row in _ev.constraints.items():
    d = row.__dict__ if hasattr(row, '__dict__') else row
    if hasattr(d, 'get'):
        _cons[k] = {'value': float(d['value']), 'ok': bool(d['pass'])}
    else:
        _cons[k] = {'value': float(row[0]), 'ok': bool(row[1])}
_out = {
  'success': bool(_res['success']), 'message': str(_res['message']),
  'waste_loading': float(_res['waste_loading']), 'wl_physical': float(_res['wl_physical']),
  'glass_input_total': float(_res['glass_input_total']),
  'x': {k: _t(v) for k, v in _res['x'].items()},
  'gfc_raw': ({k: float(v) for k, v in _res['gfc_raw_mass_fraction'].items()}
              if isinstance(_res['gfc_raw_mass_fraction'], dict) else {}),
  'glass': ({k: _t(v) for k, v in _ev.g.items()} if isinstance(_ev.g, dict)
            else {k: _t(v) for k, v in zip(FULL_OXIDES, _ev.g)}),
  'props': {'eta1150': _t(_ev.eta1150), 'eta1100': _t(_ev.eta1100), 'ec1100': _t(_ev.ec1100),
            'ec1200': _t(_ev.ec1200), 'nca_g_l': _t(_ev.nca_g_l), 'np_p': _t(_ev.np_p),
            'c950': _t(_ev.c950), 'NNaLi': _t(_ev.NNaLi), 'NALK': _t(_ev.NALK),
            'NSiAl': _t(_ev.NSiAl), 'NSiBi': _t(_ev.NSiBi)},
  'constraints': _cons, 'all_pass': bool(_ev.all_pass),
}
json.dumps(_out)
`;
}

function buildWasteTable(name) {
  const w = window.PRESETS[name];
  statusEl('preset').value = name;
  const rows = [];
  for (const [oxide, val] of Object.entries(w))
    rows.push(trOxide(oxide, val, true));
  for (const oxide of window.FULL_OXIDES)
    if (!(oxide in w))
      rows.push(trOxide(oxide, 0, false));
  statusEl('tbody-waste').innerHTML = rows.join('');
  statusEl('waste-sum').textContent = `Σ = ${fmt(Object.values(w).reduce((a, b) => a + b, 0), 6)}`;
}
function trOxide(oxide, val, fromPreset) {
  return `<tr><td>${oxide}</td>` +
    `<td class="num"><input data-oxide="${oxide}" type="number" step="0.0001" min="0" value="${val}"/></td></tr>`;
}

function readWaste() {
  const out = {};
  document.querySelectorAll('#waste input[data-oxide]').forEach(inp => {
    const v = parseFloat(inp.value);
    if (v > 0) out[inp.dataset.oxide] = v;
  });
  return out;
}

function renderResult(r, tSec) {
  statusEl('panel-out').hidden = false;
  statusEl('panel-busy').hidden = true;
  statusEl('meta').textContent = `solved in ${tSec.toFixed(2)} s`;
  statusEl('verdict').className = r.all_pass ? 'pass' : 'fail';
  statusEl('verdict').textContent = r.all_pass ? 'ALL LIMITS PASS' : 'CONSTRAINT FAILURES';
  const kpiCard = (label, val, cls = '') =>
    `<div class="card"><div class="muted">${label}</div><div class="v ${cls}">${val}</div></div>`;
  statusEl('kpi').innerHTML =
    kpiCard('Waste loading', fmt(r.waste_loading * 100, 2) + ' %') +
    kpiCard('Physical (GFC) loading', fmt(r.wl_physical * 100, 2) + ' %') +
    kpiCard('Glass produced', fmt(r.glass_input_total, 3) + ' kg') +
    kpiCard('Verifier', r.all_pass ? 'PASS' : 'FAIL', r.all_pass ? 'pass' : 'fail');

  statusEl('wl').innerHTML =
    `The optimizer maximizes its internal (<i>optimizer</i>) waste loading, here ` +
    `<b>${fmt(r.waste_loading * 100, 2)} %</b>, then reports a separately-computed physical, ` +
    `GFC-based loading of <b>${fmt(r.wl_physical * 100, 2)} %</b> that accounts for the volatile fraction.`;

  fillTable('gfc', Object.entries(r.gfc_raw).filter(([k, v]) => v > 1e-9),
    ['Glass-forming chemical', 'Raw mass (per glass kg)'],
    ([k, v]) => [k, fmt(v, 6)]);
  fillTable('glass', Object.entries(r.glass).filter(([k, v]) => Number(v) > 1e-7),
    ['Oxide', 'Mass fraction'],
    ([k, v]) => [k, fmt(v, 6)]);
  fillTable('props', Object.entries(r.props), ['Property model output', 'Value'],
    ([k, v]) => [k, fmt(v, 4)]);
  fillTable('cons', Object.entries(r.constraints), ['Constraint', 'Value', 'Verdict'],
    ([k, c]) => {
      const cls = c.ok ? 'pass' : 'fail';
      return [k, fmt(c.value, 4), `<span class="${cls}">${c.ok ? 'PASS' : 'FAIL'}</span>`];
    });
}

function fillTable(id, entries, heads, mapper) {
  const tbl = statusEl(id);
  let thead = tbl.querySelector('thead');
  if (!thead) { thead = document.createElement('thead'); tbl.appendChild(thead); }
  let tbody = tbl.querySelector('tbody');
  if (!tbody) { tbody = document.createElement('tbody'); tbl.appendChild(tbody); }
  thead.innerHTML = '<tr>' + heads.map(h => `<th>${h}</th>`).join('') + '</tr>';
  tbody.innerHTML =
    entries.map(([k, v]) =>
      '<tr>' + mapper([k, v]).map((c, i) => `<td class="${i > 0 ? 'num' : ''}">${c}</td>`).join('') + '</tr>'
    ).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  main();
  statusEl('preset').addEventListener('change', e => {
    if (window.PRESETS) buildWasteTable(e.target.value);
  });
  statusEl('run').addEventListener('click', () => {
    const btn = statusEl('run');
    if (btn.disabled || !window.EWG_RUN) return;
    btn.disabled = true;
    statusEl('panel-out').hidden = true;
    statusEl('panel-busy').hidden = false;
    statusEl('busy-msg').textContent =
      'Solving… (a run in this browser typically takes 1–5 s; heel-heavy vectors longer)';
    setTimeout(() => {
      const t0 = performance.now();
      try {
        const r = window.EWG_RUN(readWaste(), parseFloat(statusEl('conf').value) || 0.90);
        btn.disabled = false;
        renderResult(r, (performance.now() - t0) / 1000);
      } catch (e) {
        console.error(e);
        btn.disabled = false;
        statusEl('busy-msg').textContent = 'Solver error: ' + String(e).slice(0, 300);
      }
    }, 30);
  });
});
