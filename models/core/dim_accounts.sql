select 
    a.account_id, 
    a.account_name,
    a.plan as signup_plan,
    a.region,
    a.signup_date,
    b.plan as current_plan
from {{ ref('stg_accounts') }} as a
left join {{ ref('dim_account_plan_history') }} as b
on a.account_id = b.account_id 
and b.is_current 