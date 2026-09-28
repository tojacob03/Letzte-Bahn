-- Population-weighted accessibility for the whole region, per time window and category.
with cell_values as (
    select
        a.window_id,
        a.category,
        c.region_population as weight,
        a.pt_minutes,
        a.car_minutes,
        a.pt_car_ratio
    from {{ ref('fct_cell_accessibility') }} as a
    inner join {{ ref('dim_cells') }} as c on c.cell_id = a.cell_id
    where c.region_population > 0
),

{{ summarise_accessibility('cell_values', ['window_id', 'category']) }}
