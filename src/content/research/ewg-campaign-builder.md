---
title: 'Campaign Builder & Mission Planning'
description: 'Turns tank waste inventory chemistry into sequenced retrieval campaigns with WAC evaluation, glass-forming optimization, and mission rollups, reproducing published benchmarks.'
pubDate: 2026-09-20
tags: ['optimization', 'mission planning', 'python', 'nuclear engineering']
repo: 'https://github.com/aspen8494/hlw-facility-mission-model'
repoLabel: 'Related repo'
weight: 9
status: active
---

## The problem

Large defense tank farms hold tens of millions of gallons of mixed radioactive and chemical waste across hundreds of underground tanks. The baseline mission retrieves that waste, separates most of the volume into a low-activity waste stream, and converts the sludge fraction, which bears the transuranic and cesium-strontium activity, into glass in a high-level waste vitrification facility.

Retrieval sequencing matters because the waste is heterogeneous at every scale: between tanks, between horizontal layers within a tank, and between liquid, saltcake, and sludge phases. The campaign builder answers which material moves when, in what blends, and with what glass-forming chemistry, such that every constraint holds and the mission is as short and cheap as possible.

## The approach

### Data lineage

Published tank inventory chemistry is pulled from a public data service and flattened to per-tank snapshots, about 400 MB, scripted with response-shape verification because the service can return an HTTP 200 page containing a rejection notice instead of data. Layer vectors follow a published layer-by-layer convention, extended with homogenized heel layers synthesized from whole-tank chemistry for every tank outside the published set: 38 published plus 53 heel layers, roughly 15 Mt of waste oxide.

### Stoichiometry

The element-to-oxide conversion uses n-atoms-per-oxide factors and excludes anions from oxide mass. Getting this wrong is not subtle: a naive oxide-name mapping fabricates about a kilotonne of phantom cobalt oxide across the published layer set.

### Campaign sequencing

A builder walks tanks and layers under published sequencing rules (quadrant drain order, shallowest-layer eligibility, at most five tanks per campaign, a 450 to 550 kgal volume band), refined by a linear program (HiGHS) that maximizes waste transfer subject to WAC constraints.

### Glass formulation as constrained optimization

The published glass property models act as constraint functions: product consistency, viscosity (Vogel-Fulcher-Tammann), electrical conductivity, sulfate solubility, and phosphate capacity, each with per-oxide validity bounds. The solve is SLSQP with multi-start over initial waste fractions, because a single start is infeasible-by-convergence on high-sodium wastes.

### Re-attribution under adjusted WAC

Relaxing a criterion re-blends campaigns through a quadratic program that minimizes drift from the original layer fractions while preserving throughput, with a bounded drop-and-retry when infeasible.

## Verified results

- Property models reproduce the published property benchmarks to reported precision (1 to 4%), the acceptance gate for the property engine. This required evaluating each model on its own declared basis: a shared full composition basis biases viscosity low by 12 to 25% and normalized release low by 30 to 70%.
- Per-former oxide yields recover raw glass-former demands correctly (boric acid carries 0.563 as-fired B₂O₃). Treating solver outputs as powder masses underfeeds boron by about 44%.
- Custom scenarios: any (density, solids) combination synthesizes from published anchors and round-trips the full scenario set to ≤0.8% mass and ≤0.4% volume across all 32 published conditions. A representative custom condition yields 42 campaigns, 21,973 t glass, 7,095 canisters, and 18.5 years at 5 t/d and 65% availability.
- A workbook export reproduces the published example workbook (12/18 exact matches, 4 close) so results remain auditable against the source document.

## What's next

Wash-efficiency coupling to the facility model, additional property and companion models (nepheline, spinel, TCLP), and deeper WAC sensitivity studies across the published scenario set.
