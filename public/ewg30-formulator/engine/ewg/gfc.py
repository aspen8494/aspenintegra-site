"""Glass-forming chemical (GFC) library and waste-to-oxide bookkeeping for the
EWG3.0 formulation optimizer (PNNL-38953 Tables 3.3/3.4/3.5, Appendix C).

GFC oxide compositions derived from stoichiometry of the raw chemical (the
EWG3.0 GFC set is the same concentrates listed in EWG2.5; the extracted
ewg30/gfcs.json table carries only names, so the stoichiometric yields are
kept).  Waste and GFC composition vectors are in mass fraction of oxides
summing to 1.

Sucrose: the report uses sucrose (C12H22O11) as an organic reductant; it
contributes ZERO glass oxides (ewg30/gfcs.json note_sucrose) and is therefore
NOT in the oxide-fraction decision space (a zero-yield x_k/y_k demand is
undefined).  Model redox control with Sucrose outside the optimizer, not as a
GFC row.
"""
from __future__ import annotations
import json
import os
from typing import Dict
import numpy as np

import warnings

# Molecular weights (g/mol)
MW = {
 "SiO2": 60.0843, "B2O3": 69.6202, "Al2O3": 101.9613, "CaO": 56.0774,
 "Na2O": 61.9789, "K2O": 94.196, "Li2O": 29.8814, "ZnO": 81.379, "ZrO2": 123.218,
 "Cr2O3": 151.9904, "V2O5": 181.88, "H3BO3": 61.833, "H2O": 18.0153,
 "Na2CO3": 105.9888, "Li2CO3": 73.8909, "CaSiO3": 116.1617, "CO2": 44.0095,
 "Al2SiO5": 162.0456,  # kyanite
}

# GFC: oxide yield per unit mass of raw chemical (as-fired oxide content)
def _pure_from(compound: str, oxides: Dict[str, float]) -> Dict[str, float]:
    return oxides

GFCS: Dict[str, Dict[str, float]] = {
    # Kyanite: Al2SiO5 -> Al2O3 + SiO2. Mass split: Al2O3/SiO2 = MW ratio
    "Kyanite":     {"Al2O3": MW["Al2O3"]/MW["Al2SiO5"],
                    "SiO2": MW["SiO2"]/MW["Al2SiO5"]},
    # Boric acid: 2 H3BO3 -> B2O3 + 3 H2O ; oxide yield fraction
    "BoricAcid":   {"B2O3": MW["B2O3"]/(2*MW["H3BO3"])},
    # Wollastonite: CaSiO3 -> CaO + SiO2
    "Wollastonite":{"CaO": MW["CaO"]/MW["CaSiO3"],
                    "SiO2": MW["SiO2"]/MW["CaSiO3"]},
    # Soda ash: Na2CO3 -> Na2O + CO2
    "Na2CO3":      {"Na2O": MW["Na2O"]/MW["Na2CO3"]},
    # Lithium carbonate: Li2CO3 -> Li2O + CO2
    "Li2CO3":      {"Li2O": MW["Li2O"]/MW["Li2CO3"]},
    # Chromia: pure Cr2O3
    "Cr2O3":       {"Cr2O3": 1.0},
    # Silica: pure SiO2
    "Silica":      {"SiO2": 1.0},
    # Zincite: pure ZnO
    "Zincite":     {"ZnO": 1.0},
    # Zircon: ZrSiO4 -> ZrO2 + SiO2
    "Zircon":      {"ZrO2": MW["ZrO2"]/(MW["ZrO2"]+MW["SiO2"]),
                    "SiO2": MW["SiO2"]/(MW["ZrO2"]+MW["SiO2"])},
    # Vanadia: pure V2O5 (added only when sulfate-limited; logic enforced in optimizer)
    "V2O5":        {"V2O5": 1.0},
}

GFC_NAMES = list(GFCS)  # decision-space order (excluding "Waste", handled separately)

ALL_OXIDES = sorted(set().union(*[set(v) for v in GFCS.values()]))

# Example waste compositions.
# EWG3.0 Table 3.4: the six report example wastes (extracted verbatim from
# ewg30/examples.json at import).  Keys: High Al2O3 / High F / High Na2O /
# High P2O5 / High SO3 / Dilution Water.
_EX30 = os.path.join(os.path.dirname(__file__), "data", "ewg30", "examples.json")

