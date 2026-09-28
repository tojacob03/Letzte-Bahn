# Methodology

The atlas answers: *How many people and which everyday destinations can I reach from here
within 30, 45 and 60 minutes by public transport, and how does my place compare with its
neighbours and with the car?* This document describes how every number is produced and
where it can be wrong. A shorter German version is on the website (`web/methodik.html`).

## 1. Study area and grid

- **Pilot region:** Saarland (all municipalities with an AGS starting with `10`), set in
  `config/saarland.yaml`. Any region can be configured by its AGS prefix.
- **Buffer:** destinations and residents up to **20 km** beyond the region count, so that
  places near the border are not penalised. The buffer is restricted to German territory,
  because population and destinations abroad are not covered by the same data. The street
  and transit network extends a further 5 km.
- **Grid:** the Zensus 2022 100 m grid (EPSG:3035, INSPIRE cell codes) is aggregated to
  **500 m cells**. 500 m keeps walking distances inside a cell short while keeping the
  number of origins manageable.
- **Routing origin:** the **population-weighted centroid** of the inhabited 100 m cells in
  a 500 m cell, not its geometric centre. A cell that is half forest starts where people
  actually live.
- **Origins** are all cells with residents inside the region; buffer cells are destinations
  only. A cell crossing a municipal border contributes to each municipality with the
  population of its 100 m cells on that side.

## 2. Destinations

| Category | Source | Rule |
| --- | --- | --- |
| Family doctor (Hausarzt) | OSM `amenity=doctors` / `healthcare=doctor` | Counted unless tagged as another speciality or named as dentist / orthodontist / vet. Internists count (many work as family doctors). |
| Family doctor, strict (sensitivity) | OSM | Only `healthcare:speciality` general / Allgemeinmedizin or a name that says so |
| Pharmacy | OSM `amenity=pharmacy` / `healthcare=pharmacy` | all |
| Supermarket | OSM `shop=supermarket` | all |
| Primary school | OSM `amenity=school` | name contains "Grundschule" and similar, or ISCED level 1 |
| Secondary school | OSM `amenity=school` | Gymnasium, Gemeinschaftsschule, Realschule, Gesamtschule and similar, or ISCED 2/3; vocational and special-needs schools excluded |
| Hospital | OSM `amenity=hospital` / `healthcare=hospital` | rehabilitation, psychiatric and day clinics excluded |
| Rail station | GTFS | stops served by heavy rail (regional, S-Bahn, long-distance; no tram/light rail), counted per parent station |

Areas (buildings, sites) are represented by an interior point. Where tagging is
ambiguous, the rules include rather than exclude, so that gaps in accessibility are
**conservative** (the real situation is at least as bad). The strict doctor definition is
computed alongside (`gp_strict`) to show how sensitive the results are to this choice; a
dbt test asserts that the strict variant is never closer than the default.

A rail station only counts in a time window if at least one train departs there within
that window. Opening hours of practices and shops are **not** modelled: the atlas measures
the transport connection, not whether the door is open.

## 3. Timetable and analysis days

- Timetable: the national GTFS feed of gtfs.de (DELFI e.V.), clipped to all trips that
  stop in the network area. Trips are kept with all stops, so trains leaving the area
  keep correct timings.
- The free feed covers about 30 days. The pipeline chooses the analysis days itself
  (`src/transit_atlas/service_dates.py`):
  - a **Tuesday** that is not a public holiday of the state, not 24/31 December and not
    in the school holidays of Saarland or Rheinland-Pfalz (KMK calendar);
  - the following **Sunday** that is not a public holiday (Easter and Whit Sunday count
    as holidays);
  - days with fewer than 80 % of the usual number of trips for that weekday are skipped
    (data gaps, special timetables);
  - the first two days of a feed are skipped;
  - if the feed already covers the next **timetable change** (second Sunday in December),
    days after the change are used, so the new timetable is captured as early as possible.

## 4. Time windows and the median

Three windows are computed: **weekday 07:00–09:00**, **weekday 20:00–22:00** and
**Sunday 10:00–12:00**.

For **every departure minute** of a window, R5 computes the fastest trip, including the
wait at the origin. The reported travel time is the **median over all departure minutes**:
in half of the minutes you are faster, in the other half slower. A single lucky connection
therefore does not make a place look well served. If a destination cannot be reached
within **120 minutes** in more than half of the minutes, it counts as *not reachable*
(stored as NULL and shown as "über 2 Std.").

