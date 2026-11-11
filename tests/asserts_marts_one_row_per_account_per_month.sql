select
    account_id,
    month,
    count(*) as n
from {{ ref('mart_account_monthly') }}
group by account_id, month
having count(*) > 1