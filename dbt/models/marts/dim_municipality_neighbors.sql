-- Municipalities that share a border, for the neighbour comparison on the map.
select
    a.ags,
    b.ags as neighbor_ags
from {{ ref('stg_municipalities') }} as a
inner join {{ ref('stg_municipalities') }} as b
    on a.ags <> b.ags and ST_Intersects(a.geom, b.geom)