## 5. Routing parameters

| Parameter | Value | Note |
| --- | --- | --- |
| Router | R5 (Conveyal) via r5py 1.1.7 | origins routed in parallel threads, see `routing.py` |
| Modes | public transport + walking | a walking-only trip counts if it is faster |
| Walking speed | 4.5 km/h | on the OSM path network |
| Max. walking time | 30 min | applies to access, egress and walking-only trips in R5 |
| Max. trip time | 120 min | |
| Max. rides | 8 | r5py default |
| Car | free-flow speeds from OSM, one departure | no congestion, no parking search, no walk to the car |

The car times flatter the car. The ratio public transport ÷ car is therefore rather an
underestimate of the real gap for car owners, and an upper bound on the disadvantage of
relying on public transport.

## 6. Metrics

Per origin cell and window:

- `pt_minutes`: minutes to the nearest destination of each category.
- `car_minutes`: the same by car (window-independent).
- `pt_car_ratio`: `pt_minutes / max(car_minutes, 1)`.
- `reachable_population_pt` for 30/45/60 minutes: residents of all cells (region plus
  buffer) whose centroid is reached within the threshold, the own cell included. It stands
  in for "opportunities", because open job data on a small grid does not exist.

Per municipality and for the whole region (all weighted by population):

- **weighted median** of travel time and of the ratio. NULL (not reachable) sorts as
  +infinity, so the median is NULL when more than half of the residents cannot reach a
  destination in time (`macros/weighted_median.sql`);
- **shares** of residents reaching a destination within 15, 30 and 60 minutes and the
  share that cannot reach it at all;
- share of residents for whom public transport takes more than three times as long as the
  car (or is not possible);
- **mean reachable population** (and region-wide median);
- **neighbours:** municipalities that share a border (DuckDB spatial, `ST_Intersects`).

## 7. Snapshots and change over time

Every run on `main` publishes a snapshot named after the region and the publication day of
the timetable feed (`saarland_YYYY-MM-DD`), with all municipality metrics in long format
(`data/published/snapshots/*/municipality_metrics.csv`). The next run compares itself with
the latest earlier snapshot (`fct_municipality_change`) and the map shows the difference.
If the configuration changed between the two snapshots (config fingerprint), the website
warns that the comparison mixes method and timetable effects. Runs are scheduled twice a
month; the first comparison of two timetable years becomes possible once the feed covers
the December timetable change.

## 8. Quality checks

- **Unit tests** (pytest) for grid aggregation, census parsing, destination rules,
  holiday and analysis-day logic, GTFS clipping and the calendar.
- **dbt build on a hand-checked fixture** in CI: every expected value (weighted medians,
  shares, reachable population, station eligibility, change) is worked out by hand.
- **dbt data tests** on every run: keys unique and not null, referential integrity,
  accepted values, shares between 0 and 1, reachable population monotonic in the
  threshold, strict doctor never closer than the default, every municipality populated,
  every headline finding computable, and a warning if more than 1 % of origins reach no
  destination at all (a sign of network-linking problems).
- The run metadata report the number of origins that could not be linked to the network,
  destinations never reached, OSM schools that could not be classified, and the number of
  trips on the analysis days.

## 9. Known sources of error

- **Scheduled timetable only.** No real-time data, delays, cancellations or crowding.
- **Gaps in GTFS.** Missing or incomplete lines lower accessibility; construction works on
  the analysis day can distort one snapshot.
- **On-demand services** (Rufbus, Anruf-Sammeltaxi) are either missing or listed like
  regular trips although they must be booked in advance. Both distort results in rural
  areas, in opposite directions.
- **OSM completeness** varies, especially for doctors' practices and their specialities.
- **Opening hours** are not modelled (see section 2).
- **Border effects:** population and destinations in France and Luxembourg are missing,
  although cross-border trips are common in Saarland.
- **Grid:** a 500 m cell has one origin; walking times within the cell are not captured.
- **Car times** ignore congestion and parking.
- **Accessibility needs** (step-free access, walking speed of older people) are not
  modelled; 4.5 km/h is an average adult pace.
