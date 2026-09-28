select
    dest_idx,
    dest_kind,
    dest_key
from {{ source('pipeline', 'destinations') }}
