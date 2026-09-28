{% macro weighted_median_query(relation, value, weight, group_by) %}
{#-
    Population-weighted (lower) median of `value` for every group. NULL values count as
    +infinity ("not reachable within the time limit"): if the median resident cannot
    reach a destination, the result is +infinity, which callers turn back into NULL.
-#}
{%- set keys = group_by | join(', ') -%}
select
    {{ keys }},
    min(sort_value) filter (where cumulative_weight >= total_weight / 2.0) as weighted_median
from (
    select
        {{ keys }},
        coalesce(cast({{ value }} as double), 'infinity'::double) as sort_value,
        sum({{ weight }}) over (
            partition by {{ keys }}
            order by coalesce(cast({{ value }} as double), 'infinity'::double)
            rows between unbounded preceding and current row
        ) as cumulative_weight,
        sum({{ weight }}) over (partition by {{ keys }}) as total_weight
    from {{ relation }}
) as ranked
group by {{ keys }}
{% endmacro %}
