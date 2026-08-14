{{ config(materialized='view') }}

-- Grain: one activity event enriched with the customer state valid at
--         event_timestamp.
-- Problem: latest-state joins rewrite the past.
-- Decision: half-open point-in-time join on source-time intervals.
-- Mechanism:
--   event.customer_id = dimension.customer_id
--   and event.event_timestamp >= dimension.valid_from
--   and (event.event_timestamp < dimension.valid_to or dimension.valid_to is null)
-- Failure mode: joining on ingested_at or row_current = true.
-- Verification: fixtures/expected/customer_42_events_enriched.csv

select
    facts.event_id,
    facts.customer_id,
    facts.event_name,
    facts.event_timestamp,
    dim.customer_version_id,
    dim.country_code,
    dim.subscription_tier,
    dim.account_status,
    dim.email_verified,
    dim.valid_from as customer_valid_from,
    dim.valid_to as customer_valid_to,
    dim.row_current as customer_row_current,
    dim.source_change_id,
    (dim.customer_version_id is not null) as matched_historical_state
from {{ ref('fact_customer_events') }} as facts
left join {{ ref('dimension_customers_t2') }} as dim
    on facts.customer_id = dim.customer_id
   and facts.event_timestamp >= dim.valid_from
   and (
        facts.event_timestamp < dim.valid_to
        or dim.valid_to is null
   )
