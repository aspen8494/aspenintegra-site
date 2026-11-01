#!/usr/bin/env python3
"""Vendor the Off-Gas Capture Visualizer into the site.

Copies the static app (index.html + css/ + js/) from a local clone of the
upstream repo into public/offgas-visualizer/, then re-applies the vendored
SEO head block (canonical, description, keywords).

Usage:
  python3 scripts/sync_offgas_visualizer.py [path-to-clone]

Default clone path: ../offgas-visualizer (sibling of the site root).
Upstream: https://github.com/aspen8494/offgas-visualizer
After syncing: npm run build && python3 scripts/append_sitemap.py
"""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT.parent / "offgas-visualizer"
DEST = ROOT / "public" / "offgas-visualizer"

OLD_TITLE_BLOCK = """<title>Off-Gas Capture Visualizer — HLW Melter</title>
<meta name="description" content="Interactive decontamination-factor visualizer for a Hanford HLW melter off-gas train (SBS, WESP, HEME, HEPA, carbon bed, mordenite, SCO/SCR)."/>"""

NEW_TITLE_BLOCK = """<title>Off-Gas Capture Visualizer — HLW Melter</title>
<link rel="canonical" href="https://aspenintegra.com/offgas-visualizer/" />
<meta name="description" content="Interactive Hanford HLW melter off-gas capture visualizer: DF sliders on every treatment stage (scrubber, WESP, HEPA, carbon bed, mordenite, SCO/SCR) with live stack-composition readouts — fully client-side." />
<meta name="keywords" content="Hanford offgas, off-gas treatment, melter off-gas, vitrification offgas train, SBS scrubber, WESP, HEPA, carbon bed, mordenite, SCO SCR, decontamination factor, Hanford waste, stack emissions, interactive" />"""

SERVED = ["index.html", "css", "js"]


def main() -> int:
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    if not (src / "index.html").exists():
        print(f"ERROR: {src}/index.html not found.")
        print("Clone first: git clone https://github.com/aspen8494/offgas-visualizer")
        return 1

    DEST.mkdir(parents=True, exist_ok=True)
    for item in SERVED:
        s = src / item
        d = DEST / item
        if s.is_dir():
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    print(f"Copied {', '.join(SERVED)} from {src} -> {DEST}")

    html_path = DEST / "index.html"
    html = html_path.read_text(encoding="utf-8")

    if 'rel="canonical"' in html:
        print("SEO head: already present")
    else:
        assert OLD_TITLE_BLOCK in html, (
            "Upstream index.html head changed — update OLD/NEW_TITLE_BLOCK."
        )
        html = html.replace(OLD_TITLE_BLOCK, NEW_TITLE_BLOCK, 1)
        html_path.write_text(html, encoding="utf-8")
        print("SEO head: injected")

    print("Sync complete. Now: npm run build && python3 scripts/append_sitemap.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
