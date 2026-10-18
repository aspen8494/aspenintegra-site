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

    final = PAGE.read_text(encoding="utf-8")
    leaks = [f for f in FORBIDDEN + ["PNNL"] if f in final]
    if leaks:
        print("FORBIDDEN STRINGS remain:", leaks)
        return 1

    print("Scrub complete: attribution genericized, no leaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
