with usage_monthly as (

    -- aggregate daily usage to account x month BEFORE joining, to avoid fan-out
    select
        account_id,
        date_trunc('month', usage_date) as month,
        sum(actions) as actions,                                            -- flow: sum
        count(distinct case when actions > 0 then namespace_id end) as active_namespaces,
        avg(storage_gb) as avg_storage_gb                                   -- level: average
    from {{ ref('fct_daily_usage') }}
    group by 1, 2

)

select
    i.account_id,
    i.invoice_month as month,
    a.region,
    date_trunc('month', a.signup_date) as signup_month,
    i.plan,
    i.amount_usd as revenue_usd,
    u.actions,
    u.active_namespaces,
    u.avg_storage_gb
from {{ ref('stg_invoices') }} as i
left join usage_monthly as u
    on i.account_id = u.account_id
    and i.invoice_month = u.month
left join {{ ref('dim_accounts') }} as a
    on i.account_id = a.account_id