select
    account_id,
    trim(account_name)          as account_name,
    cast(signup_date as date)   as signup_date,
    region,
    lower(plan)                 as plan
from {{ ref('raw_accounts') }}