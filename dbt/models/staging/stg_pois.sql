select
    poi_id,
    category,
    is_strict,
    name,
    lon,
    lat,
    source
from {{ source('pipeline', 'pois') }}
