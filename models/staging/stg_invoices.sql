select distinct
invoice_id,
account_id,
cast(invoice_month as date) as invoice_date,
plan,
amount_usd
from {{source ('raw','invoices')}}