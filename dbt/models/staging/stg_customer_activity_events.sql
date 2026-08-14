{{ config(materialized='view') }}

-- Grain: one customer activity event.
-- Problem: facts must later join to the state valid at event_timestamp.
-- Decision: type only; do not attach current customer attributes here.
-- Mechanism: seed → typed view.
-- Failure mode: joining latest state in this model would hide PIT bugs.
-- Verification: event counts match the seeded activity file.

select
    event_id,
    customer_id,
    event_name,
    event_timestamp::timestamp as event_timestamp
from {{ ref('customer_activity_events') }}
