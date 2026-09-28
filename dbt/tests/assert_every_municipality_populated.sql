-- Every municipality of the region must have residents on the census grid.
select ags, name
from {{ ref('dim_municipalities') }}
where population <= 0
