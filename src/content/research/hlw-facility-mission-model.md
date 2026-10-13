---
title: 'HLW Facility Mission Model'
description: 'An element-conserving, speciated stream-flow model of the Hanford HLW vitrification facility and its complete off-gas treatment train, driven by real tank-farm campaign schedules.'
pubDate: 2026-10-01
tags: ['nuclear engineering', 'process modeling', 'python', 'thermodynamics']
repo: 'https://github.com/aspen8494/hlw-facility-mission-model'
repoLabel: 'hlw-facility-mission-model'
weight: 10
status: active
---

## The problem

Planning analyses for the Hanford tank waste mission have historically split at the facility fence line: upstream studies produce a feed schedule and blend composition, downstream studies assume a feed and size the plant. The coupling between the two is where the interesting engineering lives.

A campaign blend that satisfies waste acceptance criteria on paper can still drive the off-gas train hard, because soluble nitrate and sulfate that survive retrieval washing volatilize in the melter and load the scrubber and catalytic reactors. A feed that is comfortable for the melter can strand heel material that doubles the number of campaigns. And every retrieval decision, from which tank drains when to how much wash water follows it, propagates directly into how much glass, how many canisters, and how many years the mission takes.

I wanted one continuous data path from tank inventory chemistry to stack composition and operator schedules.

## The approach

The model is a chain of unit-operation modules built on one shared thermodynamic core.

### Species library and Stream core

Every chemical species is tracked explicitly: ideal gases with NASA Shomate polynomials, aqueous ions, condensed oxides and hydrates, radioisotopes. A `Stream` carries molar flow per species, phase, temperature, and pressure. Enthalpy sums formation plus sensible heat evaluated in each species' own phase, which is what makes flash duties close against unit-level energy balances.

### Melter partition engine

Feed species decompose to a per-element ledger. Scenario-supplied decontamination factors move a computed fraction of each volatile element to off-gas, and the remainder resynthesizes as glass oxides. Residual-ledger gates and partner-atom capping guarantee that no synthesis step fabricates atoms.

### Full off-gas train

Subsurface boiler scrubber, wet electrostatic precipitator, mist eliminator, reheater, HEPA, activated carbon, silver mordenite, regenerative heat exchanger, selective catalytic oxidation, selective catalytic reduction, then the stack. Each unit applies per-species capture factors and thermodynamic state changes on the same Stream basis.

### Mission coupling

Campaigns arrive from the companion EWG campaign builder (RPP-RPT-64878 §6.2 sequencing, Appendix D layer vectors, EWG2.5 glass formulation) and are converted to speciated feed through a bridge with locked species-mapping rules.

### Discrete operations layer

An experimental scheduler executes the SME operator recipe serially: prepare, receive, mix, sample, QC, GFC, transfer. It answers not only how much the plant processes but when.

## Verified results

Verification is built into the workflow rather than bolted on.

- 135+ automated tests: per-species mass closure with hybrid absolute/relative tolerances, energy closure with explicit duty reporting, saturation-point physical anchors, and a reagent-inclusive element audit across the entire train boundary.
- On a representative 59-campaign mission, all 38 tracked elements close to better than 1% relative. The single worst residual is a trace arsenic flow whose 21% relative error amounts to about 1 µg/s absolute.
- Wash-efficiency sensitivity: lowering retrieval wash efficiency from 0.9 to 0.5 nearly doubles mission glass (45.0 to 86.2 kt) and extends mission runtime from 9,044 to 16,033 days. This quantified, for the first time in this toolchain, the mission-level effect of quadrant washing strategy.
- Discrete vs. continuous: under the SME's serial batch recipe the MFPV is not the bottleneck. A 3-campaign mission runs 424 days discrete versus roughly 724 days under the continuous model's uniform pacing, with mass totals invariant to 5e-14.
- A full campaign simulates in 1 to 2 seconds and a full mission in about 76 seconds, fast enough for Monte-Carlo sensitivity sweeps over feed-rate uncertainty.

## What's next

Ongoing work includes SME review of the interactive PFD and discrete layer, deeper condensate chemistry coupling to the LAW plant, and exporting the master campaign workbook as an auditable deliverable.
