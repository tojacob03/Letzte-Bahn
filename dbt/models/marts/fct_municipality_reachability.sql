-- Average number of residents reachable from a municipality's homes (population-weighted).
with cell_values as (
    select
        w.ags,
        r.window_id,
        r.threshold_min,
        w.population as weight,
        r.reachable_population_pt,
        r.reachable_population_car
    from {{ ref('fct_cell_reachability') }} as r
    inner join {{ ref('stg_cell_municipality') }} as w on w.cell_id = r.cell_id
)

select
    ags,
    window_id,
    threshold_min,
    sum(weight) as population,
    round(sum(weight * reachable_population_pt) / sum(weight)) as mean_reachable_population_pt,
    round(sum(weight * reachable_population_car) / sum(weight)) as mean_reachable_population_car,
    round(
        sum(weight * reachable_population_pt)
        / nullif(sum(weight * reachable_population_car), 0),
        3
    ) as pt_car_reach_ratio
from cell_values
group by ags, window_id, threshold_min
