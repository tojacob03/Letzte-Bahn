-- Car travel time from every origin cell to the nearest destination of each category.
-- Rail stations count if trains depart there in any analysis window.
with travel_times as (
    select
        tt.origin_idx,
        d.dest_key as poi_id,
        tt.minutes
    from {{ ref('stg_travel_times_car') }} as tt
    inner join {{ ref('stg_destinations') }} as d
        on d.dest_idx = tt.dest_idx and d.dest_kind = 'poi'
),

served_stations as (
    select distinct poi_id
    from {{ ref('stg_station_service') }}
    where departures > 0
),

eligible_pois as (
    select
        poi_id,
        category,
        is_strict
    from {{ ref('stg_pois') }}
    where category <> 'rail_station' or poi_id in (select poi_id from served_stations)
),

poi_times as (
    select
        tt.origin_idx,
        e.category,
        e.is_strict,
        tt.minutes
    from travel_times as tt
    inner join eligible_pois as e on e.poi_id = tt.poi_id
),

nearest as (
    select origin_idx, category, min(minutes) as minutes
    from poi_times
    group by origin_idx, category

    union all

    select origin_idx, 'gp_strict' as category, min(minutes) as minutes
    from poi_times
    where category = 'gp' and is_strict
    group by origin_idx
),

spine as (
    select
        c.cell_id,
        c.cell_idx,
        k.category_id as category
    from {{ ref('stg_cells') }} as c
    cross join {{ ref('categories') }} as k
    where c.is_origin
)

select
    spine.cell_id,
    spine.category,
    nearest.minutes
from spine
left join nearest
    on nearest.origin_idx = spine.cell_idx and nearest.category = spine.category
