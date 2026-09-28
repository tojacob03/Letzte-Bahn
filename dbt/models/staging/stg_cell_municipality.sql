select
    cell_id,
    ags,
    population
from {{ source('pipeline', 'cell_municipality') }}
