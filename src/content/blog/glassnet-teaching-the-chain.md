---
title: 'Teaching a network the glass formulation chain'
description: 'Training a PyTorch surrogate on 3,503 mission-model formulations: feed analysis to recipe, glass, and thirteen property flags in 50 ms — plus what a network must never be allowed to learn.'
pubDate: 2026-10-15
tags: ['machine learning', 'pytorch', 'glass chemistry', 'surrogate modeling']
---

For two years the modeling tools in this lab have shared one habit: they are slow in the specific way that optimization is slow. The campaign builder formulates every campaign as a constrained optimization against a chain of glass property models, and that is the correct thing for planning a mission years out. It is the wrong tool for the moment a laboratory calls with a batch analysis and wants a first read today.

So I exported the campaign builder's decisions into a training corpus and taught a neural network to give the same answers faster. The corpus is 3,503 campaign-level formulations across 34 waste scenarios and 10 waste families. Each row holds the feed oxide blend, the optimal glass-former recipe, the final glass composition, and thirteen property outputs from the published property models. The network, GlassNet, reads a feed and returns the recipe, the glass, and property flags for every acceptance limit, in under fifty milliseconds on a laptop CPU. The same answer through the optimizer takes minutes.

## What the network is never allowed to learn

The most useful design decision was noticing what the problem hands you for free. The final glass composition is not free information that needs predicting. It is an exact linear function of the feed, the waste loading, and the recipe: glass = WL·feed + Σ xₖeₖ. The dataset obeys this identity to 4×10⁻⁴ wt%. So GlassNet never predicts the glass. It predicts the loading and the recipe, then assembles the glass analytically from the identity. Composition sums to exactly 100, the mass ledger closes by construction, and property error stays isolated from recipe error during training.

The recipe fractions are constrained the same way. They have to sum to one minus the waste loading, because the waste and the formers together are the whole glass. A plain regression head would violate that sum on the first weird feed. Decoding through a renormalized sigmoid makes the constraint hold for any network output, so the constraint can't drift out from under you as training moves weights around.

This is the general pattern I keep landing on in this lab: assemble what has a closed form, learn only what needs learning. The network is smaller, the training is shorter, and the outputs are trustworthy by construction rather than by checkpoint.

## The honest holdout

A stratified random split on this corpus is flattering and nearly meaningless, because sibling scenarios inside a waste family share most of their composition space. Train on 90% of family A and test on the other 10%, and the network is mostly being tested on compositions it has seen before.

The number that matters is on families it has never seen. Holding out two entire waste families, 1,113 rows from compositions with no relatives in training: waste-loading error 0.62 wt%, recipe error 0.0051 of former mass, viscosity at 1150 °C to 0.10% median relative error, and zero false acceptances on every acceptance limit the data exercise except a small product-consistency tail.

That last clause needs its own paragraph. The old training corpus had a problem you would never notice from the accuracy tables: the campaign builder only returns passing recipes, so almost no row violated any limit. A network trained on it learns to predict "pass" trivially. The rebuilt dataset packs more campaigns per scenario, regenerated feed layer vectors, and a corrected durability engine, so the property ranges now genuinely straddle the limits. Product consistency spans 0.16 to 14 g/m² against a 6.44 limit. The flag statistics finally mean something.

## The most useful table in the paper

Before claiming the network needed to be a network, I fit a closed-form ridge regression on the same transformed inputs, with the regularizer chosen in the baseline's favor. On the family holdout it lands 4.5 wt% waste-loading error against the network's 0.62. Both unseen families sit near 4.5. The linear model cannot cross family boundaries at all where the network holds level.

A factor of seven is the whole capacity argument in one comparison. It says the feed-to-loading map is nonlinear in exactly the structure that separates waste families, and that whatever the network learned, it wasn't curve-fitting a linear trend. If ridge had come in at 0.9, the honest move would have been to ship the ridge.

## Trust views

Accuracy tables do not build trust with the analyst who has to use the thing, so the app ships three views computed live from the trained weights.

The first is a PCA map of all 3,503 training feeds with your feed projected on it, nearest-neighbor envelope drawn. If your composition is drifting out of the cloud, you can see that you are asking for extrapolation before you trust a number.

The second is true gradient attribution, ∂WL/∂input by autograd, ranked and signed, with a signal-path diagram from the strongest inputs through the most active neurons into the heads. When the loading moves, you can see which oxides moved it.

The third is a Monte Carlo dropout consensus: fifty stochastic passes with dropout active, and the histogram of waste loadings the network itself produces. The median feed shows a 1.41 wt% spread, and the spread tracks actual error on the holdout, so a wide histogram is a real warning, not decoration.

## Where this goes

The open gate is measurement. Every error in this post is known against the formulation model, not against real glass, and the network is a surrogate of the formulation chain, not of the melter. The validation program is well-defined: melt a set of batches spanning the families, measure the properties the limits touch, compare against prediction with the same flag-agreement statistics. If measured accuracy holds near model accuracy, the surrogate becomes admissible as a screening instrument. If it lags, the discrepancy map points at exactly where the formulation chain itself needs work. Either outcome is useful, which is my favorite kind of experiment.

The next modeling step is closing the loop into mission planning, where a millisecond answer to "is there a passing glass for this blend" changes what the planner can ask. Screening thousands of candidate blends per planning run is something the optimizer cannot do, and something a mission planner might want.

The code is on GitHub, the white paper documents the architecture and every number above, and the app runs from a clean clone with two commands. If you formulate glass for a living, I would like to hear what your lab reports look like.
