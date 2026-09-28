select
    cell_id,
    cell_idx,
    x_ll,
    y_ll,
    lon,
    lat,
    population,
    is_origin
from {{ source('pipeline', 'cells') }}
