"""Prompts and JSON schemas. The model works ONLY from the evidence blocks it is given."""

GROUNDING = (
    "Use ONLY the evidence blocks provided; each starts with an id like [E-1a2b3c]. Cite the ids you rely on. "
    "When asked for a quote, copy a short exact fragment (3-15 words) character-for-character from one block. "
    "Never invent services, endpoints, tables, files or functions that are not in the evidence. "
    "Write for business readers: short, plain English, no jargon."
)

# ---------------------------------------------------------------- map: resolve an unclear call
RESOLVE_SYSTEM = "You are a senior engineer mapping how the services of a banking application depend on each other. " + GROUNDING

RESOLVE_USER = """A static code parser found a call it could not fully resolve.

Problem: {reason}

Code of the calling function, any helper code it uses, and the candidate endpoints:
{evidence}

Decide where this call really goes. Options:
{options}
- NOT_INTERNAL: the call does not go to one of our services (e.g. cloud platform, browser callback, generic helper)

Return "decision" (one option exactly), "category", "method" (HTTP method if known), a one-sentence "explanation",
a "quote" copied from the code that proves it, and "evidence_ids"."""


def resolve_schema(options: list[str]) -> dict:
    return {"type": "object", "properties": {
        "decision": {"type": "string", "enum": options + ["NOT_INTERNAL"]},
        "category": {"type": "string", "enum": ["internal_api", "cloud_infrastructure", "external_callback",
                                                "generic_helper", "unknown"]},
        "method": {"type": "string"}, "explanation": {"type": "string"}, "quote": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["decision", "category", "explanation", "quote", "evidence_ids"]}


# ---------------------------------------------------------------- map: describe one service
DESCRIBE_SYSTEM = "You explain a banking application's services to business analysts and managers. " + GROUNDING

DESCRIBE_USER = """Service: {service} ({language}). Business area from the catalog: {capability}.

Its API endpoints (ids in brackets), the data it uses, and the services it calls:
{facts}

Evidence (code):
{evidence}

Return:
- "service_summary": 1-2 plain sentences on what this service does for the bank and its customers.
- "endpoints": for each endpoint id listed above, a one-sentence "summary" of what it does.
- "links": for each link id listed above, a short "business_label" (max 8 words) saying WHY the link exists,
  e.g. "checks there is enough money before paying".
- "evidence_ids" you used."""

DESCRIBE_SCHEMA = {"type": "object", "properties": {
    "service_summary": {"type": "string"},
    "endpoints": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "summary": {"type": "string"}}, "required": ["id", "summary"]}},
    "links": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "business_label": {"type": "string"}}, "required": ["id", "business_label"]}},
    "evidence_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["service_summary", "endpoints", "links", "evidence_ids"]}

# ---------------------------------------------------------------- map: tables + column sensitivity
TABLES_SYSTEM = "You explain a bank's database tables to business readers and flag sensitive data. " + GROUNDING

TABLES_USER = """Database tables (ids in brackets) and their columns. Columns already labelled by the bank's
data register are marked with their label; the others are UNLABELLED.
{facts}

Evidence (table definitions):
{evidence}

Return:
- "tables": for each table id, a one-sentence "summary" of what it stores.
- "column_suggestions": ONLY for UNLABELLED columns that look sensitive: "id", suggested "classification"
  (Personal, Financial or Secret) and a short "reason".
- "evidence_ids"."""

TABLES_SCHEMA = {"type": "object", "properties": {
    "tables": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "summary": {"type": "string"}}, "required": ["id", "summary"]}},
    "column_suggestions": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "classification": {"type": "string", "enum": ["Personal", "Financial", "Secret"]},
        "reason": {"type": "string"}}, "required": ["id", "classification", "reason"]}},
    "evidence_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["tables", "column_suggestions", "evidence_ids"]}

# ---------------------------------------------------------------- impact 1: understand the CR
UNDERSTAND_SYSTEM = ("You are a senior business analyst at a bank reviewing a Jira change request before any coding starts. "
                     + GROUNDING)

UNDERSTAND_USER = """Change request {key}:
Title: {summary}
Description: {description}
Acceptance criteria:
{ac}
Components: {components}   Labels: {labels}

The system has these parts (use these exact names only):
{parts}

Return:
- "change_type": the main kind of change.
- "intent": one plain sentence saying what the business wants.
- "business_terms": key business words from the request (max 6).
- "likely_parts": names from the list above whose code or data will most likely need to CHANGE (max 3; only the
  parts that really must be edited, not everything that is connected).
- "new_data": new pieces of data the change needs to store (field name, the existing table it probably belongs to
  or "new", and whether it is Personal or Financial data). Empty list if none.
- "outside_systems": names from the list above of outside systems this change involves (empty if none).
- "open_questions": questions a BA must answer before development because the request is unclear or incomplete
  (max 4; empty if the request is clear).
- "assumptions": assumptions you had to make (max 3)."""

