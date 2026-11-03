select
    account_id,
    change_date,
    count(*) as n
from {{ ref('stg_plan_changes') }}
group by account_id, change_date
having count(*) > 1