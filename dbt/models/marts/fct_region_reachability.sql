-- Reachable population for the whole region: population-weighted mean and median.
with cell_values as (
    select
        r.window_id,
        r.threshold_min,
        c.region_population as weight,
        r.reachable_population_pt,
        r.reachable_population_car
    from {{ ref('fct_cell_reachability') }} as r
    inner join {{ ref('dim_cells') }} as c on c.cell_id = r.cell_id
    where c.region_population > 0
),

means as (
    select
        window_id,
        threshold_min,
        sum(weight) as population,
        round(sum(weight * reachable_population_pt) / sum(weight))
            as mean_reachable_population_pt,
        round(sum(weight * reachable_population_car) / sum(weight))
            as mean_reachable_population_car
    from cell_values
    group by window_id, threshold_min
),

median_pt as (
    {{ weighted_median_query('cell_values', 'reachable_population_pt', 'weight',
                             ['window_id', 'threshold_min']) }}
),

median_car as (
    {{ weighted_median_query('cell_values', 'reachable_population_car', 'weight',
                             ['window_id', 'threshold_min']) }}
)

select
    means.*,
    nullif(median_pt.weighted_median, 'infinity'::double) as median_reachable_population_pt,
    nullif(median_car.weighted_median, 'infinity'::double) as median_reachable_population_car
from means
left join median_pt using (window_id, threshold_min)
left join median_car using (window_id, threshold_min)
