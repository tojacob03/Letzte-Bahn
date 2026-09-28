-- The strict family-doctor definition is a subset of the default one, so the nearest
-- strictly tagged doctor can never be closer than the nearest doctor overall.
select
    strict_gp.cell_id,
    strict_gp.window_id,
    strict_gp.minutes as strict_minutes,
    any_gp.minutes as any_minutes
from {{ ref('int_nearest_destination_pt') }} as strict_gp
inner join {{ ref('int_nearest_destination_pt') }} as any_gp
    on any_gp.cell_id = strict_gp.cell_id
    and any_gp.window_id = strict_gp.window_id
    and any_gp.category = 'gp'
where strict_gp.category = 'gp_strict'
    and (
        strict_gp.minutes < any_gp.minutes
        or (strict_gp.minutes is not null and any_gp.minutes is null)
    )
