# Data sources and licenses

The license and terms of every source were checked on **28 September 2026**, before any
data was used. Nothing without a clear open license is part of the pipeline.

Every pipeline run records, per downloaded file, the URL, the final URL after redirects,
the HTTP `Last-Modified` header, the SHA-256 checksum and the retrieval time
(`data/raw/manifest.json` during the run). These retrieval dates are published with each
snapshot in `data/published/snapshots/<snapshot>/metadata.json` and `web/data/meta.json`.

## Overview

| Source | Used for | License | Main obligations | Retrieved |
| --- | --- | --- | --- | --- |
| GTFS Germany, [gtfs.de](https://gtfs.de/de/feeds/de_full/) (from the DELFI e.V. NeTEx dataset) | Timetable, rail stations | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Credit DELFI e.V. and gtfs.de, link the license, state changes | every run |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) via [Geofabrik](https://download.geofabrik.de/europe/germany.html) | Street and path network, destinations | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) | "© OpenStreetMap contributors"; derived databases under ODbL | every run |
| [Zensus 2022](https://www.destatis.de/zensus2022) population grid (Statistische Ämter des Bundes und der Länder) | Population per 100 m cell | [dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0) | Source note, license reference with link, note on changes | every run |
| [VG250](https://gdz.bkg.bund.de/index.php/default/verwaltungsgebiete-1-250-000-stand-01-01-vg250-01-01.html), Stand 01.01.2026 (BKG) | Municipal and state boundaries | [dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0) | "© BKG (year) dl-de/by-2-0" with links, note on changes | every run |
| [OpenFreeMap](https://openfreemap.org) | Background map tiles on the website | Free public instance, no key | Attribution "OpenFreeMap © OpenMapTiles, data from OpenStreetMap" | loaded by the browser |
| [KMK Ferienkalender](https://www.kmk.org/service/ferien.html) 2026/27 and 2027/28 | School holidays, to avoid them as analysis days | Public dates (facts) | none | 2026-09-28 |

## Details

### Timetable: GTFS Germany (gtfs.de / DELFI e.V.)

- **URL:** `https://download.gtfs.de/germany/free/latest.zip` (feed "Deutschland gesamt")
- **License:** the feed page states Creative Commons 4.0 (CC BY 4.0). The data are derived
  from the national NeTEx dataset of DELFI e.V. (the cooperation of the federal states for
  timetable data); the feed's `feed_info.txt` and `attributions.txt` name DELFI e.V. and
  gtfs.de, and DELFI publishes its data under CC BY as well.
- **Coverage:** the free feed is generated daily and covers roughly the next 30 days. It
  contains no history, which is why this project keeps its own snapshots.
- **Changes made:** the feed is clipped to all trips that stop in the network area of the
  region (kept with all their stops); unused stops, routes and agencies are dropped.
- **Attribution used:** "Fahrplandaten: DELFI e.V., bereitgestellt über gtfs.de, Lizenz
  CC BY 4.0; auf die Region zugeschnitten."
- **Not used:** the direct DELFI download on opendata-oepnv.de requires a user account.
  DELFI's public archive of weekly GTFS files would allow historical comparisons, but it
  is produced by a different conversion than gtfs.de; mixing both would make differences
  between snapshots partly an artefact of processing, so it is deliberately not mixed in.

### Street network and destinations: OpenStreetMap

- **URLs:** `https://download.geofabrik.de/europe/germany/saarland-latest.osm.pbf` and
  `.../rheinland-pfalz-latest.osm.pbf` (neighbouring state for the 20 km buffer)
- **License:** Open Database License 1.0. Produced works must credit OpenStreetMap;
  adapted databases that are publicly used must be shared under the ODbL.
- **Consequence for this project:** the published results (`web/data/`,
  `data/published/`) are a database derived in part from OpenStreetMap and are released
  under the ODbL (see `DATA_LICENSE.md`). The code is MIT-licensed.
- **Changes made:** cut to the network area with osmium; destinations classified by tags
  (rules in `src/transit_atlas/pois.py` and `METHODOLOGY.md`).

### Population: Zensus 2022 grid

- **URL:** `https://www.destatis.de/static/DE/zensus/gitterdaten/Zensus2022_Bevoelkerungszahl.zip`
  with the dataset description (`Datensatzbeschreibung_Bevoelkerungszahl_Gitterzellen.xlsx`)
- **License:** the dataset description licenses the data under the Datenlizenz
  Deutschland – Namensnennung – Version 2.0; copyright of the Statistische Ämter des Bundes
  und der Länder.
- **Data notes from the description:** reference date 15 May 2022; the Cell-Key method
  slightly perturbs counts for statistical confidentiality, so cell values need not add up
  to official totals; cells without residents are not listed; a small number of residents
  (8,766 nationwide) could not be assigned to grid cells.
- **Changes made:** 100 m cells aggregated to 500 m cells with population-weighted
  centroids.
- **Attribution used:** "Bevölkerung: Zensus 2022, © Statistische Ämter des Bundes und der
  Länder, dl-de/by-2-0; auf ein 500-m-Raster zusammengefasst."

### Boundaries: VG250 (BKG)

- **URL:** `https://daten.gdz.bkg.bund.de/produkte/vg/vg250_ebenen_0101/aktuell/vg250_01-01.utm32s.gpkg.ebenen.zip`
- **License:** Datenlizenz Deutschland – Namensnennung – Version 2.0. Required attribution
  "© BKG (year of the last data retrieval) dl-de/by-2-0", where BKG and the license are
  linked.
- **Changes made:** municipalities of the region selected; outlines simplified for the web
  (shared borders preserved). Therefore marked "Daten verändert".

### Background map: OpenFreeMap

- **Style:** `https://tiles.openfreemap.org/styles/positron`
- **Terms:** the public instance is free, without registration, API keys or view limits;
  attribution is required and shown in the map corner automatically.

## Where the attribution appears

- In the footer of every page of the website and in the map corner.
- In this file, `DATA_LICENSE.md` and the README.
