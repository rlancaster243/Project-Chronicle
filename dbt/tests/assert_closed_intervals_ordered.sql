-- Every closed SCD2 row must satisfy valid_from < valid_to.

select
    customer_id,
    source_change_id,
    valid_from,
    valid_to
from {{ ref('dimension_customers_t2') }}
where valid_to is not null
  and valid_from >= valid_to
