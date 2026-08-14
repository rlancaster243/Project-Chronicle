{% test exactly_one_current_record(model, entity_key, current_flag, valid_to) %}

-- Active entities (an open interval exists) must have exactly one current row.
-- Deleted entities (no open interval) must have zero current rows.

with tallied as (
    select
        {{ entity_key }} as entity_id,
        sum(case when {{ current_flag }} then 1 else 0 end) as current_rows,
        sum(case when {{ valid_to }} is null then 1 else 0 end) as open_rows
    from {{ model }}
    group by 1
)

select
    entity_id,
    current_rows,
    open_rows
from tallied
where current_rows > 1
   or (open_rows > 0 and current_rows <> 1)
   or (open_rows = 0 and current_rows <> 0)

{% endtest %}
