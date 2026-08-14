{{ config(materialized='view') }}

-- Grain: one received mutation record (duplicates retained).
-- Problem: landing rows mix event time and arrival time.
-- Decision: type the CDC log and filter only by ingest_cutoff, never by
--           source_updated_at.
-- Mechanism: seed → typed view; cutoff simulates incremental arrival.
-- Failure mode: filtering on source time would hide late mutations.
-- Verification: customer 42 still contains the Jul 11 late move when cutoff
--               is null, and loses it when cutoff is 2026-07-10 23:59:59.

with source as (
    select * from {{ ref('customer_cdc_log') }}
),

typed as (
    select
        change_id,
        customer_id,
        upper(operation) as operation,
        country_code,
        subscription_tier,
        account_status,
        email_verified,
        source_updated_at::timestamp as source_updated_at,
        ingested_at::timestamp as ingested_at,
        scenario_tag,
        md5(
            concat_ws(
                '|',
                change_id,
                customer_id::varchar,
                ingested_at::varchar,
                source_updated_at::varchar
            )
        ) as received_id
    from source
)

select *
from typed
{% if var('ingest_cutoff', none) %}
where ingested_at <= '{{ var("ingest_cutoff") }}'::timestamp
{% endif %}