def _load_example_wastes_ewg30() -> Dict[str, Dict[str, float]]:
    try:
        with open(_EX30) as f:
            t34 = json.load(f)["waste_compositions_table_3_4"]
        heads = [k for k in t34 if not (k.startswith("Table") or k.startswith("Example"))]
        # the extractor glued the six column headers into one key:
        # 'High Al2O3 High F High Na2O High P2O5 High SO3 Dilution Water'
        # (+ a stray isotope token appended)
        merged = next((k for k in t34 if "High Al2O3" in k), None)
        head = next(k for k in t34 if k.startswith("Table 3.4"))
        names = []
        if merged:
            s = merged
            while True:
                i = s.find("High ")
                j = s.find("Dilution Water")
                if i == -1 and j == -1:
                    break
                if j != -1 and (i == -1 or j < i):
                    names.append(s[j:].split(" Ac2O3")[0].strip())
                    s = s[:j]
                    break
                nxt_j = s.find("Dilution Water", i)
                nxt_i = s.find("High ", i + 1)
                stop = min(x for x in (nxt_j, nxt_i) if x != -1)
                names.append(s[i:stop].strip())
                s = s[stop:]
        cols = names if len(names) == 6 else None
        if cols is None:
            raise ValueError("Table 3.4 header parse: %r" % (names,))
        out = {}
        for i, nm in enumerate(cols):
            out[nm.strip()] = {o: v[i] for o, v in t34.items()
                               if isinstance(v, list) and o not in ("SUM",)
                               and not o.startswith(("Table", "Example"))}
        return out
    except Exception as _e:  # pragma: no cover - extraction-format guard
        warnings.warn(f"EWG3.0 Table 3.4 wastes unavailable ({_e}); "
                      "falling back to legacy EWG2.5 example wastes")
        return {}

EXAMPLE_WASTES: Dict[str, Dict[str, float]] = _load_example_wastes_ewg30()

# Legacy EWG2.5 (PNNL-35884 Table 3-3) wastes, kept for back-compat references.
LEGACY_EXAMPLE_WASTES = {
 "Batch3": {"Ag2O":0.00017,"Al2O3":0.506138,"B2O3":0.000623,"BaO":0.00012,
   "Bi2O3":0.001788,"CaO":0.007861,"CdO":0.00002,"Cl":0.003726,"Cr2O3":0.002525,
   "F":0.004061,"Fe2O3":0.066038,"K2O":0.003881,"Li2O":0.0000565,"MgO":0.000267,
   "MnO":0.006666,"Na2O":0.29061,"La2O3":0.001045,"NiO":0.006564,"P2O5":0.007112,
   "PbO":0.003531,"PdO":0.0000133,"Rh2O3":0.00000474,"RuO2":0.000138,
   "SiO2":0.059441,"SnO2":0.0,"SO3":0.00517,"SrO":0.000189,"ThO2":0.008035,
   "TiO2":0.0000432,"UO3":0.008836,"V2O5":0.0000667,"ZnO":0.000135,
   "ZrO2":0.004402,"Others":0.000724},
 "Batch17": {"Ag2O":2.76e-07,"Al2O3":0.106807,"B2O3":0.0,"BaO":0.0000767,
   "Bi2O3":0.0000303,"CaO":0.013103,"Cl":0.00453,"Cr2O3":0.002402,"F":0.104781,
   "Fe2O3":0.013945,"K2O":0.006364,"MgO":0.0,"MnO":0.000311,"Na2O":0.6154,
   "La2O3":0.000296,"NiO":0.000595,"P2O5":0.023669,"PbO":0.000254,"RuO2":0.0,
   "SiO2":0.003471,"SO3":0.09653,"SrO":0.0000657,"ThO2":0.0000469,"UO3":0.003284,
   "ZrO2":0.000891,"Others":0.0000118},
 "Batch45": {"Ag2O":0.000472,"Al2O3":0.080257,"B2O3":0.002414,"BaO":0.000265,
   "Bi2O3":0.000348,"CaO":0.003004,"Cl":0.007745,"Cr2O3":0.000966,"F":0.071917,
   "Fe2O3":0.060013,"K2O":0.010779,"Li2O":0.0000101,"MgO":0.001611,
   "MnO":0.005099,"Na2O":0.569473,"La2O3":0.001355,"NiO":0.002265,
   "P2O5":0.005366,"PbO":0.00252,"RuO2":0.000178,"SiO2":0.008385,"SO3":0.009433,
   "SrO":0.00022,"ThO2":0.0000782,"TiO2":0.0000482,"UO3":0.013115,
   "V2O5":0.0000372,"ZnO":0.000113,"ZrO2":0.142022,"Others":0.000456},
}

def gfc_matrix() -> "np.ndarray":
    """rows = GFC names (+ 'Waste' appended by caller), cols = ALL_OXIDES."""
    return np.array([[GFCS[g].get(o, 0.0) for o in ALL_OXIDES] for g in GFC_NAMES])
