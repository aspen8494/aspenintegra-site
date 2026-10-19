#!/usr/bin/env python3
"""Genericize the vendored Cross-Site Waste Taxonomy explorer dashboard.

The explorer (public/waste-taxonomy/index.html) is a vendored copy of the
upstream srs-tank-waste-database repo's dashboard/unsupervised_analysis.html.
Site names (SRS, Savannah River, Hanford) and the SRNL/DWPF/SWPF program
references are the SUBJECT of this dashboard and stay. What gets scrubbed:
the laboratory name in the data-service attribution.

Usage:  python3 scripts/scrub_waste_taxonomy.py
Run AFTER copying upstream dashboard/unsupervised_analysis.html to
public/waste-taxonomy/index.html. Fails loudly if an expected source string
is missing (upstream reworded something) so the scrub can be updated rather
than silently skipped.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "public" / "waste-taxonomy" / "index.html"

TEXT_EDITS = [
    ("Hanford BBI via PNNL PHOENIX", "Hanford BBI via the PHOENIX data service"),
]

FORBIDDEN = ["Hermes", "hermes", "/Users/", "Savannah_RiverTF"]




# ---- SEO head injection (idempotent) ----
# Adds canonical + description + keywords to the vendored page so search
# engines index it. Safe to re-run after every upstream re-sync: skips if
# already present.

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
    src = PAGE.read_text(encoding="utf-8")

    misses = []
    for old, new in TEXT_EDITS:
        if old not in src:
            misses.append(old)
            continue
        src = src.replace(old, new)

    if misses:
        print("MISSING source strings — upstream reworded, update this script:")
        for m in misses:
            print("  -", repr(m))
        return 1

    PAGE.write_text(src, encoding="utf-8")

    inject_seo(
        PAGE,
        "https://aspenintegra.com/waste-taxonomy/",
        "Unsupervised machine learning on Hanford tank waste: 433 tank-phase "
        "compositions clustered into waste families, with every SRS batch "
        "projected to find its Hanford analogs.",
        "Hanford waste, Hanford tank waste, Hanford open source data, "
        "unsupervised machine learning, waste taxonomy, clustering, SRS tank "
        "waste, Best-Basis Inventory, open data",
    )

    final = PAGE.read_text(encoding="utf-8")
    leaks = [f for f in FORBIDDEN + ["PNNL"] if f in final]
    if leaks:
        print("FORBIDDEN STRINGS remain:", leaks)
        return 1

    print("Scrub complete: attribution genericized, no leaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
