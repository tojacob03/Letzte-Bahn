select
    poi_id,
    window_id,
    departures
from {{ source('pipeline', 'station_service') }}
