select
    snapshot_id,
    ags,
    window_id,
    dimension,
    metric,
    value
from {{ source('pipeline', 'previous_municipality_metrics') }}
