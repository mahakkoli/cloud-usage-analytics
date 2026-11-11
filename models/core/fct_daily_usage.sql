select
    u.namespace_id,
    n.account_id,
    u.usage_date,
    u.actions,
    u.storage_gb
from {{ ref('stg_daily_usage') }} as u
left join {{ ref('stg_namespaces') }} as n
    on u.namespace_id = n.namespace_id