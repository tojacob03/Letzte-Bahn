select
    window_id,
    label,
    day_type,
    service_date,
    start_time,
    minutes,
    sort_order
from {{ source('pipeline', 'windows') }}
