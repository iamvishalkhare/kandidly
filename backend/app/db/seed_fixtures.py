"""Bulky fixture data for the dev seed (app.db.seed).

Catalog values mirror the console builder's autocomplete lists
(web/src/pages/console/RequisitionBuilder.tsx); candidate names mirror the
console mock roster (web/src/pages/console/interviewData.ts) so the future
console APIs serve familiar data.
"""

from __future__ import annotations

CATALOG: dict[str, list[str]] = {
    "domain": [
        "Engineering",
        "Machine Learning",
        "Data Science",
        "Infrastructure",
        "Product",
        "Marketing",
    ],
    "skill": [
        "Python",
        "Go",
        "TypeScript",
        "React",
        "PostgreSQL",
        "Kafka",
        "Kubernetes",
        "Docker",
        "AWS",
        "Terraform",
        "PyTorch",
        "RAG",
        "Vector DBs",
        "LLM Ops",
        "Figma",
        "SQL",
        "Spark",
        "Airflow",
        "SEO",
        "Content Strategy",
    ],
    "job_title": [
        "Backend Engineer",
        "Senior Backend Engineer",
        "ML Engineer",
        "Data Scientist",
        "Platform Engineer",
        "Site Reliability Engineer",
        "Product Manager",
        "Product Designer",
        "Growth Marketer",
        "Frontend Engineer",
    ],
}

# Extra candidates beyond the two legacy dev candidates; display names match
# the console mock roster.
CANDIDATES: list[tuple[str, str]] = [
    ("ananya.rao@example.dev", "Ananya Rao"),
    ("marcus.lee@example.dev", "Marcus Lee"),
    ("priya.menon@example.dev", "Priya Menon"),
    ("diego.alvarez@example.dev", "Diego Alvarez"),
    ("sara.kim@example.dev", "Sara Kim"),
    ("rahul.nair@example.dev", "Rahul Nair"),
]


