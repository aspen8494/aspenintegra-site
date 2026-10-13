---
title: 'EWG Campaign Builder & Mission Planning'
description: 'Turns tank-by-tank Best-Basis Inventory chemistry into sequenced retrieval campaigns — WAC evaluation, glass-forming optimization, and mission rollups — reproducing published benchmarks to within a few percent.'
pubDate: 2026-09-20
tags: ['optimization', 'mission planning', 'python', 'nuclear engineering']
repo: 'https://github.com/aspen8494/hlw-facility-mission-model'
repoLabel: 'Related repo'
weight: 9
status: active
---

## The problem

The Hanford tank farms hold ~56 million gallons of mixed radioactive and chemical waste in 177 underground tanks. The baseline mission retrieves that waste, separates most of the volume into a low-activity waste stream, and converts the sludge fraction — bearing the transuranic and cesium-strontium activity — into glass in a high-level waste vitrification facility.

Retrieval sequencing matters because the waste is heterogeneous at every scale: between tanks, between horizontal layers within a tank, and between liquid, saltcake, and sludge phases. The question the campaign builder answers: **which material moves when, in what blends, and with what glass-forming chemistry — such that every constraint holds and the mission is as short and cheap as possible?**

## The approach

- **Data lineage** — Best-Basis Inventory chemistry is pulled from the PNNL PHOENIX service and flattened to per-tank snapshots (~400 MB, scripted with response-shape verification). Layer vectors follow the Appendix D layer-by-layer convention of RPP-RPT-64878, extended with homogenized heel layers synthesized from whole-tank chemistry for every tank outside the published set: 38 published + 53 heel layers, ~15 Mt of waste oxide.
- **Stoichiometry that survives audits** — the element-to-oxide conversion uses n-atoms-per-oxide factors and excludes anions from oxide mass. Getting this wrong is not subtle: a naive oxide-name mapping fabricates about a kilotonne of phantom cobalt oxide across the published layer set.
- **Campaign sequencing** — a builder walks tanks and layers under the Section 6.2 rules (quadrant drain order, shallowest-layer eligibility, ≤5 tanks per campaign, 450–550 kgal volume band), refined by a linear program (HiGHS) that maximizes waste transfer subject to WAC constraints.
- **Glass formulation as constrained optimization** — the EWG2.5 property models (PNNL-35884) act as constraint functions: product consistency, viscosity (Vogel-Fulcher-Tammann), electrical conductivity, sulfate solubility, phosphate capacity, each with per-oxide validity bounds. SLSQP with multi-start over initial waste fractions, because a single start is infeasible-by-convergence on high-sodium wastes.
- **Re-attribution under adjusted WAC** — relaxing a criterion re-blends campaigns via a quadratic program that minimizes drift from original layer fractions while preserving throughput, with a bounded drop-and-retry when infeasible.

## Verified results

- Property models **reproduce PNNL-35884 Table 3-6 to published precision** (1–4%) — the acceptance gate for the property engine. This required evaluating each model on its own declared basis: a shared full composition basis biases viscosity low by 12–25% and normalized release low by 30–70%.
- Per-former oxide yields recover raw glass-former demands correctly (boric acid carries 0.563 as-fired B₂O₃); treating solver outputs as powder masses underfeeds boron by ~44%.
- Custom scenarios: any (ρ, solids) combination synthesizes from anchors and round-trips the published set to ≤0.8% mass / ≤0.4% volume across all 32 published tags. A custom 120.105.200 condition yields 42 campaigns, 21,973 t glass, 7,095 canisters, 18.5 years at 5 t/d and 65% availability.
- An App-E-style Excel export reproduces the published workbook (12/18 exact matches, 4 close) so results remain auditable against the source document.

## What's next

Wash-efficiency coupling to the facility model, additional property/companion models (nepheline, spinel, TCLP), and deeper WAC sensitivity studies across the published scenario set.
