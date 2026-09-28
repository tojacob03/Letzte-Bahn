select
    origin_idx,
    dest_idx,
    minutes
from {{ source('pipeline', 'travel_times_car') }}
