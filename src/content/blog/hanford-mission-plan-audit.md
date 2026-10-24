---
title: 'A technical challenge to Hanford mission planning'
description: 'The Hanford Mission Plan rests on models built and reviewed by the same organizations whose schedules they justify. We are building an open, first-principles HLW mission model to check them.'
pubDate: 2026-10-24
tags: ['nuclear engineering', 'modeling', 'waste treatment', 'open source']
---

Every few years, the Department of Energy, its contractors at the Hanford Tank Farms, and the Washington State Department of Ecology publish the Hanford Mission Plan. It has grown into a multi-hundred-page document driven primarily by mission planning models, and those models decide what the cleanup will cost, how long it will take, and which Tri-Party Agreement deadlines are achievable.

Nobody independent audits them. The models are built, run, and reviewed inside the same organizations whose schedules and budgets they justify. That gap is what this project is about. We are building an open, first-principles model of the Hanford waste treatment mission and publishing all of it: the data, the code, and the results. Part one is a process model of the HLW system, built up from physics and published operating assumptions. Part two is a mission model that plans campaigns the way the official documents do, so the two can be compared head to head. The goal is a fair, fully open analysis of the Hanford HLW cleanup mission that anyone can inspect.

## Starting from the tanks

We start with what is public. Waste compositions for every tank come from Hanford's Best-Basis Inventory, and the first job is validating our compositions against that data before anything downstream runs. From there, published assumptions about retrieval and campaign generation distill the tank farms into a sequence of waste compositions: the same campaign structure the official models plan against, rebuilt entirely from public inputs.

## Why the HLW mission

We focus on the HLW mission because that is where most of the Hanford risk lives. The long-lived radionuclides ride in a complex mixture of process chemicals, and that mixture has to be immobilized in glass for geological disposal. Once campaigns are generated in the tank farms, they feed the HLW process one after another. The model follows the streams the way the melter would see them: waste in, glass out, and the material the glass does not capture, offgas and byproducts, routed to further processing.

## The independence problem

Current Hanford mission planning is part technical work, part legal and political effort. DOE uses the planning documents and the models behind them to justify shifting the deadlines in the TPA. And the stakeholders are not independent: the same organizations write the models, run them, review the results, and live inside the outcomes. Results can drift toward a preferred schedule rather than toward what the data supports.

None of this requires assuming bad faith. It only requires noticing that no independent check exists, and deciding to build one. When our numbers differ from the official ones, the difference will be traceable to a specific input or assumption, because every one of ours is public.

The tank waste data is already on the [open data page](/data/). The mission model comes next, and it will land here first.
