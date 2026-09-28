-- Population assigned to municipalities can never exceed the population of the cell.
select
    c.cell_id,
    c.population,
    sum(w.population) as assigned_population
from {{ ref('stg_cells') }} as c
inner join {{ ref('stg_cell_municipality') }} as w on w.cell_id = c.cell_id
group by c.cell_id, c.population
having sum(w.population) > c.population
