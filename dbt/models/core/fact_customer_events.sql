{{ config(
    materialized='incremental',
    unique_key='event_id',
    incremental_strategy='delete+insert'
) }}

-- Grain: one customer activity event.
-- Problem: consumption needs event-time state, not a latest-state fact table.
-- Decision: keep facts attribute-free; enrichment happens in serving.
-- Mechanism: typed pass-through of staged events.
-- Failure mode: joining dimension_customers_t2 here on row_current would
--               silently use current state for historical events.
-- Verification: event_id unique; customer 42 has four seeded events.

select
    event_id,
    customer_id,
    event_name,
    event_timestamp
from {{ ref('stg_customer_activity_events') }}
{% if is_incremental() %}
where event_timestamp > (select coalesce(max(event_timestamp), timestamp '1970-01-01') from {{ this }})
{% endif %}
