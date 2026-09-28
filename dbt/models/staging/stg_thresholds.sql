select threshold_min
from {{ source('pipeline', 'thresholds') }}
