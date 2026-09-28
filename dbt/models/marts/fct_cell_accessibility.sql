select
    pt.cell_id,
    pt.window_id,
    pt.category,
    pt.minutes as pt_minutes,
    car.minutes as car_minutes,
    case
        when pt.minutes is not null and car.minutes is not null
            then round(pt.minutes / greatest(car.minutes, 1), 3)
    end as pt_car_ratio
from {{ ref('int_nearest_destination_pt') }} as pt
left join {{ ref('int_nearest_destination_car') }} as car
    on car.cell_id = pt.cell_id and car.category = pt.category
