#!/usr/bin/env python3
"""Genericize program identifiers in the vendored HLW Blend Sandbox copy.

The sandbox (public/sandbox/) is a vendored copy of the upstream repo's web/
folder. Site policy keeps program identifiers (facility names, report numbers,
project codenames) out of the public site, so every re-sync must re-apply
these replacements after copying fresh files over.

Usage:  python3 scripts/scrub_sandbox.py
Run AFTER copying upstream web/ into public/sandbox/. Fails loudly if an
expected source string is missing (upstream reworded something) so the
scrub can be updated rather than silently skipped.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SBX = ROOT / "public" / "sandbox"

# (file, old, new) — plain-string replacements, asserted present.
TEXT_EDITS = [
    ("index.html",
     "<title>Hanford HLW Blend Sandbox — mission planner</title>",
     "<title>HLW Blend Sandbox — mission planner</title>"),
    ("index.html",
     'content="An in-browser sandbox of the Hanford HLW campaign-blending problem:',
     'content="An in-browser sandbox of the HLW campaign-blending problem:'),
    ("index.html",
     "campaign planner &middot; RPP-RPT-64878 §6.2 &middot; EWG2.5 glass models",
     "campaign planner &middot; published sequencing rules &middot; published glass models"),
    ("index.html",
     "Data: 38 App-D DFHLW feed layers (+ retrieval heels) with per-layer",
     "Data: 38 published DFHLW feed layers (+ retrieval heels) with per-layer"),
    ("index.html",
     "oxide vectors and WAP values from RPP-RPT-64878-01; glass property",
     "oxide vectors and WAP values from the published inventory basis; glass"),
    ("index.html",
     "models from PNNL-35884 Rev. 1 (EWG2.5).  The sandbox reproduces the",
     "models from the published vitreous state benchmark set.  The sandbox reproduces the"),
    ("css/sandbox.css",
     "/* Hanford HLW Blend Sandbox — sandbox.css",
     "/* HLW Blend Sandbox — sandbox.css"),
    ("js/engine/engine.js",
     "* Scaled-down port of the full application's ewg/campaign_builder.py",
     "* Scaled-down port of the full application's campaign builder"),
    ("js/engine/engine.js",
     "* (RPP-RPT-64878-01 §6.2): quadrant-ordered greedy layer walk with",
     "* (published sequencing rules): quadrant-ordered greedy layer walk with"),
    ("js/engine/engine.js",
     "// ---- refine ladder (port of ewg/campaign_builder.refine_campaign) --",
     "// ---- refine ladder (port of the full application's refine_campaign) --"),
    ("js/engine/glass.js",
     "* glass.js — EWG2.5 glass formulation for the sandbox (client-side).",
     "* glass.js — published-model glass formulation for the sandbox (client-side)."),
    ("js/engine/glass.js",
     "* Faithful port of the full application's ewg/properties.py + ewg/optimize.py",
     "* Faithful port of the full application's property models + optimizer"),
    ("js/engine/glass.js",
     "* (PNNL-35884 Rev. 1 models, paper-verified against Tables 3-5/3-6):",
     "* (published glass property models, paper-verified against the source tables):"),
    ("js/engine/glass.js",
     "// Property-model coefficients (PNNL-35884 Rev. 1, ported verbatim)",
     "// Property-model coefficients (published vitreous-state model set, ported verbatim)"),
    ("js/engine/sqp.js",
     " * application's ewg/optimize.py).",
     " * application's glass optimizer)."),
    ("js/engine/sqp.js",
     "* the full app's scipy/SLSQP outputs on the PNNL-35884 example wastes.",
     "* the full app's scipy/SLSQP outputs on the reference example wastes."),
    ("js/engine/lp.js",
     "* `refine_campaign` (ewg/campaign_builder.py).  Campaign LPs here are small",
     "* `refine_campaign` (full application's campaign builder).  Campaign LPs here are small"),
]

JSON_META = {
    "title": "HLW Blending Mission Sandbox",
    "source": "Published inventory basis (feed layer set) + published vitreous-state glass property models",
    "provenance": "Extracted from the full mission application's published data layer; see tools/build_sandbox_data.py",
}

TERMS = ("hanford", "ewg", "rpp-rpt", "pnnl")


# ---- SEO head injection (idempotent) ----
# Adds canonical + description + keywords to the vendored page. Safe to
# re-run after every upstream re-sync: skips if already present. NOTE: this
# app ships under a Hanford-free scrub policy (TERMS leak gate below), so
# the keywords/description passed here must also be Hanford-free.

CANONICAL_MARKER = 'rel="canonical"'


def inject_seo(
    path: pathlib.Path, canonical: str, description: str, keywords: str
) -> None:
    html = path.read_text(encoding="utf-8")
    if CANONICAL_MARKER in html:
        return
    tags = (
        f'\n  <link rel="canonical" href="{canonical}" />\n'
        f'  <meta name="description" content="{description}" />\n'
        f'  <meta name="keywords" content="{keywords}" />\n'
    )
    marker = "</title>"
    idx = html.find(marker)
    assert idx != -1, f"{path}: no <title> tag to anchor SEO tags on"
    html = html[: idx + len(marker)] + tags + html[idx + len(marker) :]
    path.write_text(html, encoding="utf-8")

def main() -> int:
    misses = []
    for rel, old, new in TEXT_EDITS:
        path = SBX / rel
        src = path.read_text(encoding="utf-8")
        if old not in src:
            misses.append(f"{rel}: {old[:60]!r}")
            continue
        path.write_text(src.replace(old, new), encoding="utf-8")

    jpath = SBX / "data" / "mission_data.json"
    data = json.loads(jpath.read_text(encoding="utf-8"))
    data["meta"].update(JSON_META)
    jpath.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    if misses:
        print("MISSING source strings — upstream reworded, update this script:")
        for m in misses:
            print("  -", m)
        return 1

    # Verify: no program identifiers anywhere in the shipped tree.
    leaks = []
    for f in SBX.rglob("*"):
        if not f.is_file():
            continue
        low = f.read_text(encoding="utf-8", errors="ignore").lower()
        for t in TERMS:
            if t in low:
                leaks.append(f"{f.relative_to(SBX)} contains {t!r}")
    inject_seo(
        SBX / "index.html",
        "https://aspenintegra.com/sandbox/",
        "In-browser mission planner for nuclear tank waste blending: build "
        "retrieval campaigns, optimize the glass formulation, watch mission "
        "glass respond — client-side, no server.",
        "tank waste, HLW, mission planning, waste blending, glass "
        "formulation, vitrification, nuclear waste, open data",
    )

    if leaks:
        print("IDENTIFIER LEAKS remain:")
        for l in leaks:
            print("  -", l)
        return 1

    print("Scrub complete: all identifiers genericized, no leaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
