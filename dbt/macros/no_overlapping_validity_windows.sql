{% test no_overlapping_validity_windows(model, entity_key, valid_from, valid_to) %}

-- Fails when two historical rows for one entity overlap in half-open space,
-- or when a closed row is inverted / zero-width (valid_from >= valid_to).
-- Inverted windows are treated as integrity failures because they are the
-- typical symptom of sequencing by ingested_at while labeling with source time.

with base as (
    select
        {{ entity_key }} as entity_id,
        {{ valid_from }} as valid_from,
        {{ valid_to }} as valid_to
    from {{ model }}
),

inverted as (
    select
        entity_id,
        valid_from,
        valid_to,
        'inverted_or_zero_width'::varchar as failure_kind
    from base
    where valid_to is not null
      and valid_from >= valid_to
),

overlapping_pairs as (
    select
        a.entity_id,
        a.valid_from,
        a.valid_to,
        'overlap'::varchar as failure_kind
    from base as a
    inner join base as b
        on a.entity_id = b.entity_id
       and (
            a.valid_from <> b.valid_from
            or a.valid_to is distinct from b.valid_to
       )
       and a.valid_from < coalesce(b.valid_to, timestamp '9999-12-31 00:00:00')
       and b.valid_from < coalesce(a.valid_to, timestamp '9999-12-31 00:00:00')
)

select * from inverted
union all
select * from overlapping_pairs

{% endtest %}