def generic_template_schema(role_title: str) -> dict:
    """A small candidate-renderer-compatible KYI schema for non-flagship
    requisitions (only x-field kinds the web form renderer supports)."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "x-kandidly": {
            "profile": "kyi-form/v1",
            "field_order": [
                "full_name",
                "current_role",
                "years_experience",
                "motivation",
                "resume",
            ],
        },
        "required": ["full_name", "resume"],
        "properties": {
            "full_name": {
                "type": "string",
                "title": "Full name",
                "maxLength": 120,
                "x-field": "short_text",
            },
            "current_role": {
                "type": "string",
                "title": "Current role / title",
                "maxLength": 120,
                "x-field": "short_text",
            },
            "years_experience": {
                "type": "integer",
                "title": f"Years of relevant experience for {role_title}",
                "minimum": 0,
                "maximum": 40,
                "x-field": "number",
            },
            "motivation": {
                "type": "string",
                "title": "Why this role?",
                "maxLength": 2000,
                "x-field": "long_text",
            },
            "resume": {
                "type": "string",
                "title": "Upload your resume",
                "x-field": "file",
                "x-accept": [".pdf", ".docx"],
                "x-max-bytes": 10485760,
            },
        },
    }


def generic_rubric_criteria(keys: list[tuple[str, str, int]]) -> list[tuple]:
    """(key, name, weight) → seed.RUBRIC_CRITERIA-shaped tuples with generic
    anchors. Weights must total 100."""
    out = []
    for order, (key, name, weight) in enumerate(keys, start=1):
        out.append(
            (
                key,
                name,
                f"Assessment of {name.lower()}.",
                weight,
                order,
                [
                    {"level": 1, "anchor": "Well below the bar."},
                    {"level": 2, "anchor": "Below the bar."},
                    {"level": 3, "anchor": "Meets the bar."},
                    {"level": 4, "anchor": "Above the bar."},
                    {"level": 5, "anchor": "Exceptional."},
                ],
            )
        )
    return out


# Non-flagship requisitions (the flagship swe_backend one is defined in
# seed.py and carries the interview pipelines).
EXTRA_REQUISITIONS: list[dict] = [
    {
        "code": "ML-014",
        "title": "ML Engineer",
        "domain": "Machine Learning",
        "skills": ["Python", "PyTorch", "RAG", "Vector DBs"],
        "objective": (
            "Own retrieval quality for the RAG stack end-to-end: embedding "
            "models, chunking strategy, and eval harnesses."
        ),
        "sample_questions": [
            "Walk me through a retrieval-quality regression you debugged.",
            "How would you evaluate chunking strategies offline?",
        ],
        "tone": "technical",
        "status": "open",
        "interview_type": "ml_engineer",
        "rubric": [
            ("ml_fundamentals", "ML fundamentals", 40),
            ("retrieval_systems", "Retrieval systems", 35),
            ("communication", "Communication", 25),
        ],
        "clicks": 342,
        "uses": 51,
    },
    {
        "code": "DAT-003",
        "title": "Data Scientist",
        "domain": "Data Science",
        "skills": ["Python", "SQL", "Spark"],
        "objective": "Drive experiment design and causal analysis for growth initiatives.",
        "sample_questions": [
            "Describe an A/B test you designed that produced a surprising result.",
        ],
        "tone": "structured",
        "status": "open",
        "interview_type": "data_scientist",
        "rubric": [
            ("statistics", "Statistics & experimentation", 45),
            ("data_wrangling", "Data wrangling", 30),
            ("communication", "Communication", 25),
        ],
        "clicks": 210,
        "uses": 33,
    },
    {
        "code": "INF-008",
        "title": "Platform Engineer",
        "domain": "Infrastructure",
        "skills": ["Kubernetes", "Terraform", "Go", "AWS"],
        "objective": "Build and operate the multi-region compute platform.",
        "sample_questions": [
            "Tell me about an incident you ran point on.",
            "How do you approach zero-downtime migrations?",
        ],
        "tone": "bar_raiser",
        "status": "paused",
        "interview_type": "platform_engineer",
        "rubric": [
            ("reliability", "Reliability engineering", 40),
            ("infra_depth", "Infrastructure depth", 35),
            ("ownership", "Ownership", 25),
        ],
        "clicks": 96,
        "uses": 12,
    },
    {
        "code": "PRO-002",
        "title": "Product Manager",
        "domain": "Product",
        "skills": ["Figma", "SQL"],
        "objective": "Own the candidate-experience surface from discovery to launch.",
        "sample_questions": [
            "Walk me through a product bet that failed and what you learned.",
        ],
        "tone": "conversational",
        "status": "open",
        "interview_type": "product_manager",
        "rubric": [
            ("product_sense", "Product sense", 40),
            ("execution", "Execution", 35),
            ("communication", "Communication", 25),
        ],
        "clicks": 188,
        "uses": 27,
    },
    {
        "code": "MKT-005",
        "title": "Growth Marketer",
        "domain": "Marketing",
        "skills": ["SEO", "Content Strategy"],
        "objective": "Scale organic acquisition with a content-led motion.",
        "sample_questions": [
            "Which growth loop are you proudest of building?",
        ],
        "tone": "friendly",
        "status": "closed",
        "interview_type": "growth_marketer",
        "rubric": [
            ("growth_strategy", "Growth strategy", 50),
            ("analytics", "Analytics", 25),
            ("communication", "Communication", 25),
        ],
        "clicks": 421,
        "uses": 64,
    },
]


def transcript_script(name: str, system_story: str) -> list[tuple[str, str, str | None]]:
    """(speaker, text, decision) turns for one seeded flagship interview."""
    first = name.split()[0]
    return [
        (
            "kandidly",
            f"Hi {first}, welcome to your Kandidly interview for the Backend "
            "Engineer role. We'll spend about twenty-five minutes on your "
            "experience. Ready to start?",
            "GREET",
        ),
        ("candidate", "Yes, sounds good. Thanks for having me.", None),
        (
            "kandidly",
            "Great. To start: tell me about the most complex system you have "
            "built or operated, and your specific role in it.",
            "ASK",
        ),
        ("candidate", system_story, None),
        (
            "kandidly",
            "How did that system behave under partial failure — say a broker "
            "or a downstream dependency going away?",
            "PROBE",
        ),
        (
            "candidate",
            "We designed for at-least-once delivery, so consumers were "
            "idempotent by keying on event ids. When a broker died the "
            "producers buffered locally and we alerted on consumer lag. The "
            "worst incident was a poison message loop, which we fixed with a "
            "dead-letter queue and replay tooling.",
            None,
        ),
        (
            "kandidly",
            "What consistency guarantees did the read path give, and how did "
            "you communicate those tradeoffs to product stakeholders?",
            "PROBE",
        ),
        (
            "candidate",
            "Reads were eventually consistent, usually within two hundred "
            "milliseconds. For the checkout flow we added a read-your-writes "
            "session guarantee by pinning to the primary. I wrote a one-page "
            "tradeoff doc so product could choose per surface.",
            None,
        ),
        (
            "kandidly",
            "Let's switch to debugging. Walk me through a production issue "
            "you personally root-caused end to end.",
            "ADVANCE",
        ),
        (
            "candidate",
            "We saw p99 latency spikes every four hours. I correlated them "
            "with a cron that vacuumed a hot table, confirmed with pg_stat "
            "activity, and reproduced it in staging. The fix was moving to "
            "partitioned tables with per-partition vacuum, which flattened "
            "the spikes completely.",
            None,
        ),
        (
            "kandidly",
            "Nice. How do you decide when a service boundary deserves to "
            "exist versus staying inside a modular monolith?",
            "ASK",
        ),
        (
            "candidate",
            "I default to the monolith until an axis of independent scaling "
            "or ownership appears. Boundaries are expensive: you pay in "
            "latency, versioning, and on-call surface. When the payments "
            "team needed independent deploys and a stricter SLO, that was "
            "the signal to split.",
            None,
        ),
        (
            "kandidly",
            "Before we wrap: do you have questions for us about the role or the team?",
            "WRAP",
        ),
        (
            "candidate",
            "Yes — what does the on-call rotation look like, and how much of "
            "the roadmap is platform work versus product features?",
            None,
        ),
        (
            "kandidly",
            "Good questions; the recruiter will follow up with specifics. "
            "Thanks for your time — the team will review and get back to you "
            "shortly.",
            "CLOSE",
        ),
        ("candidate", "Thank you, I enjoyed the conversation.", None),
    ]


# Per-candidate flagship interview cases. `anchors` are the 3-run 1–5 scores
# per rubric criterion (median → evaluation); decision None ⇒ scored-not-yet-
# reviewed. Overall (weights 30/25/20/15/10) spans ~31–89 for percentile math.
INTERVIEW_CASES: list[dict] = [
    {
        "email": "ananya.rao@example.dev",
        "name": "Ananya Rao",
        "story": (
            "I led the design of our order-event pipeline: a Kafka-based "
            "event bus feeding a CQRS read model in Postgres, handling about "
            "forty thousand events a minute. I owned it end to end, from the "
            "schema registry to the consumer autoscaling policy."
        ),
        "anchors": {
            "system_design_depth": [5, 5, 4],
            "distributed_systems": [5, 4, 5],
            "ownership": [5, 5, 5],
            "problem_solving": [4, 4, 5],
            "communication": [4, 5, 4],
        },
        "decision": "shortlist",
        "notes": "Exceptional depth on failure modes; fast-track to onsite.",
        "days_ago": 2,
        "duration_s": 1642,
    },
    {
        "email": "marcus.lee@example.dev",
        "name": "Marcus Lee",
        "story": (
            "I built the ingestion service for our analytics product — a Go "
            "service in front of Kafka that validated and enriched about ten "
            "thousand events a second before they landed in the warehouse."
        ),
        "anchors": {
            "system_design_depth": [4, 4, 4],
            "distributed_systems": [4, 4, 3],
            "ownership": [4, 5, 4],
            "problem_solving": [4, 3, 4],
            "communication": [4, 4, 4],
        },
        "decision": "shortlist",
        "notes": "Solid systems instincts; strong ownership signal.",
        "days_ago": 4,
        "duration_s": 1518,
    },
    {
        "email": "priya.menon@example.dev",
        "name": "Priya Menon",
        "story": (
            "I maintained our billing reconciliation system and later "
            "rewrote its retry layer. I owned the consumer side of the "
            "pipeline and worked with another engineer on the producer."
        ),
        "anchors": {
            "system_design_depth": [3, 4, 3],
            "distributed_systems": [3, 3, 4],
            "ownership": [4, 3, 3],
            "problem_solving": [4, 4, 3],
            "communication": [4, 4, 5],
        },
        "decision": "hold",
        "notes": "Communicates crisply; design depth borderline for senior.",
        "days_ago": 6,
        "duration_s": 1447,
    },
    {
        "email": "diego.alvarez@example.dev",
        "name": "Diego Alvarez",
        "story": (
            "Most recently I worked on an internal CRUD platform — I added "
            "features to the API layer and helped migrate it from REST to "
            "gRPC alongside the platform team."
        ),
        "anchors": {
            "system_design_depth": [3, 3, 3],
            "distributed_systems": [3, 2, 3],
            "ownership": [3, 3, 4],
            "problem_solving": [3, 3, 3],
            "communication": [3, 4, 3],
        },
        "decision": None,
        "notes": None,
        "days_ago": 1,
        "duration_s": 1389,
    },
    {
        "email": "sara.kim@example.dev",
        "name": "Sara Kim",
        "story": (
            "I've mainly worked on frontend-for-backend services, and last "
            "year I took over a notification fanout worker that pushed to "
            "about a million devices a day."
        ),
        "anchors": {
            "system_design_depth": [2, 3, 2],
            "distributed_systems": [2, 2, 3],
            "ownership": [3, 3, 3],
            "problem_solving": [3, 2, 3],
            "communication": [4, 4, 4],
        },
        "decision": None,
        "notes": None,
        "days_ago": 9,
        "duration_s": 1256,
    },
    {
        "email": "rahul.nair@example.dev",
        "name": "Rahul Nair",
        "story": (
            "I contributed bug fixes to a payments service and shadowed the "
            "on-call rotation; I haven't owned a large system myself yet."
        ),
        "anchors": {
            "system_design_depth": [2, 2, 1],
            "distributed_systems": [2, 1, 2],
            "ownership": [2, 2, 2],
            "problem_solving": [2, 3, 2],
            "communication": [3, 3, 2],
        },
        "decision": "reject",
        "notes": "Too junior for the senior bar on this requisition.",
        "days_ago": 12,
        "duration_s": 1103,
    },
]

# Proctor snapshot cadence/signals for each seeded interview (offset seconds
# from interview start → signal).
SNAPSHOT_PLAN: list[tuple[int, str]] = [
    (10, "clear"),
    (130, "clear"),
    (250, "attention_shift"),
    (370, "clear"),
    (490, "low_light"),
    (610, "clear"),
]
