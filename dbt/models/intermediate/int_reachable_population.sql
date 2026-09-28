-- Population reachable within each travel-time threshold: the stand-in for "opportunities"
-- because open job data on a small grid does not exist. The own cell always counts.
with pt as (
    select
        tt.window_id,
        tt.origin_idx,
        d.dest_key as cell_id,
        tt.minutes
    from {{ ref('stg_travel_times_pt') }} as tt
    inner join {{ ref('stg_destinations') }} as d
        on d.dest_idx = tt.dest_idx and d.dest_kind = 'cell'
),

car as (
    select
        tt.origin_idx,
        d.dest_key as cell_id,
        tt.minutes
    from {{ ref('stg_travel_times_car') }} as tt
    inner join {{ ref('stg_destinations') }} as d
        on d.dest_idx = tt.dest_idx and d.dest_kind = 'cell'
),

pt_reach as (
    select
        pt.window_id,
        pt.origin_idx,
        th.threshold_min,
        sum(dest.population) as population
    from pt
    inner join {{ ref('stg_cells') }} as dest on dest.cell_id = pt.cell_id
    inner join {{ ref('stg_thresholds') }} as th on pt.minutes <= th.threshold_min
    group by pt.window_id, pt.origin_idx, th.threshold_min
),

car_reach as (
    select
        car.origin_idx,
        th.threshold_min,
        sum(dest.population) as population
    from car
    inner join {{ ref('stg_cells') }} as dest on dest.cell_id = car.cell_id
    inner join {{ ref('stg_thresholds') }} as th on car.minutes <= th.threshold_min
    group by car.origin_idx, th.threshold_min
),

car_available as (
    select count(*) > 0 as available
    from {{ ref('stg_travel_times_car') }}
),

spine as (
    select
        c.cell_id,
        c.cell_idx,
        w.window_id,
        th.threshold_min
    from {{ ref('stg_cells') }} as c
    cross join {{ ref('stg_windows') }} as w
    cross join {{ ref('stg_thresholds') }} as th
    where c.is_origin
)

select
    spine.cell_id,
    spine.window_id,
    spine.threshold_min,
    coalesce(pt_reach.population, 0) as reachable_population_pt,
    case when car_available.available then coalesce(car_reach.population, 0) end
        as reachable_population_car
from spine
cross join car_available
left join pt_reach
    on pt_reach.origin_idx = spine.cell_idx
    and pt_reach.window_id = spine.window_id
    and pt_reach.threshold_min = spine.threshold_min
left join car_reach
    on car_reach.origin_idx = spine.cell_idx
    and car_reach.threshold_min = spine.threshold_min
