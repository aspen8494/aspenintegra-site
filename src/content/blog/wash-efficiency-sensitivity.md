---
title: 'Washing the waste: how one retrieval parameter doubles a mission'
description: 'A sensitivity study from the HLW facility mission model. Lowering retrieval wash efficiency from 0.9 to 0.5 nearly doubles mission glass (45.0 to 86.2 kt) and stretches the mission from 9,044 to 16,033 days. The coupling explains why.'
pubDate: 2026-10-12
tags: ['nuclear engineering', 'modeling', 'hanford']
---

One of the first genuinely useful questions my HLW facility mission model could answer was deceptively simple: what happens to the whole mission if the tanks are washed less thoroughly during retrieval?

The mechanism is worth walking through, because it's a textbook case of planning and facility models needing to be coupled.

## Why washing matters

Waste in a Hanford tank is layered: supernatant liquor over saltcake over sludge. Retrieval doesn't get everything. A heel of sludge remains on the floor of nearly every tank, and that heel carries a disproportionate share of the mission's problem species.

Washing the heel mobilizes and decants soluble species like sodium salts, nitrates, and sulfates into the low-activity waste stream, where they're cheap to immobilize in cast stone. Whatever doesn't wash out rides along to the high-level waste facility, where every ton of soluble salt has to go somewhere: through the melter, out the off-gas train, and eventually into the glass.

Wash efficiency η is the fraction of soluble species actually decanted during retrieval. The model re-synthesizes every heel record at any specified η, so the question became a parameter sweep instead of a debate.

## What the model says

Across two published scenarios, the sweep is not subtle:

| Wash efficiency | Mission glass (135.105.200) | Mission runtime |
|---|---|---|
| 0.90 | 45.0 kt | 9,044 days |
| 0.50 | 86.2 kt | 16,033 days |

Nearly double the glass and 77% more calendar time from one retrieval parameter. The mechanism compounds through three coupled paths:

1. More mass to glass. Unwashed soluble species ride the heel into HLW feed. Every retained ton of sodium must be diluted into glass to keep melt chemistry feasible, so the glass-forming optimizer adds substantially more glass-forming chemical while holding viscosity and product consistency constraints.
2. More campaigns. Heavier feeds fill the 450 to 550 kgal campaign volume band faster per ton of true waste, and heel-dominated campaigns stretch runtime. The discrete operations layer shows campaign turnarounds and QC holds multiplying along with them.
3. A hotter off-gas train. Soluble nitrate and sulfate volatilize in the melter and load the scrubber, catalytic reactors, and condensate system. The facility model tracks exactly which elements go where, and the stack numbers move accordingly.

## Why coupling is the point

An upstream planning study that stops at the facility fence line would happily recommend aggressive retrieval schedules and never price the washing question. A downstream facility study given a fixed feed can't see the washing decision at all, because it's already baked into the blend.

Only a coupled model can answer it. Closing that gap is what Aspen Integra is for.
