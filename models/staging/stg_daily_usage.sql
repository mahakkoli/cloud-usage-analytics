select distinct 
namespace_id,
cast(usage_date as date) as usage_date,
actions,
storage_gb
from {{source ('raw', 'daily_usage')}}