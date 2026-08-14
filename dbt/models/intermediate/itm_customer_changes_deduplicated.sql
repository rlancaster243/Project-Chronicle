{{ config(materialized='view') }}

-- Grain: one canonical change_id.
-- Problem: the same mutation can be delivered twice or replayed.
-- Decision: change_id is mutation identity; first-write wins.
-- Mechanism: row_number by ingested_at, keep rn = 1.
-- Failure mode: treating identical business values as duplicates would
--               collapse two legitimate change_ids (customer 22).
-- Verification: chg_042_move and chg_010_update appear once; chg_022_insert
--               and chg_022_noop both survive.

with ordered as (
    select
        *,
        row_number() over (
            partition by change_id
            order by ingested_at, received_id
        ) as delivery_rank
    from {{ ref('stg_customer_cdc_log') }}
)

select
    change_id,
    customer_id,
    operation,
    country_code,
    subscription_tier,
    account_status,
    email_verified,
    source_updated_at,
    ingested_at,
    scenario_tag,
    received_id
from ordered
where delivery_rank = 1
