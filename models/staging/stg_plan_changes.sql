select
    account_id,
    cast(change_date as date) as change_date,
    lower(old_plan) as old_plan,
    lower(new_plan) as new_plan

from {{ source('raw', 'plan_changes') }}