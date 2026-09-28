-- Travel time by public transport (walking included) from every origin cell to the nearest
-- destination of each category, per time window. NULL = not reachable within the maximum
-- trip time. Rail stations only count in a window if trains actually depart there.
with travel_times as (
    select
        tt.window_id,
        tt.origin_idx,
        d.dest_key as poi_id,
        tt.minutes
    from {{ ref('stg_travel_times_pt') }} as tt
    inner join {{ ref('stg_destinations') }} as d
        on d.dest_idx = tt.dest_idx and d.dest_kind = 'poi'
),

eligible_pois as (
    select
        p.poi_id,
        p.category,
        p.is_strict,
        w.window_id
    from {{ ref('stg_pois') }} as p
    cross join {{ ref('stg_windows') }} as w
    left join {{ ref('stg_station_service') }} as s
        on s.poi_id = p.poi_id and s.window_id = w.window_id
    where p.category <> 'rail_station' or coalesce(s.departures, 0) > 0
),

poi_times as (
    select
        tt.window_id,
        tt.origin_idx,
        e.category,
        e.is_strict,
        tt.minutes
    from travel_times as tt
    inner join eligible_pois as e
        on e.poi_id = tt.poi_id and e.window_id = tt.window_id
),

nearest as (
    select window_id, origin_idx, category, min(minutes) as minutes
    from poi_times
    group by window_id, origin_idx, category

    union all

    -- sensitivity variant: only clearly tagged family doctors
    select window_id, origin_idx, 'gp_strict' as category, min(minutes) as minutes
    from poi_times
    where category = 'gp' and is_strict
    group by window_id, origin_idx
),

spine as (
    select
        c.cell_id,
        c.cell_idx,
        w.window_id,
        k.category_id as category
    from {{ ref('stg_cells') }} as c
    cross join {{ ref('stg_windows') }} as w
    cross join {{ ref('categories') }} as k
    where c.is_origin
)

select
    spine.cell_id,
    spine.window_id,
    spine.category,
    nearest.minutes
from spine
left join nearest
    on nearest.origin_idx = spine.cell_idx
    and nearest.window_id = spine.window_id
    and nearest.category = spine.category
