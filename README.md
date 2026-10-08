# Change Impact Copilot

**AI change-impact analysis for Jira change requests: before any code is written, running fully on a laptop.**

> Hackathon problem statement **#8: AI Change-Impact and Testing Intelligence**

Before a change is built, developers, leads, testers and BAs spend hours working out what it will touch: which services, which data, which other teams, which approvals. The Change Impact Copilot does this in minutes. It reads the Jira ticket, follows a verified map of the real code, uses a **local AI** to judge what must change and **how**, and posts the result back to Jira, **with proof for every claim**.

---

## What it does

| Feature | |
|---|---|
| **Jira integration** | Syncs change requests from Jira Cloud (REST API v3) and posts the impact summary back as a comment |
| **Impact analysis** | For each ticket: risk, size, what **must change / is likely affected / needs re-testing** and how, open questions for the BA, sensitive data, outside systems to notify, approvals required, tests to re-run, test gaps, people to involve |
| **Dependency map** | An interactive map of the whole system, built automatically from code and config, with *what-if* analysis, customer journeys and a ticket's impact overlaid |
| **Proof & control** | Every item links to the exact file and line it's based on; reviewers can change any verdict, and every edit is logged |

**Demo system:** [Bank of Anthos](https://github.com/GoogleCloudPlatform/bank-of-anthos), Google's open-source sample bank (6 services in Python and Java, 2 PostgreSQL databases), pinned to `v0.6.11`.

---

## How it works

```
Jira ticket ──► 1 Understand (AI) ──► 2 Find entry points ──► 3 Follow the dependency map
                                        (glossary + embeddings)       (verified links only)
            ◄── 6 Post to Jira ◄── 5 Assess (rules + AI) ◄── 4 Judge each part (AI)
```

1. **Map builder:** parses Kubernetes manifests, Python (`ast`), Java (`tree-sitter`) and SQL schemas into services, APIs, tables, settings and tests. Calls are resolved to real endpoints through config wiring. The AI only resolves what parsing can't, and its answer must quote real code.
2. **Impact pipeline:** the AI may only judge candidates found on the verified map. A verifier checks every citation, and anything unproven falls back to rules and is labelled as such.
3. **Bank knowledge** (owners, outside systems, data classification, approval rules) comes from a small catalog. At a bank this would be imported from the CMDB, interface catalogue and data register.

**No model training. No cloud AI.** Models run locally via [Ollama](https://ollama.com): `qwen2.5:7b`, `qwen2.5:3b` and `nomic-embed-text`.

---

## Results

| | |
|---|---|
| **Dependency map** vs hand-checked answer key | **49/49 facts correct, 0 wrong links** (48/49 from parsing, the last one resolved by the AI) |
| **Impact analysis**, 9 change requests vs an engineer's answer key | **100%** of involved parts found · **100%** of required approvals and outside systems · **0** parts wrongly marked "must change" |
| Risk levels | High only where expected (new personal data, new third-party vendor); a vague ticket is rated Low with clarifying questions |

---

## Quick start (Windows)

**Prerequisites:** Python 3.12, Node 20+, Git, Ollama.

```powershell
ollama pull qwen2.5:7b; ollama pull qwen2.5:3b; ollama pull nomic-embed-text
.\scripts\fetch_repo.ps1                                   # downloads Bank of Anthos (pinned)

python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..

# optional, ~1-2 h on a CPU laptop: pre-compute AI results so the demo opens instantly (cached)
backend\.venv\Scripts\python scripts\build_map.py
backend\.venv\Scripts\python scripts\precompute_crs.py

cd backend;  .venv\Scripts\python -m uvicorn app.main:app --port 8000   # terminal 1
cd frontend; npm run dev                                               # terminal 2 -> http://localhost:5173
```

Without Jira settings, the app uses the 9 demo change requests in `demo_data/jira/`.

### Connect Jira Cloud (optional)
1. Create a free Jira Cloud site with a space whose key is `BOA` (optionally add a *Change Request* work type).
2. Create an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>.
3. Copy `.env.example` to `.env` and fill in `JIRA_BASE_URL`, `JIRA_EMAIL` and `JIRA_API_TOKEN`.
4. Load the demo tickets: `backend\.venv\Scripts\python scripts\seed_jira.py --issuetype "Change Request"`
5. In the app, click **Sync from Jira**.

No Jira account? `jira_sim/` is a small local tracker with the same API: run `backend\.venv\Scripts\python -m uvicorn jira_sim.server:app --port 8090` and set `JIRA_BASE_URL=http://localhost:8090`.

### Tests
```powershell
cd backend; .venv\Scripts\python -m pytest -q
```
These cover map accuracy, impact rules, the AI verifier, the Jira parser, and cached AI results vs the answer key.

---

## Repository

```
backend/app/mapbuild/   dependency map: Kubernetes, Python & Java parsers, link resolution, AI enrichment
backend/app/engine/     impact pipeline, change propagation, embeddings, approval rules, evaluation
backend/app/llm/        local AI client, prompts, verifier
backend/app/jira/       Jira REST client, rich-text parser, sync & publish
frontend/src/           React UI: Board, Impact page, Dependency Map
demo_data/              pinned project, demo catalog, 9 change requests, answer keys
jira_sim/               optional local Jira-compatible tracker
scripts/                fetch repo, pre-compute, seed Jira
```

## Documentation
- **[PROJECT_GUIDE.md](PROJECT_GUIDE.md)**: how everything works, step by step
- **[DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md)**: every screen explained, plus the demo video script

## Limitations
- Python and Java parsers today; other languages plug in through the same interface.
- On a CPU laptop a full AI analysis takes about 5-10 minutes; on a GPU or server, seconds.
- Owners, outside systems, data labels, approval rules and change requests are demo data; the code, map, AI and Jira integration are real.
