#!/usr/bin/env python3
"""Genericize the vendored SRS vs Hanford tank-waste comparison dashboard.

The dashboard (public/tank-comparison/index.html) is a vendored copy of the
upstream srs-tank-waste-database repo's self-contained HTML dashboard. Site
names (SRS, Savannah River Site, Hanford) are the SUBJECT of this project and
stay. What gets scrubbed: the AI-agent self-reference in the footer, the
laboratory name in the data-service attribution, and local file paths.

Usage:  python3 scripts/scrub_tank_comparison.py
Run AFTER copying upstream dashboard/srs_hanford_comparison.html to
public/tank-comparison/index.html. Fails loudly if an expected source string
is missing (upstream reworded something) so the scrub can be updated rather
than silently skipped.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "public" / "tank-comparison" / "index.html"

# (old, new) — plain-string replacements, asserted present.
TEXT_EDITS = [
    # Footer: remove the AI-agent self-reference, keep the provenance trail.
    ("Assembled by Hermes agent from public DOE/NRC/PNNL sources",
     "Assembled from public DOE/NRC sources"),
    # Data-service attribution: keep the service name, drop the lab name.
    ("PNNL PHOENIX TankFarmService API (BBIWaste / BBIVolume, all 177 tanks)",
     "PHOENIX TankFarmService API (BBIWaste / BBIVolume, all 177 tanks)"),
]

# Strings that must NOT appear anywhere in the shipped file.
FORBIDDEN = ["Hermes", "hermes", "/Users/", "Savannah_RiverTF"]


def main() -> int:
    src = PAGE.read_text(encoding="utf-8")

    misses = []
    for old, new in TEXT_EDITS:
        if old not in src:
            misses.append(old[:70])
            continue
        src = src.replace(old, new)

    if misses:
        print("MISSING source strings — upstream reworded, update this script:")
        for m in misses:
            print("  -", repr(m))
        return 1

    PAGE.write_text(src, encoding="utf-8")

    # Verify: no forbidden strings anywhere.
    final = PAGE.read_text(encoding="utf-8")
    leaks = [f for f in FORBIDDEN if f in final]
    if leaks:
        print("FORBIDDEN STRINGS remain:", leaks)
        return 1

    print("Scrub complete: footer de-agentized, attribution genericized, no leaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
