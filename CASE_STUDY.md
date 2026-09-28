# Case study: Letzte Bahn – how well is every place connected by bus and train?

## Problem

Whether you can live without a car depends on where you live. Timetables answer "when is
the next bus?", but not the question people and planners actually have: *from my home,
what can I reach in reasonable time – and what if I need it in the evening or on a
Sunday?* Existing accessibility studies are often one-off reports with a single departure
time and no way to check the numbers.

Goal: a public, reproducible atlas for a pilot region (Saarland) that measures, for every
inhabited 500 m square and every municipality, the travel time to everyday destinations,
the number of people within reach, the gap to the car, and the difference between weekday
mornings, evenings and Sundays – built only from open data and running at zero cost.

## Approach

1. **Sources and licenses first.** Checked the terms of every candidate source before
   using it and documented obligations (CC BY 4.0, ODbL, Datenlizenz Deutschland). One
   source (the direct DELFI download) was rejected because it requires an account; an
   archive with history was not mixed in because its different processing would create
   artificial changes.
2. **Pipeline in Python.** Streamed the 2 GB national timetable out of its zip archive
   and clipped it with pyarrow and DuckDB; aggregated the census grid with
   population-weighted centroids; classified OpenStreetMap destinations with explicit,
   unit-tested rules; picked representative analysis days automatically (school days,
   holidays, timetable change, days with unusually little service).
3. **Routing.** Used the open-source router R5 via r5py and parallelised it over origins,
   computing the median travel time over every departure minute of each time window.
4. **Data model in dbt (DuckDB).** Layered staging → intermediate → marts, with reusable
   macros for population-weighted medians, spatial neighbour detection, snapshot-to-snapshot
   change and the headline findings. Data tests guard business rules (e.g. reachable
   population can only grow with a longer time budget).
5. **Testing.** Unit tests plus a dbt build on a synthetic data set whose expected values
   are worked out by hand; CI on every push.
6. **Delivery.** GitHub Actions runs the whole pipeline on a schedule, stores each timetable
   snapshot, and publishes a static website (MapLibre, German) and the dbt documentation to
   GitHub Pages. README, website and this document take their numbers from the pipeline.

## Result

<!-- results:start -->
<!-- results:end -->

The live atlas: https://tojacob03.github.io/Letzte-Bahn/

## Transferable skills

| In this project | In a data / BI / controlling role |
| --- | --- |
| Checking licenses and documenting data lineage (manifest with checksums and dates) | Data governance, audit trails, source documentation |
| Python pipeline on messy public data (GTFS, OSM, census) | ETL/ELT, integrating heterogeneous sources |
| dbt layers, macros, tests and documentation | Analytics engineering, maintainable SQL models, data quality |
| Defining KPIs precisely (median over departures, population weighting, NULL semantics) | KPI definitions that stakeholders can trust and reproduce |
| Snapshots and change over time | Period-over-period reporting, versioned figures |
| Findings and charts written for non-experts | Management reporting and data storytelling |
| Zero-cost automation in GitHub Actions | CI/CD, scheduling, cost awareness |
| Documenting limitations openly | Honest communication of uncertainty |
