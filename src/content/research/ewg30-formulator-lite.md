---
title: 'EWG3.0 Formulator Lite'
description: "Lightweight pure-Python CLI for EWG3.0 (PNNL-38953) glass formulation on any waste vector: byte-identical engine to the full mission app, parity-tested, Excel in and a five-sheet result workbook out."
pubDate: 2026-11-19
tags: ['glass chemistry', 'vitrification', 'python', 'optimization', 'open source']
repo: 'https://github.com/aspen8494/EWG30_Lite'
repoLabel: 'EWG30_Lite'
weight: 13
status: active
---

## The problem

The full facility mission model carries the EWG3.0 glass formulation engine, but you cannot hand it to someone who just wants an answer: feed a waste composition, get the best glass. Starting the whole application to solve one formulation is a wall between the algorithm and the people who need it — a lab with a waste analysis, a student checking a paper's example, an engineer sanity-checking a blend before the mission run.

## The approach

EWG3.0 Formulator Lite is that algorithm, alone. You supply a waste-oxide vector in an Excel template; the tool solves the identical waste-loading maximization used by the full application and writes a result workbook mirroring its export — Summary, Input_Waste, GFC_Recipe, Glass_Composition, Glass_Properties, and Constraints sheets, every constraint shown as value vs published limit with PASS/FAIL and uncertainty margins.

The engine inside (`ewg30lite/ewg/`) is a byte-copy of the full application's EWG3.0 stack at a pinned commit (`VENDORED_SOURCE_COMMIT.txt`): same optimizer, same property models, same coefficients, same Upred conventions. When a sibling checkout of the full application is available, `tests/test_parity.py` asserts bit-identical formulation results against it — the QA harness has confirmed parity on the report's six Table 3.4 example wastes and through the full application's live campaign path.

## Use

```bash
pip install -e .                          # provides the ewg30-lite command
ewg30-lite template                       # writes waste_vector_template.xlsx
ewg30-lite run waste_vector_template.xlsx -o result.xlsx
```

The template ships pre-filled with the report's Table 3.4 "High Al2O3" example waste, so the first run is a reproduction of a published result, not a blank form.

## What's next

The same engine powers the [glass property explorer](/glass-explorer/) in the browser and the formulation step of the [campaign builder](/research/ewg-campaign-builder/). Lite is the portable piece of that chain: no server, no GUI, stdlib-plus-numpy/scipy/openpyxl only.
