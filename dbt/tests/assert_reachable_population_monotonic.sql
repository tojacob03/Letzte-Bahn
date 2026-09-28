-- A longer travel-time budget can never reach fewer people.
with ordered as (
    select
        cell_id,
        window_id,
        threshold_min,
        reachable_population_pt,
        lag(reachable_population_pt) over (
            partition by cell_id, window_id order by threshold_min
        ) as previous_population
    from {{ ref('fct_cell_reachability') }}
)

select *
from ordered
where reachable_population_pt < previous_population
