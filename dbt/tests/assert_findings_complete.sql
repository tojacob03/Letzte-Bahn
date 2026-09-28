-- Every headline finding must be computable: the website and the README rely on them.
with expected as (
    select unnest([
        'gp_evening_60',
        'reach_45',
        'pt_car_ratio_supermarket',
        'hospital_60',
        'rail_station_30',
        'municipal_gap_45'
    ]) as finding_id
)

select finding_id
from expected
where finding_id not in (select finding_id from {{ ref('fct_findings') }})
