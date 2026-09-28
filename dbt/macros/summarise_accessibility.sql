{% macro summarise_accessibility(relation, group_by) %}
{#-
    Aggregates cell-level accessibility (columns weight, pt_minutes, car_minutes,
    pt_car_ratio) to the given grouping. Emits CTEs plus the final select, so it is
    used after a preceding CTE:  `with cell_values as (...), {{ '{{' }} summarise_accessibility(...) {{ '}}' }}`
-#}
{%- set keys = group_by | join(', ') -%}
shares as (
    select
        {{ keys }},
        sum(weight) as population,
        coalesce(sum(weight) filter (where pt_minutes <= 15), 0) / sum(weight) as share_within_15,
        coalesce(sum(weight) filter (where pt_minutes <= 30), 0) / sum(weight) as share_within_30,
        coalesce(sum(weight) filter (where pt_minutes <= 60), 0) / sum(weight) as share_within_60,
        coalesce(sum(weight) filter (where pt_minutes is null), 0) / sum(weight)
            as share_unreachable,
        coalesce(sum(weight) filter (where pt_minutes is null or pt_car_ratio > 3), 0)
            / sum(weight) as share_ratio_over_3
    from {{ relation }}
    group by {{ keys }}
),

median_pt as (
    {{ weighted_median_query(relation, 'pt_minutes', 'weight', group_by) }}
),

median_car as (
    {{ weighted_median_query(relation, 'car_minutes', 'weight', group_by) }}
),

median_ratio as (
    {{ weighted_median_query(relation, 'pt_car_ratio', 'weight', group_by) }}
)

select
    shares.*,
    nullif(median_pt.weighted_median, 'infinity'::double) as median_pt_minutes,
    nullif(median_car.weighted_median, 'infinity'::double) as median_car_minutes,
    nullif(median_ratio.weighted_median, 'infinity'::double) as median_pt_car_ratio
from shares
left join median_pt using ({{ keys }})
left join median_car using ({{ keys }})
left join median_ratio using ({{ keys }})
{% endmacro %}
