#!/usr/bin/env python3
"""Append the four vendored playground apps to the Astro-generated sitemap.

Astro's sitemap integration only sees rendered routes; the vendored static
apps under public/ (sandbox, glass-explorer, tank-comparison, waste-taxonomy)
are copied verbatim and never appear. This script adds them to dist/sitemap-0.xml
after `astro build`.

Usage:  python3 scripts/append_sitemap.py
Run AFTER `npm run build` and BEFORE deploy. Idempotent: skips URLs already
present.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "dist" / "sitemap-0.xml"

APP_URLS = [
    "https://aspenintegra.com/sandbox/",
    "https://aspenintegra.com/glass-explorer/",
    "https://aspenintegra.com/tank-comparison/",
    "https://aspenintegra.com/waste-taxonomy/",
    "https://aspenintegra.com/glass-research-db/",
]


def main() -> int:
    if not SITEMAP.exists():
        print(f"ERROR: {SITEMAP} not found — run `npm run build` first.")
        return 1

    xml = SITEMAP.read_text(encoding="utf-8")

    added = []
    for url in APP_URLS:
        if f"<loc>{url}</loc>" in xml:
            continue
        entry = f"<url><loc>{url}</loc></url>"
        # Insert before the closing </urlset>.
        idx = xml.rfind("</urlset>")
        if idx == -1:
            print("ERROR: no </urlset> in sitemap — unexpected format.")
            return 1
        xml = xml[:idx] + entry + xml[idx:]
        added.append(url)

    if added:
        SITEMAP.write_text(xml, encoding="utf-8")
        print(f"Sitemap: appended {len(added)} app URL(s):")
        for u in added:
            print("  -", u)
    else:
        print("Sitemap: all app URLs already present — nothing to do.")

    # Verify.
    final = SITEMAP.read_text(encoding="utf-8")
    missing = [u for u in APP_URLS if f"<loc>{u}</loc>" not in final]
    if missing:
        print("ERROR: still missing after write:", missing)
        return 1
    print("Sitemap verified: all", len(APP_URLS), "app URLs present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
