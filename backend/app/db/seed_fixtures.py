"""Bulky fixture data for the dev seed (app.db.seed).

Catalog values mirror the console builder's autocomplete lists
(web/src/pages/console/RequisitionBuilder.tsx); candidate names mirror the
console mock roster (web/src/pages/console/interviewData.ts) so the future
console APIs serve familiar data.

Every non-flagship requisition ships a rich, builder-shaped screening form
(``screening_fields``) and rubric (``rubric``) so that opening any of them in
the console Requisition Builder shows all sections fully populated. The field
lists intentionally span all eight builder field types across the set:
text, textarea, multiple_choice, multi_select, range, date, file, social.
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
    ("lena.fischer@example.dev", "Lena Fischer"),
]


def _field(ftype, label, *, placeholder="", required=False, options=None) -> dict:
    """Builder-shaped screening field ({type,label,placeholder,required,options})
    — the exact shape app.domain.builder.builder_fields_to_schema consumes."""
    return {
        "type": ftype,
        "label": label,
        "placeholder": placeholder,
        "required": required,
        "options": list(options or []),
    }


# Non-flagship requisitions (the flagship swe_backend one is defined in
# seed.py and carries the interview pipelines). Each `screening_fields` entry
# is builder-shaped; seed.py converts it via builder_fields_to_schema so the
# round trip through the console builder is lossless. `rubric` weights total
# 100 per requisition. `close_in_days` seeds the "Close Date" field (negative
# ⇒ already past, for a closed requisition).
EXTRA_REQUISITIONS: list[dict] = [
    {
        "code": "ML-014",
        "title": "ML Engineer",
        "domain": "Machine Learning",
        "skills": ["Python", "PyTorch", "RAG", "Vector DBs"],
        "objective": (
            "Own retrieval quality for the RAG stack end-to-end: embedding "
            "models, chunking strategy, and eval harnesses. We want someone "
            "who can move a real quality metric, not just ship a demo."
        ),
        "sample_questions": [
            "Walk me through a retrieval-quality regression you debugged.",
            "How would you evaluate chunking strategies offline before shipping?",
            "When would you fine-tune a model versus improve retrieval or prompting?",
        ],
        "tone": "technical",
        "status": "open",
        "interview_type": "ml_engineer",
        "close_in_days": 45,
        "screening_fields": [
            _field(
                "text", "Current role / title", placeholder="e.g. Senior ML Engineer", required=True
            ),
            _field(
                "textarea",
                "Describe an ML system you shipped to production",
                placeholder="Model, data, serving, and your specific role…",
                required=True,
            ),
            _field(
                "multi_select",
                "Which ML domains have you worked in?",
                options=[
                    "NLP / LLMs",
                    "Computer Vision",
                    "Recommendations",
                    "Search & Retrieval",
                    "Tabular / Classical ML",
                ],
            ),
            _field(
                "multiple_choice",
                "Largest model you have fine-tuned",
                options=["Under 1B params", "1–7B", "7–70B", "70B+"],
            ),
            _field("range", "Rate your production PyTorch proficiency"),
            _field(
                "social",
                "Link your GitHub or Hugging Face profile",
                placeholder="https://github.com/…",
            ),
            _field(
                "file", "Upload your resume", placeholder="PDF or DOCX, up to 10 MB", required=True
            ),
        ],
        "rubric": [
            {
                "name": "ML fundamentals",
                "description": "Depth on modeling choices, training dynamics, and evaluation.",
                "weight": 30,
            },
            {
                "name": "Retrieval & RAG systems",
                "description": "Embeddings, chunking, and offline eval of retrieval quality.",
                "weight": 25,
            },
            {
                "name": "Production ML Ops",
                "description": "Serving, monitoring, and safe rollout of models.",
                "weight": 20,
            },
            {
                "name": "Problem solving",
                "description": "Debugging regressions with structured, hypothesis-driven logic.",
                "weight": 15,
            },
            {
                "name": "Communication",
                "description": "Clarity when explaining tradeoffs to technical and product peers.",
                "weight": 10,
            },
        ],
        "clicks": 342,
        "uses": 51,
    },
    {
        "code": "DAT-003",
        "title": "Data Scientist",
        "domain": "Data Science",
        "skills": ["Python", "SQL", "Spark"],
        "objective": (
            "Drive experiment design and causal analysis for growth "
            "initiatives, turning fuzzy questions into decisions the team "
            "can act on."
        ),
        "sample_questions": [
            "Describe an A/B test you designed that produced a surprising result.",
            "How do you decide when an observed effect is causal versus correlational?",
            "Tell me about a time your analysis changed a leadership decision.",
        ],
        "tone": "structured",
        "status": "open",
        "interview_type": "data_scientist",
        "close_in_days": 30,
        "screening_fields": [
            _field(
                "text", "Current role / title", placeholder="e.g. Data Scientist II", required=True
            ),
            _field(
                "textarea",
                "Describe an experiment whose result changed a product decision",
                placeholder="Hypothesis, design, and the call it drove…",
                required=True,
            ),
            _field(
                "multiple_choice",
                "Primary statistical toolkit",
                options=["Python / statsmodels", "R", "SQL-first", "Bayesian stack"],
            ),
            _field("range", "Rate your SQL proficiency"),
            _field("date", "Earliest available start date"),
            _field(
                "file", "Upload your resume", placeholder="PDF or DOCX, up to 10 MB", required=True
            ),
        ],
        "rubric": [
            {
                "name": "Statistics & experimentation",
                "description": "Rigorous experiment design and correct inference.",
                "weight": 35,
            },
            {
                "name": "Causal inference",
                "description": "Isolating causal effects from observational and A/B data.",
                "weight": 20,
            },
            {
                "name": "Data wrangling & SQL",
                "description": "Efficiently shaping messy data into analysis-ready form.",
                "weight": 20,
            },
            {
                "name": "Business impact",
                "description": "Framing analysis around decisions that move the metric.",
                "weight": 15,
            },
            {
                "name": "Communication",
                "description": "Explaining findings and uncertainty to non-technical partners.",
                "weight": 10,
            },
        ],
        "clicks": 210,
        "uses": 33,
    },
    {
        "code": "INF-008",
        "title": "Platform Engineer",
        "domain": "Infrastructure",
        "skills": ["Kubernetes", "Terraform", "Go", "AWS"],
        "objective": (
            "Build and operate the multi-region compute platform: the "
            "paved road other teams deploy on, with reliability and cost as "
            "first-class concerns."
        ),
        "sample_questions": [
            "Tell me about an incident you ran point on.",
            "How do you approach zero-downtime migrations?",
            "What does a healthy on-call rotation look like to you?",
        ],
        "tone": "bar_raiser",
        "status": "paused",
        "interview_type": "platform_engineer",
        "close_in_days": 60,
        "screening_fields": [
            _field(
                "text",
                "Current role / title",
                placeholder="e.g. Staff Platform Engineer",
                required=True,
            ),
            _field(
                "textarea",
                "Walk through the largest production incident you led",
                placeholder="Impact, your role, and the follow-up…",
                required=True,
            ),
            _field(
                "multi_select",
                "Clouds you have operated at scale",
                options=["AWS", "GCP", "Azure", "On-prem / Bare-metal"],
            ),
            _field(
                "multiple_choice",
                "Infrastructure-as-code tool of choice",
                options=["Terraform", "Pulumi", "CloudFormation", "CDK"],
            ),
            _field("range", "On-call comfort level"),
            _field("social", "Link your GitHub profile", placeholder="https://github.com/…"),
            _field(
                "file", "Upload your resume", placeholder="PDF or DOCX, up to 10 MB", required=True
            ),
        ],
        "rubric": [
            {
                "name": "Reliability engineering",
                "description": "SLOs, error budgets, and designing for graceful failure.",
                "weight": 30,
            },
            {
                "name": "Infrastructure depth",
                "description": "Networking, compute, and storage fundamentals at scale.",
                "weight": 25,
            },
            {
                "name": "Incident response",
                "description": "Calm, structured command and blameless follow-up.",
                "weight": 20,
            },
            {
                "name": "Automation & IaC",
                "description": "Repeatable, reviewed infrastructure changes.",
                "weight": 15,
            },
            {
                "name": "Communication",
                "description": "Clear status and tradeoff communication under pressure.",
                "weight": 10,
            },
        ],
        "clicks": 96,
        "uses": 12,
    },
    {
        "code": "PRO-002",
        "title": "Product Manager",
        "domain": "Product",
        "skills": ["Figma", "SQL"],
        "objective": (
            "Own the candidate-experience surface from discovery to launch, "
            "balancing user delight with measurable funnel impact."
        ),
        "sample_questions": [
            "Walk me through a product bet that failed and what you learned.",
            "How do you decide what not to build in a crowded roadmap?",
            "Describe how you turned a fuzzy metric into a concrete product goal.",
        ],
        "tone": "conversational",
        "status": "open",
        "interview_type": "product_manager",
        "close_in_days": 21,
        "screening_fields": [
            _field(
                "text",
                "Current role / title",
                placeholder="e.g. Senior Product Manager",
                required=True,
            ),
            _field(
                "textarea",
                "Describe a product bet that failed and what you learned",
                placeholder="The bet, the outcome, and the lesson…",
                required=True,
            ),
            _field(
                "multiple_choice",
                "Product surface you are strongest in",
                options=["Consumer", "B2B SaaS", "Platform / API", "Growth"],
            ),
            _field("range", "Comfort reading SQL and dashboards"),
            _field("date", "Earliest available start date"),
            _field("social", "Link your LinkedIn profile", placeholder="https://linkedin.com/in/…"),
            _field(
                "file", "Upload your resume", placeholder="PDF or DOCX, up to 10 MB", required=True
            ),
        ],
        "rubric": [
            {
                "name": "Product sense",
                "description": "Judgment on what to build and why it matters to users.",
                "weight": 30,
            },
            {
                "name": "Execution & delivery",
                "description": "Driving cross-functional work from discovery to launch.",
                "weight": 25,
            },
            {
                "name": "Analytical rigor",
                "description": "Framing decisions with data and clear success metrics.",
                "weight": 20,
            },
            {
                "name": "Stakeholder communication",
                "description": "Aligning engineering, design, and leadership.",
                "weight": 15,
            },
            {
                "name": "Leadership",
                "description": "Influence without authority and raising the team's bar.",
                "weight": 10,
            },
        ],
        "clicks": 188,
        "uses": 27,
    },
    {
        "code": "MKT-005",
        "title": "Growth Marketer",
        "domain": "Marketing",
        "skills": ["SEO", "Content Strategy"],
        "objective": (
            "Scale organic acquisition with a content-led motion, owning the "
            "loop from keyword research through conversion."
        ),
        "sample_questions": [
            "Which growth loop are you proudest of building?",
            "How do you measure incrementality of a channel you own?",
            "Tell me about a campaign that underperformed and your response.",
        ],
        "tone": "friendly",
        "status": "closed",
        "interview_type": "growth_marketer",
        "close_in_days": -3,
        "screening_fields": [
            _field(
                "text",
                "Current role / title",
                placeholder="e.g. Growth Marketing Lead",
                required=True,
            ),
            _field(
                "textarea",
                "Describe the growth loop you are proudest of building",
                placeholder="The loop, the metrics, and your role…",
                required=True,
            ),
            _field(
                "multi_select",
                "Channels you have owned",
                options=[
                    "SEO / Content",
                    "Paid Social",
                    "Lifecycle / Email",
                    "Partnerships",
                    "Product-led",
                ],
            ),
            _field(
                "multiple_choice",
                "Attribution model you trust most",
                options=["Last-touch", "First-touch", "Multi-touch", "Incrementality"],
            ),
            _field("range", "Comfort with analytics tooling"),
            _field("social", "Link a portfolio or campaign you led", placeholder="https://…"),
            _field(
                "file", "Upload your resume", placeholder="PDF or DOCX, up to 10 MB", required=True
            ),
        ],
        "rubric": [
            {
                "name": "Growth strategy",
                "description": "Designing durable acquisition and retention loops.",
                "weight": 35,
            },
            {
                "name": "Channel expertise",
                "description": "Depth across the channels the role will own.",
                "weight": 25,
            },
            {
                "name": "Analytics & experimentation",
                "description": "Measuring incrementality and iterating on evidence.",
                "weight": 20,
            },
            {
                "name": "Creative & content",
                "description": "Judgment on messaging and content that converts.",
                "weight": 10,
            },
            {
                "name": "Communication",
                "description": "Crisp storytelling across stakeholders and channels.",
                "weight": 10,
            },
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
        # Clean integrity: every frame clear.
        "snapshot_plan": [
            (10, "clear", "Candidate centered, single face visible"),
            (130, "clear", "Single face, steady gaze at screen"),
            (250, "clear", "Single face, steady gaze at screen"),
            (370, "clear", "Candidate centered, single face visible"),
            (490, "clear", "Single face, steady gaze at screen"),
            (610, "clear", "Candidate centered, single face visible"),
        ],
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
        # Flagged integrity: sustained absence plus a second person in frame.
        "snapshot_plan": [
            (10, "clear", "Candidate centered, single face visible"),
            (130, "no_face", "Chair empty, no person in frame"),
            (250, "no_face", "Frame unchanged, candidate still absent"),
            (370, "multiple_faces", "Second person visible behind candidate"),
            (490, "clear", "Candidate centered, single face visible"),
            (610, "attention_shift", "Gaze directed off-screen to the right"),
        ],
    },
    {
        # Still-evaluating case: interview finalized minutes ago, scoring in
        # flight — no CriterionScore/Evaluation/Report rows, ScoringJob queued,
        # snapshots unanalyzed. Exercises console polling + "pending" frames.
        "email": "lena.fischer@example.dev",
        "name": "Lena Fischer",
        "story": (
            "I run the search-indexing pipeline for a marketplace: a Flink "
            "job consuming change streams and writing to OpenSearch, about "
            "five thousand documents a second at peak."
        ),
        "decision": None,
        "notes": None,
        "days_ago": 0,
        "duration_s": 1174,
        "evaluating": True,
        "snapshot_plan": [
            (10, None, None),
            (130, None, None),
            (250, None, None),
            (370, None, None),
            (490, None, None),
            (610, None, None),
        ],
    },
]

# Proctor snapshot cadence for seeded interviews: (offset seconds from
# interview start, signal, vision note). `signal=None` seeds an unanalyzed
# frame (pending vision analysis). Cases override via "snapshot_plan".
DEFAULT_SNAPSHOT_PLAN: list[tuple[int, str | None, str | None]] = [
    (10, "clear", "Candidate centered, single face visible"),
    (130, "clear", "Single face, steady gaze at screen"),
    (250, "attention_shift", "Gaze directed off-screen to the left"),
    (370, "clear", "Single face, steady gaze at screen"),
    (490, "low_light", "Face visible but underexposed"),
    (610, "clear", "Candidate centered, single face visible"),
]
