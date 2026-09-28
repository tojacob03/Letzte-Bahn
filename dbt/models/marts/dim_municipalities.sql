with population as (
    select
        ags,
        sum(population) as population,
        count(distinct cell_id) as n_cells
    from {{ ref('stg_cell_municipality') }}
    group by ags
)

select
    m.ags,
    m.name,
    m.municipality_type,
    m.kreis_ags,
    m.kreis_name,
    round(m.area_km2, 2) as area_km2,
    coalesce(p.population, 0) as population,
    coalesce(p.n_cells, 0) as n_cells
from {{ ref('stg_municipalities') }} as m
left join population as p on p.ags = m.ags
