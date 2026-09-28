-- Tidy table of all municipality metrics: published with every snapshot and used to
-- compare snapshots. Car metrics do not depend on the time window (window_id = 'car').
{% set reference = var('reference_window') %}

with accessibility as (
    select * from {{ ref('fct_municipality_accessibility') }}
),

reachability as (
    select * from {{ ref('fct_municipality_reachability') }}
)

select ags, window_id, category as dimension, 'median_pt_minutes' as metric,
       median_pt_minutes as value
from accessibility
union all
select ags, window_id, category, 'share_within_30', share_within_30
from accessibility
union all
select ags, window_id, category, 'share_within_60', share_within_60
from accessibility
union all
select ags, window_id, category, 'median_pt_car_ratio', median_pt_car_ratio
from accessibility
union all
select ags, 'car', category, 'median_car_minutes', median_car_minutes
from accessibility
where window_id = '{{ reference }}'
union all
select ags, window_id, cast(threshold_min as varchar), 'mean_reachable_population_pt',
       mean_reachable_population_pt
from reachability
union all
select ags, 'car', cast(threshold_min as varchar), 'mean_reachable_population_car',
       mean_reachable_population_car
from reachability
where window_id = '{{ reference }}'
