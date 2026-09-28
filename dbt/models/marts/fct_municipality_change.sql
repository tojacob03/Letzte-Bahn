-- Change of every municipality metric against the previous published snapshot.
-- Empty until at least two timetable snapshots have been published.
select
    cur.ags,
    cur.window_id,
    cur.dimension,
    cur.metric,
    prev.snapshot_id as previous_snapshot_id,
    prev.value as previous_value,
    cur.value as current_value,
    cur.value - prev.value as change
from {{ ref('mart_municipality_metrics_long') }} as cur
inner join {{ ref('stg_previous_municipality_metrics') }} as prev
    on prev.ags = cur.ags
    and prev.window_id = cur.window_id
    and prev.dimension = cur.dimension
    and prev.metric = cur.metric
