#!/usr/bin/env python3
"""Genericize program identifiers in the vendored Glass Property Explorer.

The explorer (public/glass-explorer/) is a vendored copy of the upstream
repo's web/ folder. Site policy keeps program identifiers (facility names,
report numbers, internal project paths) out of the public site, so every
re-sync must re-apply these replacements after copying fresh files over.

Usage:  python3 scripts/scrub_glass_explorer.py
Run AFTER copying upstream web/ into public/glass-explorer/. Fails loudly
if an expected source string is missing (upstream reworded something) so
the scrub can be updated rather than silently skipped.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "public" / "glass-explorer"

# (file, old, new) — plain-string replacements, asserted present.
TEXT_EDITS = [
    ("index.html",
     'content="Drag glass or feed composition sliders and watch viscosity (VFT), '
     'electrical conductivity, and PCT release respond in real time — a 3-head '
     'neural network running client-side in your browser, overlaid with the '
     'published PNNL-35884 glass property formulations."',
     'content="Drag glass or feed composition sliders and watch viscosity (VFT), '
     'electrical conductivity, and PCT release respond in real time — a 3-head '
     'neural network running client-side in your browser, overlaid with the '
     'published glass property formulations."'),
    ("index.html",
     "The published model is the acceptance basis (PNNL-35884 Rev. 1).",
     "The published model is the acceptance basis."),
    ("index.html",
     "Published formulations: PNNL-35884 Rev. 1 (VFT viscosity",
     "Published formulations: the published vitreous-state model set (VFT viscosity"),
    ("js/app.js",
     "sub: 'published limits (PNNL-35884)',",
     "sub: 'published acceptance limits',"),
    ("js/app.js",
     " * Both modes overlay the NN prediction with the published PNNL-35884",
     " * Both modes overlay the NN prediction with the published"),
    ("js/nn/glassnet.js",
     "// acceptance flags at the PNNL-35884 raw limits (dataset flag basis)",
     "// acceptance flags at the published raw limits (dataset flag basis)"),
    ("js/nn/glassnet.js",
     " * Architecture (PytorchNN_GlassApp/src/models.py, trained 2026-10-15):",
     " * Architecture (GlassNet production training repo, trained 2026-10-15):"),
    ("js/engine/props.js",
     " * props.js — published PNNL-35884 Rev. 1 glass property models (JS port).",
     " * props.js — published glass property models (JS port)."),
    ("js/engine/props.js",
     " * (Hanford_Tank_BBI/ewg_app/ewg/properties.py), which reproduces the",
     " * (the production property-model source), which reproduces the"),
]

TERMS = ("hanford", "ewg", "rpp-rpt", "pnnl")




# ---- SEO head injection (idempotent) ----
# Adds canonical + description + keywords to the vendored page so search
# engines index it. Safe to re-run after every upstream re-sync: skips if
# already present. NOTE: this app ships under a Hanford-free scrub policy
# (TERMS leak gate below), so keywords/description must also be Hanford-free.

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
        path = APP / rel
        src = path.read_text(encoding="utf-8")
        if old not in src:
            misses.append(f"{rel}: {old[:70]!r}")
            continue
        path.write_text(src.replace(old, new), encoding="utf-8")

    # Data manifest: scrub any identifier-bearing provenance strings in place.
    jpath = APP / "data" / "glassnet.json"
    data = json.loads(jpath.read_text(encoding="utf-8"))
    replaced = {"count": 0}

    def scrub_str(value: str) -> str:
        out = value
        for t in TERMS:
            out = out.replace(t, "[published source]")
            out = out.replace(t.upper(), "[published source]")
            out = out.replace(t.capitalize(), "[published source]")
        if out != value:
            replaced["count"] += 1
        return out

    def walk(obj):
        if isinstance(obj, str):
            return scrub_str(obj) if any(t in obj.lower() for t in TERMS) else obj
        if isinstance(obj, list):
            return [walk(v) for v in obj]
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        return obj

    data = walk(data)
    if replaced["count"]:
        jpath.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        print(f"note: scrubbed {replaced['count']} identifier strings inside data/glassnet.json")

    if misses:
        print("MISSING source strings — upstream reworded, update this script:")
        for m in misses:
            print("  -", m)
        return 1

    # Verify: no program identifiers anywhere in the shipped tree.
    leaks = []
    for f in APP.rglob("*"):
        if not f.is_file() or f.suffix == ".bin":
            continue
        low = f.read_text(encoding="utf-8", errors="ignore").lower()
        for t in TERMS:
            if t in low:
                leaks.append(f"{f.relative_to(APP)} contains {t!r}")
    inject_seo(
        APP / "index.html",
        "https://aspenintegra.com/glass-explorer/",
        "Interactive waste glass property explorer: drag composition sliders, "
        "watch viscosity, conductivity, and PCT release respond — a client-side "
        "neural network vs published models.",
        "waste glass, glass property model, viscosity, electrical "
        "conductivity, PCT release, neural network, vitrification, HLW, "
        "nuclear waste, open data",
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
