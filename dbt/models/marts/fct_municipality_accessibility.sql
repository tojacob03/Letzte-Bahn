-- Population-weighted accessibility per municipality, time window and category.
-- Cells on a municipal border contribute with the population living on each side.
with cell_values as (
    select
        w.ags,
        a.window_id,
        a.category,
        w.population as weight,
        a.pt_minutes,
        a.car_minutes,
        a.pt_car_ratio
    from {{ ref('fct_cell_accessibility') }} as a
    inner join {{ ref('stg_cell_municipality') }} as w on w.cell_id = a.cell_id
),

{{ summarise_accessibility('cell_values', ['ags', 'window_id', 'category']) }}