UNDERSTAND_SCHEMA = {"type": "object", "properties": {
    "change_type": {"type": "string", "enum": ["business rule", "new feature", "data change", "user interface",
                                               "integration", "performance", "security"]},
    "intent": {"type": "string"}, "business_terms": {"type": "array", "items": {"type": "string"}},
    "likely_parts": {"type": "array", "items": {"type": "string"}},
    "new_data": {"type": "array", "items": {"type": "object", "properties": {
        "field": {"type": "string"}, "table": {"type": "string"},
        "sensitivity": {"type": "string", "enum": ["Personal", "Financial", "None"]}},
        "required": ["field", "table", "sensitivity"]}},
    "outside_systems": {"type": "array", "items": {"type": "string"}},
    "open_questions": {"type": "array", "items": {"type": "string"}},
    "assumptions": {"type": "array", "items": {"type": "string"}}},
    "required": ["change_type", "intent", "business_terms", "likely_parts", "new_data", "outside_systems",
                 "open_questions", "assumptions"]}

# ---------------------------------------------------------------- impact 2: judge each candidate
JUDGE_SYSTEM = ("You are a lead engineer deciding exactly which parts of a banking system a change request will affect. "
                + GROUNDING)

JUDGE_USER = """Change request {key}: {summary}
What the business wants: {intent}

Candidates found by following the real dependency map from the parts the request mentions (id, what it is,
and why it is a candidate):
{candidates}

Code evidence:
{evidence}

For EVERY candidate id, decide a "verdict":
- "must_change": code or data here must be modified to deliver the request
- "likely_affected": probably needs a small change or a careful look
- "retest_only": no change needed, but it depends on something that changes, so it must be re-tested
- "not_impacted": not affected by this request
and write "how": one plain sentence on HOW it is affected (what changes, or why it must be re-tested).
Cite "evidence_ids" where you can.

Be precise, like an experienced lead engineer. Over-marking causes false alarms, extra approvals and wasted work:
- Choose the SMALLEST set of "must_change" parts that delivers the request. Most candidates are usually
  "retest_only" or "not_impacted".
- A TABLE is "must_change" only if its columns change or it must store a new kind of data. A table that is only
  read, or keeps receiving the same kind of rows, is at most "retest_only".
- An OUTSIDE SYSTEM is "not_impacted" unless the data it receives changes in structure or meaning.
- A service is "must_change" only if its own code must be edited; if it just calls or is called by a changing
  part, prefer "retest_only"."""

JUDGE_SCHEMA = {"type": "object", "properties": {
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"},
        "verdict": {"type": "string", "enum": ["must_change", "likely_affected", "retest_only", "not_impacted"]},
        "how": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["id", "verdict", "how"]}}},
    "required": ["items"]}

# ---------------------------------------------------------------- impact 3: business / testing / risk assessment
ASSESS_SYSTEM = ("You write the impact assessment that a bank's change board reads before approving work. "
                 + GROUNDING)

ASSESS_USER = """Change request {key}: {summary}
What the business wants: {intent}

Facts established by code analysis and the bank's rules:
{facts}

Return:
- "summary": 2-3 plain sentences for managers: what changes, what it touches, and the main risk.
- "business_impact": 1-2 sentences on the effect on customers, operations or other teams.
- "test_scenarios": 3-5 concrete test cases a tester should run (each one short sentence, include edge cases).
- "size": T-shirt size of the work (S, M, L or XL) and "size_reason" in one sentence.
- "risks": up to 3 short risk statements."""

ASSESS_SCHEMA = {"type": "object", "properties": {
    "summary": {"type": "string"}, "business_impact": {"type": "string"},
    "test_scenarios": {"type": "array", "items": {"type": "string"}},
    "size": {"type": "string", "enum": ["S", "M", "L", "XL"]}, "size_reason": {"type": "string"},
    "risks": {"type": "array", "items": {"type": "string"}}},
    "required": ["summary", "business_impact", "test_scenarios", "size", "size_reason", "risks"]}

# ---------------------------------------------------------------- map: name and narrate customer journeys
JOURNEYS_SYSTEM = "You describe what happens inside a banking app when a customer does something. " + GROUNDING

JOURNEYS_USER = """Each journey below is a VERIFIED, ordered chain of calls that starts when the customer uses a
page of the website. Do not add, remove or reorder steps.

{facts}

Return "journeys": for each journey id, a short "name" a customer would understand (2-4 words, e.g.
"Send money"), a one-sentence "summary", and "steps": one plain-English sentence per step, in the same order,
as a list of strings with exactly the same number of items as the journey has steps."""

JOURNEYS_SCHEMA = {"type": "object", "properties": {
    "journeys": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "name": {"type": "string"}, "summary": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}}}, "required": ["id", "name", "summary", "steps"]}}},
    "required": ["journeys"]}
