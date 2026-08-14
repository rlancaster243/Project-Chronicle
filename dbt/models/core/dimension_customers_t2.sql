{{ config(
    materialized='incremental',
    unique_key='customer_id',
    incremental_strategy='delete+insert'
) }}

-- Grain: one customer × one valid historical state interval.
-- Problem: mutations arrive duplicated, late, and out of order.
-- Decision: rebuild each affected customer's history from logical source time.
-- Mechanism: order by source_updated_at, change_id; DELETE closes the open
--            interval; no tombstone row; customer-scoped incremental rebuild.
-- Failure mode: ordering by ingested_at inverts customer 42 (premium before
--               the late CA/free move) and fails no_overlapping_validity_windows.
-- Verification: fixtures/expected/customer_42_intervals.csv and generic tests.

{% set scd2_sort = var('scd2_sort', 'source_time') %}
{% if scd2_sort == 'ingest_time' %}
    {% set order_by = 'ingested_at, change_id' %}
{% else %}
    {% set order_by = 'source_updated_at, change_id' %}
{% endif %}

with changes as (
    select * from {{ ref('itm_customer_changes_deduplicated') }}
),

{% if is_incremental() %}
watermark as (
    select coalesce(max(last_seen_ingested_at), timestamp '1970-01-01') as high_water
    from {{ this }}
),

affected as (
    select distinct customer_id
    from {{ ref('stg_customer_cdc_log') }}
    where ingested_at > (select high_water from watermark)
),
{% endif %}

scoped as (
    select *
    from changes
    {% if is_incremental() %}
    where customer_id in (select customer_id from affected)
    {% endif %}
),

sequenced as (
    select
        scoped.*,
        lead(source_updated_at) over (
            partition by customer_id
            order by {{ order_by }}
        ) as next_source_updated_at,
        lead(operation) over (
            partition by customer_id
            order by {{ order_by }}
        ) as next_operation
    from scoped
),

versions as (
    select
        customer_id || '-' || change_id as customer_version_id,
        customer_id,
        country_code,
        subscription_tier,
        account_status,
        email_verified,
        source_updated_at as valid_from,
        case
            when next_operation = 'DELETE' then next_source_updated_at
            else next_source_updated_at
        end as valid_to,
        change_id as source_change_id,
        operation
    from sequenced
    where operation <> 'DELETE'
),

emitted as (
    select *
    from versions
    {% if scd2_sort == 'ingest_time' %}
    -- Defect path: emit inverted windows so temporal tests can catch them.
    {% else %}
    where valid_to is null
       or valid_from < valid_to
    {% endif %}
),

watermarks as (
    select
        customer_id,
        max(ingested_at) as last_seen_ingested_at
    from {{ ref('stg_customer_cdc_log') }}
    {% if is_incremental() %}
    where customer_id in (select customer_id from affected)
    {% endif %}
    group by 1
)

select
    emitted.customer_version_id,
    emitted.customer_id,
    emitted.country_code,
    emitted.subscription_tier,
    emitted.account_status,
    emitted.email_verified,
    emitted.valid_from,
    emitted.valid_to,
    (emitted.valid_to is null) as row_current,
    emitted.source_change_id,
    watermarks.last_seen_ingested_at
from emitted
inner join watermarks
    on emitted.customer_id = watermarks.customer_id
