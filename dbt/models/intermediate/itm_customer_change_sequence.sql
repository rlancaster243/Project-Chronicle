{{ config(materialized='view') }}

-- Grain: one canonical change_id with logical sequence metadata.
-- Problem: physical arrival order is not historical truth.
-- Decision: order by source_updated_at, then change_id. Never ingested_at.
-- Mechanism: window LEAD for the next logical timestamp; flag same-timestamp
--            attribute conflicts instead of inventing certainty.
-- Failure mode: ordering by ingested_at rebuilds customer 42 as CA/free after
--               premium and can invert validity windows.
-- Verification: customer 42 sequence is insert → move → upgrade → delete.

with changes as (
    select * from {{ ref('itm_customer_changes_deduplicated') }}
),

sequenced as (
    select
        changes.*,
        row_number() over (
            partition by customer_id
            order by source_updated_at, change_id
        ) as change_seq,
        lead(source_updated_at) over (
            partition by customer_id
            order by source_updated_at, change_id
        ) as next_source_updated_at,
        lead(change_id) over (
            partition by customer_id
            order by source_updated_at, change_id
        ) as next_change_id,
        lead(operation) over (
            partition by customer_id
            order by source_updated_at, change_id
        ) as next_operation,
        count(*) over (
            partition by customer_id, source_updated_at
        ) as same_timestamp_change_count,
        min(country_code) over (
            partition by customer_id, source_updated_at
        ) as peer_country_min,
        max(country_code) over (
            partition by customer_id, source_updated_at
        ) as peer_country_max,
        min(subscription_tier) over (
            partition by customer_id, source_updated_at
        ) as peer_tier_min,
        max(subscription_tier) over (
            partition by customer_id, source_updated_at
        ) as peer_tier_max,
        min(account_status) over (
            partition by customer_id, source_updated_at
        ) as peer_status_min,
        max(account_status) over (
            partition by customer_id, source_updated_at
        ) as peer_status_max,
        min(email_verified::integer) over (
            partition by customer_id, source_updated_at
        ) as peer_verified_min,
        max(email_verified::integer) over (
            partition by customer_id, source_updated_at
        ) as peer_verified_max
    from changes
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
    received_id,
    change_seq,
    next_source_updated_at,
    next_change_id,
    next_operation,
    same_timestamp_change_count,
    (
        same_timestamp_change_count > 1
        and (
            peer_country_min <> peer_country_max
            or peer_tier_min <> peer_tier_max
            or peer_status_min <> peer_status_max
            or peer_verified_min <> peer_verified_max
        )
    ) as is_ambiguous_tie
from sequenced
