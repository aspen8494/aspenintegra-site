---
title: 'An Unsupervised Taxonomy of Tank Waste Across Hanford and Savannah River'
description: 'Unsupervised learning organizes Hanford''s 177-tank Best-Basis Inventory into data-driven waste families, then screens Savannah River''s measured batches against that taxonomy: strong radionuclide analogs for the salt waste, no Hanford analog for the titanate-bearing PRFT batches, and an honest accounting of what the coverage gaps allow you to conclude.'
pubDate: 2026-10-18
tags: ['machine learning', 'unsupervised learning', 'nuclear engineering', 'data engineering', 'waste treatment']
repo: 'https://github.com/aspen8494/srs-tank-waste-database'
repoLabel: 'srs-tank-waste-database'
weight: 12
status: active
paper:
  file: '/unsupervised-taxonomy-white-paper.pdf'
  pages: 22
---

## The problem

Hanford and Savannah River hold the two largest legacy tank-waste inventories in the country, but they publish them on completely different footings: Hanford as a per-tank Best-Basis Inventory of current waste, SRS as closure residuals plus a small set of measured qualification samples. Nobody has published a compositional map between the two. Without one, "is waste like this treated anywhere else?" stays a question for tribal knowledge instead of data.

This project builds that map with unsupervised learning, deliberately: no site labels, no waste-type codes, no treatment assignments enter the fit. The taxonomy that emerges is then used as a screening instrument for the one thing SRS publishes that resembles current waste, its SRNL qualification samples.

## The approach

Every analyte set is treated as a closed composition and analyzed in Aitchison geometry: a centered log-ratio transform makes the entire unit problem between the sites disappear, because a composition scaled by any constant has identical CLR coordinates. Three analyte panels are clustered independently: sludge elements (158 Hanford tank-phases, 25 features), salt anions and cations (258 points, 15 features), and radionuclides (415 points, 41 features, decay-corrected to a common date).

Ward hierarchical clustering produces the final taxonomy, with K chosen by silhouette over a KMeans sweep, cross-checked for method stability. HDBSCAN flags density outliers for data-quality review, and UMAP renders the geometry for the eye without ever driving the assignments. SRS samples are never re-fit into the clusters: they are projected into the Hanford geometry, with each projection scored by percentile against the target cluster's own member-to-centroid distances and by how many analytes the analog claim actually rests on.

## What it found

- **SRS salt batches have real Hanford analogs.** The SWPF batches project at the 68–74th percentile of their radionuclide cluster with top-analog distances below Hanford's own median — genuinely strong analogs, landing near the AP108/AZ102/AN104-class high-cesium supernates. In salt chemistry they sit at the 97–98th percentile: near-analogs at the cluster edge, not twins. The pairing is physically coherent: boehmite- and zeolite-aged salt liquors on both sites.
- **The PRFT batches have no Hanford analog.** All three sit at the 100th percentile of their assigned cluster, driven by their monosodium-titanate content — an engineered sorbent Hanford does not use. "No analog" is the correct answer, not a data gap.
- **SRS sludge batches land within Hanford's normal spread, at its outer half.** SB11's nearest analog is a REDOX-class sludge solid with a similar aluminum/iron/uranium balance, though measured on only four shared elements.
- **Anomaly flags concentrate where the waste is genuinely unusual.** 87 sludge and 138 salt panel points flag as density outliers, candidates for data-quality review rather than confirmed errors.
- **The method is stable.** Ward and KMeans agree at ARI 0.71–0.79 across all three panels, so the structure is not an artifact of the clustering choice.

## Honest limitations

Coverage is stated, not hidden: SRS samples carry 37% (sludge), 77% (salt), and 25% (radionuclide) of panel analytes on average, and every analog claim ships with its support size. Batches with no shared chemistry are refused as insufficient data rather than imputed. The basis asymmetry remains the governing caveat: Hanford's inventory is current waste, SRS per-tank vectors are closure residuals that appear only in a flagged track, and a large projection percentile means "no true analog at Hanford," which is an informative result.

## The paper and the explorer

The full 22-page white paper documents the mathematics, the model selection, the per-panel results, and the caveats, and is embedded below. Every number is reproducible from the published database on the Open Data page. An interactive analog explorer — every SRS sample against every Hanford cluster, with the supporting analytes listed — lives in the repository.
