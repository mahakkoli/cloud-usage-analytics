select
    account_id,
    namespace_id,
    namespace_name,
    cast(created_date as date) as creeated_date
from {{ source('raw', 'namespaces') }}