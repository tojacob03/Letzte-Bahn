-- Grid cells with their main municipality (largest population share) and the population
-- living inside the region (cells on the border can lie partly outside).
with weights as (
    select
        cell_id,
        ags,
        population,
        row_number() over (partition by cell_id order by population desc, ags) as share_rank,
        sum(population) over (partition by cell_id) as region_population
    from {{ ref('stg_cell_municipality') }}
)

select
    c.cell_id,
    c.cell_idx,
    c.x_ll,
    c.y_ll,
    c.lon,
    c.lat,
    c.population,
    c.is_origin,
    w.ags as main_ags,
    coalesce(w.region_population, 0) as region_population
from {{ ref('stg_cells') }} as c
left join weights as w
    on w.cell_id = c.cell_id and w.share_rank = 1
