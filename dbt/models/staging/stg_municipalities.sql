select
    ags,
    name,
    bez as municipality_type,
    kreis_ags,
    kreis_name,
    area_km2,
    ST_GeomFromWKB(geometry_wkb) as geom
from {{ source('pipeline', 'municipalities') }}
