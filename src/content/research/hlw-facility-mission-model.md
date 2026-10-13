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

Planning analyses for the Hanford tank waste mission have historically split the problem at the facility fence line: upstream studies produce a feed schedule and blend composition; downstream studies assume a feed and size the plant. The coupling is where the interesting engineering lives.

- A campaign blend that satisfies waste acceptance criteria on paper can still **drive the off-gas train hard** — soluble nitrate and sulfate that survive retrieval washing volatilize in the melter and load the scrubber and catalytic reactors.
- A feed that is comfortable for the melter can strand heel material that **doubles the number of campaigns**.
- Every retrieval decision — which tank drains when, how much wash water follows it — propagates directly into how much glass, how many canisters, and how many years the mission takes.

I wanted one continuous data path from tank inventory chemistry to stack composition and operator schedules.

## The approach

The model is a chain of unit-operation modules built on one shared thermodynamic core:

- **Species library & Stream core** — every chemical species is tracked explicitly (ideal gases with NASA Shomate polynomials, aqueous ions, condensed oxides and hydrates, radioisotopes). A `Stream` carries molar flow per species, phase, temperature, and pressure; enthalpy sums formation plus sensible heat evaluated in each species' own phase, which is what makes flash duties close against unit-level energy balances.
- **Melter partition engine** — the heart of the model. Feed species decompose to a per-element ledger; scenario-supplied decontamination factors move a computed fraction of each volatile element to off-gas; the remainder resynthesizes as glass oxides. Residual-ledger gates and partner-atom capping guarantee no synthesis fabricates atoms.
- **Full off-gas train** — subsurface boiler scrubber → wet electrostatic precipitator → mist eliminator → reheater → HEPA → activated carbon → silver mordenite → regenerative heat exchanger → selective catalytic oxidation → selective catalytic reduction → stack. Each unit applies per-species capture factors and thermodynamic state changes on the same Stream basis.
- **Mission coupling** — campaigns arrive from the companion EWG campaign builder (RPP-RPT-64878 §6.2 sequencing, Appendix D layer vectors, EWG2.5 glass formulation), converted to speciated feed via a bridge with locked species-mapping rules.
- **Discrete operations layer** — an experimental scheduler executes the SME operator recipe serially (prepare → receive → mix → sample → QC → GFC → transfer), answering not only *how much* but *when*.

## Verified results

Verification is built into the workflow rather than bolted on:

- **135+ automated tests** — per-species mass closure with hybrid absolute/relative tolerances, energy closure with explicit duty reporting, saturation-point physical anchors, and a reagent-inclusive element audit across the entire train boundary.
- On a representative 59-campaign mission, all 38 tracked elements close to better than 1% relative; the single worst residual is a trace arsenic flow whose 21% relative error amounts to ~1 µg/s absolute.
- **Wash-efficiency sensitivity**: lowering retrieval wash efficiency from 0.9 to 0.5 nearly doubles mission glass (45.0 → 86.2 kt) and extends mission runtime from 9,044 to 16,033 days — quantifying, for the first time in this toolchain, the mission-level effect of quadrant washing strategy.
- **Discrete vs. continuous**: under the SME's serial batch recipe the MFPV is *not* the bottleneck — a 3-campaign mission runs 424 days discrete vs ~724 days under the continuous model's uniform pacing, with mass totals invariant to 5e-14.
- A full campaign simulates in 1–2 seconds; a full mission in ~76 seconds — fast enough for Monte-Carlo sensitivity sweeps over feed-rate uncertainty.

## What's next

Ongoing work: SME review of the interactive PFD and discrete layer, deeper condensate chemistry coupling to the LAW plant, and exporting the master campaign workbook as an auditable deliverable.
