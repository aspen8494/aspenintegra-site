---
title: 'Verification as a design choice: mass closure as a contract'
description: 'How the HLW mission model enforces element conservation with hybrid tolerances, residual-ledger gates, and reagent-inclusive audits, and why the verification suite is the product.'
pubDate: 2026-10-13
tags: ['modeling', 'verification', 'engineering practice']
---

Engineering models earn trust one verified closure at a time. When a model predicts stack emissions or mission duration for a nuclear facility, "it looks right" is not a verification strategy. The HLW facility mission model treats verification as a first-class design choice, and the techniques generalize to any serious simulation work.

## Hybrid mass-closure tolerances

A per-species mass check passes if the relative residual is below 1e-4 or the absolute residual is below 1e-9 mol/s. The hybrid form exists because both pure tests fail:

- A pure relative test flags trace isotopes at 1e-12 mol/s whose integration residue is physically meaningless.
- A pure absolute test would pass a real leak on a major species.

Tolerances should encode the physics of the quantity being checked, not the convenience of a single threshold.

## The residual-ledger gate

After the melter decomposes feed species to a per-element ledger and resynthesizes glass and off-gas, the obvious check is total mass in equals total mass out. That check alone can hide stranded elements. Mass can balance while a trace element silently vanishes into a rounding error.

So the engine asserts that the unallocated residual ledger stays near zero after synthesis, as a separate explicit check from total mass closure. Every element must be explicitly accounted, whether it lands in glass, off-gas, or a flagged residual; nothing is dropped implicitly.

## Reagent-inclusive boundary audits

An element audit across the whole train boundary that forgets its own reagents reports hydrogen, oxygen, and nitrogen "failures" that are bookkeeping errors, not physics errors. The audit therefore folds every external reagent, including wash water, SCR ammonia, and quench make-up, into the inlet ledger before products are compared.

## What verification buys

The suite runs 135+ automated tests: per-species closure with hybrid tolerances, energy balances with explicit duty reporting, saturation-point anchors, and regressions for every subject-matter-expert finding. The payoff compounds:

- Every new unit operation inherits the same Stream basis and the same closure tests, so integration risk stays bounded.
- When a result surprises you, you can quickly tell a model bug from physical insight, because the conservation skeleton is proven.
- SME review time goes to the assumptions, not the arithmetic.

One lesson from building this toolchain: the verification suite is the product. Predictions are transient. The guarantee that they're conserved, anchored, and reproducible is what keeps the tool worth maintaining over a decades-long mission.
