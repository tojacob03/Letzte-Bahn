-- Headline numbers for the analysis page, README and case study: one row per finding and
-- key. The wording lives in the presentation layer; the numbers only here.
{% set am = var('reference_window') %}
{% set pm = var('evening_window') %}

with municipal as (
    select * from {{ ref('fct_municipality_accessibility') }}
),

regional as (
    select * from {{ ref('fct_region_accessibility') }}
),

regional_reach as (
    select * from {{ ref('fct_region_reachability') }}
),

municipal_reach as (
    select r.*, m.name
    from {{ ref('fct_municipality_reachability') }} as r
    inner join {{ ref('dim_municipalities') }} as m on m.ags = r.ags
),

-- 1) Municipalities where fewer than half of the residents reach a family doctor within
--    60 minutes on a weekday evening, plus the population shares for every window.
gp_evening as (
    select
        'gp_evening_60' as finding_id,
        'municipalities_below_half' as metric_key,
        cast(count(*) filter (where share_within_60 < 0.5) as double) as value_num,
        cast(null as varchar) as value_text
    from municipal
    where window_id = '{{ pm }}' and category = 'gp'

    union all

    select 'gp_evening_60', 'municipalities_total', cast(count(*) as double), null
    from municipal
    where window_id = '{{ pm }}' and category = 'gp'

    union all

    select 'gp_evening_60', 'population_share_without_' || window_id, 1 - share_within_60, null
    from regional
    where category = 'gp'
),

-- 2) People reachable within 45 minutes by the median resident, per window and by car.
reach as (
    select 'reach_45', 'median_' || window_id, median_reachable_population_pt, null
    from regional_reach
    where threshold_min = 45

    union all

    select 'reach_45', 'car_median', median_reachable_population_car, null
    from regional_reach
    where threshold_min = 45 and window_id = '{{ am }}'
),

-- 3) Public transport versus car to the nearest supermarket.
car_ratio as (
    select 'pt_car_ratio_supermarket', 'median_ratio_' || window_id, median_pt_car_ratio, null
    from regional
    where category = 'supermarket'

    union all

    select 'pt_car_ratio_supermarket', 'share_over_3_' || window_id, share_ratio_over_3, null
    from regional
    where category = 'supermarket'
),

-- 4) Residents without a hospital within 60 minutes.
hospital as (
    select 'hospital_60', 'population_share_without_' || window_id, 1 - share_within_60, null
    from regional
    where category = 'hospital'
),

-- 5) Residents within 30 minutes of a rail station with departures in the window.
station as (
    select 'rail_station_30', 'population_share_within_' || window_id, share_within_30, null
    from regional
    where category = 'rail_station'
),

-- 6) Gap between the best- and worst-connected municipality.
gap_ranked as (
    select
        name,
        mean_reachable_population_pt,
        row_number() over (order by mean_reachable_population_pt desc, ags) as best_rank,
        row_number() over (order by mean_reachable_population_pt asc, ags) as worst_rank
    from municipal_reach
    where window_id = '{{ am }}' and threshold_min = 45
),

gap as (
    select 'municipal_gap_45', 'best', cast(mean_reachable_population_pt as double), name
    from gap_ranked
    where best_rank = 1

    union all

    select 'municipal_gap_45', 'worst', cast(mean_reachable_population_pt as double), name
    from gap_ranked
    where worst_rank = 1
)

select * from gp_evening
union all
select * from reach
union all
select * from car_ratio
union all
select * from hospital
union all
select * from station
union all
select * from gap
