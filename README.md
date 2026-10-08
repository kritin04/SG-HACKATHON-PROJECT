# Change Assurance Copilot

A local-first assistant that makes every software change **predictable, verified and documented**.

| Question | Feature | Problem statement |
|---|---|---|
| *Before coding:* "If we make this change, what will it affect?" | **Change Impact Analyzer** | #8 AI Change-Impact & Testing Intelligence |
| *Before merging:* "Did the code match the plan, and what did we miss?" | **Release Readiness** (PR reconciliation) | #8 AI Change-Impact & Testing Intelligence |
| *After shipping:* "Which docs are out of date, and what should they say?" | **Self-Healing Docs** | Self-Healing Documentation |

All AI runs locally through **Ollama**. There are no paid APIs and no cloud model calls, and no code or data leaves the machine. All demo data is **synthetic** (fictional "NovaBank" payments platform).

## How it works

```
Jira CR / PR / git repo / docs / tests ──► Indexer (Python ast, SQL + Markdown parsing)
                                              │
Curated catalog (systems, downstream,  ──► Dependency graph (NetworkX) ──► Impact propagation
glossary, data classes, controls)             │                                │
                                              ▼                                ▼
                                   Deterministic findings ──► Evidence pack ──► Local LLM (Ollama)
                                                                                 │
                                                       Verifier (code, not AI) ◄─┘
                                                       • cited evidence ids must exist
                                                       • quotes must appear verbatim
                                                       • doc fixes may only change the affected section
```

* **Facts come from deterministic analysis**: the dependency graph, rules and diffs.
* **The local LLM only explains and drafts**: impact brief, release summary, doc rewrites.
* **Every AI claim is verified** against cited evidence. Unverified claims are shown greyed out and are never used.
* **No model training.** Retrieval, structured prompts, JSON-schema output and verification are enough.
* Every item carries a badge: **Auto-detected** (from code), **From catalog** (curated by people) or **Human-confirmed**.

## Run it (Windows, PowerShell)

Prerequisites: Python 3.12, Node 20+, git, [Ollama](https://ollama.com).

```powershell
# 1. Local models (one-off)
ollama pull qwen2.5:3b      # live model
ollama pull qwen2.5:7b      # higher-quality precompute model

# 2. Backend
python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt

# 3. Synthetic demo repository + reset demo state
.\scripts\seed.ps1

# 4. (Recommended) warm the AI cache so the demo never waits on CPU inference (~25 min on a laptop CPU)
backend\.venv\Scripts\python scripts\precompute.py

# 5. Start
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000     # terminal 1
cd frontend; npm install; npm run dev                                     # terminal 2
```

Open http://localhost:5173.

Tests: `cd backend; .venv\Scripts\python -m pytest -q`. They check the engine against `demo_data/ground_truth.yaml` and check that the verifier rejects forged citations.

Configuration (environment variables): `CAC_LIVE_MODEL`, `CAC_PRECOMPUTE_MODEL`, `CAC_OLLAMA_URL`, `CAC_REPO`, `CAC_DEMO_DATA`.

## Demo walkthrough (about 5 minutes)

1. **Impact Analyzer → PAY-142, "Introduce cross-border transfer fee"**
   * Rated High risk.
   * Impacted code: fee, transfer, ledger and reporting modules.
   * Downstream: the Regulatory Reporting Hub (from the catalog).
   * Tests to run and test gaps.
   * Triggered controls: pricing approval, regulatory reporting review, financial data integrity.
   * Click **Why?** on any row to see the dependency path and the exact code and catalog evidence.
   * Untick anything out of scope, then **Confirm baseline**.
2. **Release Readiness → PR #57**: *Not ready, 6 blocking actions.*
   * Unplanned change: the PR reads a **PII** column (`customer_profile.residency_country`) that wasn't in the plan, so a privacy review is required.
   * Likely miss: `reporting/extract.py` was planned but not changed, even though the regulator extract must include the FX markup.
   * Control checklist shows no privacy-officer or reg-reporting approval and no fee doc update. 4 changed functions have no tests.
3. **Self-Healing Docs**
   * 2 stale and 2 missing doc sections left behind by stories PAY-131 and PAY-135, which closed without documentation changes.
   * The AI-drafted fix is shown as a diff. **Approve** commits it to the `docs/auto-heal` branch of the repo for normal review.

## Repository layout

```
backend/app/engine/   gitrepo · indexer · graph · catalog · impact · reconcile · docdrift · controls · evidence
backend/app/llm/      ollama_client · prompts · verify · service (cache + fallback)
backend/app/main.py   FastAPI API
frontend/src/         React + Tailwind UI (Impact Analyzer, Release Readiness, Self-Healing Docs)
demo_data/            generate_repo.py, jira/, prs/, catalog/, ground_truth.yaml  ← the only domain-specific part
scripts/              seed.ps1, precompute.py
```

To use another domain, replace the contents of `demo_data/` (repo generator or a real local repo via `CAC_REPO`, Jira/PR fixtures and catalog YAML). The engine and UI are domain-agnostic.

## Honest limits

* The demo uses synthetic data, so the numbers show how the method works. They aren't measured productivity.
* Static analysis is Python-only in this POC, and dynamic calls can be missed. Cross-service links matched by URL get *medium confidence*.
* Downstream systems, business terms, data classification and controls come from a **curated catalog**, so the results are only as good as that catalog.
* Controls are synthetic examples. The tool reports "control X triggered by rule Y". It never decides compliance.
