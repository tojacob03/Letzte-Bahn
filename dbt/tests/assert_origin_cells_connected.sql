{{ config(severity='warn') }}
-- Origins from which no destination at all is reachable usually point to a network
-- problem (e.g. an origin that could not be linked to a street). Warn above 1 %.
with per_cell as (
    select
        cell_id,
        count(minutes) as reachable_categories
    from {{ ref('int_nearest_destination_pt') }}
    where window_id = '{{ var("reference_window") }}'
    group by cell_id
)

select
    count(*) filter (where reachable_categories = 0) as isolated_cells,
    count(*) as cells
from per_cell
having count(*) filter (where reachable_categories = 0) > 0.01 * count(*)
