#!/usr/bin/env python3
"""Vendor the Hanford Glass Research Database UI into the site.

Copies ui/ from a local clone of the upstream repository into
public/glass-research-db/, then re-applies the two vendored edits that a
fresh copy would not carry:

  1. SEO head block (canonical, description, keywords)
  2. Self-contained dark theme (:root tokens matching the site palette)

Usage:
  python3 scripts/sync_glass_research_db.py [path-to-clone]

Default clone path: ../hanford-glass-research-db (sibling of the site root).
Upstream: https://github.com/aspen8494/hanford-glass-research-db
After syncing, rebuild (npm run build) and run scripts/append_sitemap.py.
"""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT.parent / "hanford-glass-research-db"
DEST = ROOT / "public" / "glass-research-db"

SEO_BLOCK = """<title>Hanford Glass Research Database</title>
<link rel="canonical" href="https://aspenintegra.com/glass-research-db/" />
<meta
  name="description"
  content="Search 6,700+ published studies on Hanford waste glass: glass composition models, formulation algorithms, viscosity, durability, nepheline, and melter research (LAW + HLW), 1976-present."
/>
<meta
  name="keywords"
  content="Hanford Site Glass, Hanford glass, waste glass composition, glass formulation, Hanford waste glass research, LAW glass, HLW glass, vitrification research, glass property models, open database"
/>"""

OLD_ROOT = """  :root { font-size: 15px; }
  body {
    margin: 0; padding: 0; color: var(--foreground, #1a1a1a);
    background: transparent;"""

NEW_ROOT = """  :root {
    font-size: 15px;
    color-scheme: dark;
    /* Self-contained dark theme matching aspenintegra.com's dark palette */
    --foreground: #e6edf7;
    --muted-foreground: #9db0c8;
    --background: #0a1120;
    --card: #121d33;
    --border: rgba(148, 180, 220, 0.14);
    --accent: #22d3ee;
  }
  body {
    margin: 0; padding: 0; color: var(--foreground, #1a1a1a);
    background: var(--background, #0a1120);"""


def main() -> int:
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    src_ui = src / "ui"
    if not (src_ui / "index.html").exists():
        print(f"ERROR: {src_ui}/index.html not found.")
        print("Clone the repo first: git clone https://github.com/aspen8494/hanford-glass-research-db")
        return 1

    DEST.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_ui / "index.html", DEST / "index.html")
    shutil.copy2(src_ui / "records_ui.json", DEST / "records_ui.json")
    print(f"Copied ui/ from {src} -> {DEST}")

    html_path = DEST / "index.html"
    html = html_path.read_text(encoding="utf-8")

    if 'rel="canonical"' not in html:
        assert "<title>Hanford Glass Research Database</title>" in html, (
            "Upstream <title> changed — update SEO_BLOCK in this script."
        )
        html = html.replace(
            "<title>Hanford Glass Research Database</title>", SEO_BLOCK, 1
        )
        print("SEO head: injected")
    else:
        print("SEO head: already present")

    if "--background: #0a1120" not in html:
        assert OLD_ROOT in html, (
            "Upstream :root/body CSS changed — update OLD_ROOT/NEW_ROOT in this script."
        )
        html = html.replace(OLD_ROOT, NEW_ROOT, 1)
        print("Dark theme: applied")
    else:
        print("Dark theme: already present")

    html_path.write_text(html, encoding="utf-8")
    print("Sync complete. Now: npm run build && python3 scripts/append_sitemap.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
