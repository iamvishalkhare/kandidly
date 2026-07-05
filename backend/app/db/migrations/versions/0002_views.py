"""analytics views (SPEC §15.4) + model_prices config table

Revision ID: 0002_views
Revises: 0001_initial
Create Date: 2026-07-05

SPEC §15.4 requires these views be created as migrations. They read the
append-only event/entity tables so a warehouse can be added later (SPEC N9).

NOTE (spec-gap): SPEC §15 references a `model_prices` config table for the cost
ledger but it is absent from the §7 DDL. It is created here as an analytics/config
addition (admin-editable seed).
"""

from __future__ import annotations

from alembic import op

revision = "0002_views"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


MODEL_PRICES = """
CREATE TABLE model_prices (
    model            text PRIMARY KEY,
    input_per_mtok   numeric(10,4) NOT NULL DEFAULT 0,
    output_per_mtok  numeric(10,4) NOT NULL DEFAULT 0,
    unit_note        text,
    updated_at       timestamptz NOT NULL DEFAULT now()
);
"""

V_FUNNEL = """
CREATE VIEW v_funnel AS
WITH durations AS (
    SELECT a.requisition_id,
           e.to_state AS state,
           EXTRACT(EPOCH FROM (
               LEAD(e.created_at) OVER (PARTITION BY e.application_id ORDER BY e.created_at)
               - e.created_at)) AS secs
    FROM application_events e
    JOIN applications a ON a.id = e.application_id
)
SELECT requisition_id,
       state,
       COUNT(*) AS count,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY secs) AS median_seconds_in_state
FROM durations
GROUP BY requisition_id, state;
"""

V_INTERVIEW_QUALITY = """
CREATE VIEW v_interview_quality AS
SELECT i.id AS interview_id,
       COALESCE(
         SUM(CASE WHEN t.speaker='kandidly' AND t.decision='PROBE' THEN 1 ELSE 0 END)::numeric
         / NULLIF(SUM(CASE WHEN t.speaker='kandidly' THEN 1 ELSE 0 END), 0), 0) AS followup_ratio,
       COALESCE(AVG(CASE WHEN t.speaker='candidate'
                         THEN array_length(regexp_split_to_array(trim(t.text), '\\s+'), 1) END), 0)
           AS avg_candidate_turn_words,
       (SELECT COUNT(*) FROM question_plan_nodes n
        JOIN question_plans p ON p.id = n.plan_id
        WHERE p.interview_id = i.id AND n.state='skipped') AS nodes_skipped,
       i.elapsed_active_seconds AS duration
FROM interviews i
LEFT JOIN turns t ON t.interview_id = i.id
    AND (t.node_id IS NULL OR t.node_id NOT IN (
        SELECT id FROM question_plan_nodes WHERE node_type='injected'))
GROUP BY i.id, i.elapsed_active_seconds;
"""

V_SCORE_DISTRIBUTION = """
CREATE VIEW v_score_distribution AS
SELECT i.requisition_id,
       ev.criterion_key,
       ROUND(ev.final_score)::int AS score,
       COUNT(*) AS count
FROM evaluations ev
JOIN interviews i ON i.id = ev.interview_id
GROUP BY i.requisition_id, ev.criterion_key, ROUND(ev.final_score)::int;
"""

V_PROCTORING_RATES = """
CREATE VIEW v_proctoring_rates AS
SELECT i.requisition_id,
       pe.type,
       COUNT(*)::numeric / NULLIF(COUNT(DISTINCT pe.interview_id), 0) AS per_interview_rate
FROM proctoring_events pe
JOIN interviews i ON i.id = pe.interview_id
GROUP BY i.requisition_id, pe.type;
"""

V_COST_PER_INTERVIEW = """
CREATE VIEW v_cost_per_interview AS
SELECT i.id AS interview_id,
       COALESCE(SUM((t.meta->'usage'->>'cost_usd')::numeric), 0) AS turns_cost_usd,
       COALESCE((SELECT SUM((sj_meta_cost)) FROM (
           SELECT 0::numeric AS sj_meta_cost) s), 0) AS jobs_cost_usd
FROM interviews i
LEFT JOIN turns t ON t.interview_id = i.id
GROUP BY i.id;
"""

_VIEWS = [
    "v_cost_per_interview",
    "v_proctoring_rates",
    "v_score_distribution",
    "v_interview_quality",
    "v_funnel",
]


def upgrade() -> None:
    op.execute(MODEL_PRICES)
    op.execute(V_FUNNEL)
    op.execute(V_INTERVIEW_QUALITY)
    op.execute(V_SCORE_DISTRIBUTION)
    op.execute(V_PROCTORING_RATES)
    op.execute(V_COST_PER_INTERVIEW)


def downgrade() -> None:
    for v in _VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {v}")
    op.execute("DROP TABLE IF EXISTS model_prices")
