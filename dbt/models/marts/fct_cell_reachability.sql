select
    cell_id,
    window_id,
    threshold_min,
    reachable_population_pt,
    reachable_population_car,
    case
        when reachable_population_car > 0
            then round(reachable_population_pt / reachable_population_car, 3)
    end as pt_car_reach_ratio
from {{ ref('int_reachable_population') }}
