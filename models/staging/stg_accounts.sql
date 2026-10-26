select
    account_id,
    trim(account_name)          as account_name,
    cast(signup_date as date)   as signup_date,
    lower(region)               as region,
    lower(plan)                 as plan
from {{ source('raw', 'accounts') }}