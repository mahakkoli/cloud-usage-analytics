select
    namespace_id,
    usage_date,
    count(*) as n
from {{ ref('stg_daily_usage') }}
group by namespace_id, usage_date
having count(*) > 1