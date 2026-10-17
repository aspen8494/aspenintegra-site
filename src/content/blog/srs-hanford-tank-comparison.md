---
title: 'Two tank farms, one question: how do SRS and Hanford inventories actually compare?'
description: 'Our team assembled the first public SRS-vs-Hanford tank-waste comparison: 51 Savannah River tanks (33.2 Mgal, 191 MCi) against Hanford''s 177-tank BBI (53.0 Mgal, 122.6 MCi). The headline surprises: SRS holds more curies in less volume, Sr-90 and its daughters dominate SRS where Cs-137 dominates Hanford, and the two sites publish their inventories on completely different bases.'
pubDate: 2026-10-16
tags: ['nuclear engineering', 'data engineering', 'waste treatment', 'data visualization']
---

The two largest tank-waste inventories in the country sit at the Savannah River Site and Hanford. Both are legacy reprocessing waste stored as sludge, supernate, and saltcake in underground tanks, both feed vitrification plants, and both publish their inventories to the public. What nobody had done, as far as we could find, is put the two datasets side by side on a consistent footing and let people explore the comparison directly.

Our team just changed that. We assembled a Best-Basis-Inventory-style database for the SRS F- and H-Area Tank Farms, all 51 tanks, from public DOE, NRC, and SRNS documents, pulled Hanford's 177-tank Best Basis Inventory live from the public data service, and built comparison dashboards on top. The SQLite database is 56.7k rows across 9 tables; every row carries its dataset, basis, and source so the different bases cannot be mixed by accident. There is a Streamlit app for the full interactive experience and a self-contained HTML version that runs anywhere, now embedded in the playground section of this site.

## The headline numbers

As of late 2025, the sites look like this:

| | SRS (51 tanks) | Hanford (177 tanks) |
|---|---|---|
| Remaining volume | 33.2 Mgal | 53.0 Mgal |
| Remaining activity | 191 MCi | 122.6 MCi |
| Sludge | 2.8 Mgal / 106 MCi | 10.4 Mgal / 67.7 MCi |
| Supernate | 16.4 Mgal / 75 MCi | 21.3 Mgal / 30.2 MCi |
| Saltcake | 10.0 Mgal / 10 MCi | 21.3 Mgal / 24.7 MCi |
| Curie density | 5.8 MCi/Mgal | 2.3 MCi/Mgal |

Two things jump out immediately. SRS holds more than half of Hanford's radioactivity in 43 tanks, versus Hanford's 177. And the curie density at SRS is roughly 2.5 times Hanford's, 5.8 versus 2.3 MCi per million gallons.

## Finding 1: the activity sits in different phases

At SRS, 106 of the 191 MCi live in sludge, which is only 9 percent of the volume. The salt waste, 91 percent of the volume, carries 45 percent of the curies. At Hanford the picture inverts: the salt phases hold 55 MCi against the sludge's 68 MCi, but the volume split is more even, and the curie density never concentrates the way it does at SRS.

The phase story has a direct processing consequence. SRS's high curie density rides on salt waste rich in Cs-137, which is exactly what the Actinide Removal Process and the Salt Waste Processing Facility are built to strip out. Hanford's sludge fraction carries the transuranics and the Sr-90 that drive its own treatment path. Same problem class, different bottleneck species.

## Finding 2: different radionuclides dominate

Summing the per-tank closure-residual inventories at SRS puts Sr-90 and its daughter Y-90 at the top by a wide margin, each around 1.7 MCi, with Sm-151 close behind at 1.5 MCi. At Hanford, the top of the stack is the same Sr-90/Y-90 pair at 33 MCi each, but Cs-137 lands at 28 MCi, and the site total of 122.6 MCi spreads across a wider set of contributors.

The per-tank view sharpens the difference. SRS Tank 51's closure-residual top nuclides are Sr-90 and Y-90 at 130k Ci, with Pu-238 in fourth at 6.5k Ci, a fingerprint of the site's plutonium-production mission. Hanford's saltcake tanks, by contrast, are Cs-137 stories: 241-U-109 carries 154k Ci of Cs-137 against 7k Ci of Sr-90. When you normalize by volume, SRS waste is salt-dominated and Cs-rich where Hanford's is more balanced, which is precisely why the two sites' treatment trains diverged the way they did.

## Finding 3: SRS does not publish a per-tank current inventory

This is the caveat that ate the most time, and it matters for anyone who wants to use these numbers.

Hanford publishes a per-tank Best Basis Inventory: for each of the 177 tanks, the current volume and composition by phase and nuclide, refreshed regularly. SRS has nothing equivalent in public. Current per-tank composition at SRS lives in the internal Waste Characterization System, which is not released at that granularity. What is public at per-tank resolution are the closure-residual inventories from the Performance Assessments and Special Analyses: conservative, decayed-to-2032 estimates of what will remain in each tank after waste removal, built for §3116 closure determinations, not operations.

So the honest comparison uses three SRS datasets, kept separate on purpose: farm-level current totals (33.2 Mgal / 191 MCi from the Liquid Waste System Plan), per-tank closure residuals for all 51 tanks, and measured SRNL sample data for the material actually being processed, the DWPF sludge batches and SWPF salt batches. Every row in the database carries its basis, and the dashboards surface the distinction rather than hiding it. A number without its basis is how wrong conclusions get made.

## Finding 4: the closure residuals have their own quirks

The PA tables assign inventories by tank group, which means tanks of the same type carry identical assigned values except for a handful of adjusted nuclides. The conservative max-of-group assignment exists to bound closure risk, not to describe reality; the actual measured residuals for the six closed-and-characterized tanks show how conservative it is. Tank 16's measured final residual came in at 18.8k Ci against an assigned value in the same family as its group's 50k Ci. Anyone doing ML on this data needs to know that the per-tank "inventory" for most SRS tanks is an assigned bound, not a measurement.

## What we built

The database holds 51 SRS tanks across four radionuclide datasets and three chemical datasets, plus the full Hanford BBI at 46,600 rows. The parse pipeline is fully scripted: PDFs in, SQLite out, with validation that computed per-tank sums reproduce each source table's own total row. The dashboards render the head-to-head, the phase and farm distributions, the radionuclide rankings, a 228-tank explorer with per-tank drill-downs, and the measured current chemistry from the sludge and salt batch qualification reports.

The interactive version is embedded in the playground section of this site: all six sections, fully client-side, no server, nothing leaves your browser. The full database, the parse pipeline, and both dashboards are on GitHub, and the tidy ML exports are ready for the surrogate-modeling work this lab does.

Go poke at it. Find something we missed, and tell us.
