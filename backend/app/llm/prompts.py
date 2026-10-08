"""Prompts and JSON schemas. The model only explains and drafts; facts come from the engine."""

GROUNDING = (
    "Use ONLY the evidence blocks provided. Each block starts with an id like [E-1a2b3c]. "
    "Every claim must cite the ids it relies on. When asked for a quote, copy a short exact phrase "
    "(3-12 words) character-for-character from one of the cited blocks. Never invent systems, files, "
    "functions or numbers that are not in the evidence. If the evidence is insufficient, say so."
)

IMPACT_SYSTEM = (
    "You are a senior change-impact analyst at a bank, writing for delivery leads and testers. "
    + GROUNDING
)

IMPACT_USER = """Change request:
{cr}

Facts already established by static analysis and the curated catalog:
{facts}

Evidence:
{evidence}

Write:
1. "summary": 2-3 plain-English sentences on what this change affects and why it matters to the business.
2. "key_risks": up to 3 DIFFERENT risks. Each "text" is one sentence (max 25 words) about a specific module,
   table or downstream system. Do not repeat the facts list. "quote" must be copied from an Evidence block
   (code, catalog or change request), never from the facts list.
3. "suggested_tests": up to 3 new test cases a tester should add. "target" is a function name that appears
   in the code evidence (for example build_daily_extract)."""

IMPACT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_risks": {"type": "array", "maxItems": 4, "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}},
                           "quote": {"type": "string"}},
            "required": ["text", "evidence_ids", "quote"]}},
        "suggested_tests": {"type": "array", "maxItems": 4, "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "target": {"type": "string"},
                           "evidence_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["title", "target", "evidence_ids"]}},
    },
    "required": ["summary", "key_risks", "suggested_tests"],
}

REVIEW_SYSTEM = (
    "You are a release reviewer at a bank summarising whether a pull request matches its planned change. "
    + GROUNDING
)

REVIEW_USER = """Pull request: {pr}

Findings already established by comparing the confirmed plan with the actual code changes:
{facts}

Evidence:
{evidence}

Write "summary": 2-3 plain-English sentences for a release manager: what matched the plan, what is missing or
unexpected, and what must happen before release. Cite evidence_ids."""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["summary", "evidence_ids"],
}

DOC_SYSTEM = (
    "You are a meticulous technical writer keeping documentation in sync with code. "
    "Rewrite ONLY the given Markdown section so it is correct for the current code. Keep the exact same first "
    "heading line. Keep every statement that is still correct. Make the smallest change that fixes the problem. "
    "Do not add new headings. " + GROUNDING
)

DOC_USER = """Problem detected: {title}
Explanation: {explanation}

Current section (from {doc_path}):
<<<
{section}
>>>

Rule-based draft you may improve (wording, brief description) but must stay consistent with:
<<<
{draft}
>>>

Evidence:
{evidence}

Return "updated_section" (the full corrected Markdown section), "change_summary" (one sentence) and "evidence_ids"."""

DOC_SCHEMA = {
    "type": "object",
    "properties": {"updated_section": {"type": "string"}, "change_summary": {"type": "string"},
                   "evidence_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["updated_section", "change_summary", "evidence_ids"],
}
