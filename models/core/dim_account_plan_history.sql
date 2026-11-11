with plan_periods as (

    -- the plan each account started on
    select
        account_id,
        plan,
        signup_date as valid_from
    from {{ ref('stg_accounts') }}

    union all

    -- every later change starts a new period
    select
        account_id,
        new_plan as plan,
        change_date as valid_from
    from {{ ref('stg_plan_changes') }}

),

plan_dates as (
select
    account_id,
    plan,
    valid_from,
    lead(valid_from) OVER (
        PARTITION BY account_id
        ORDER BY valid_from
    ) AS valid_to
from plan_periods
)

select * ,
case 
    when valid_to is null then true 
    else false 
end as is_current
from plan_dates



