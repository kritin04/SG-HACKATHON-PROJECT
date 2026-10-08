# Change Assurance Copilot: Project Guide

> A plain-language guide to **everything** in this project: what it does, why, how every part works, and what was built in which step. It's updated after every build step (see [Change log](#12-change-log)).

---

## 1. Summary

**What it is:** a local AI assistant that answers one question for a Jira change request (CR):
**"If we make this change, what will it affect, and how?"**

**Who it's for:** Business Analysts, Product Owners, Lead Engineers, Developers, Testers and Risk/Compliance. Today they spend hours tracing the impact of every CR by hand.

**Problem statement covered:** *#8 AI Change-Impact and Testing Intelligence*. Self-Healing Documentation is parked for later (see `deferred/`).

**The three features:**

| # | Feature | Status |
|---|---|---|
| 1 | **Impact Analysis of a Jira CR**: what must change, what is affected, how, why, tests, risks, approvals | planned (built on the map) |
| 2 | **Interactive dependency map** of the whole project, with the CR's impact drawn on it | in progress: map engine done |
| 3 | Self-Healing Docs | parked |

**Key principles:**
1. **Code finds the facts, AI adds understanding, code checks the AI.**
2. **Every link and every claim points to proof**: a file and line in the real code or config.
3. **Runs 100% locally** with Ollama. No data leaves the machine, and there are no paid or cloud APIs.
4. **No model training.** We use retrieval, structured prompts and verification.

---

## 2. How to run

> Windows / PowerShell. Prerequisites: Python 3.12, Node 20+, git, [Ollama](https://ollama.com).

```powershell
# 1. Local AI models (one-off)
ollama pull qwen2.5:3b          # fast model for live use
ollama pull qwen2.5:7b          # better model for pre-computing demo results
ollama pull nomic-embed-text    # turns text into vectors for meaning-based search

# 2. The project we analyse (Bank of Anthos, pinned commit)
.\scripts\fetch_repo.ps1

# 3. Backend
python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt

# 4. Tests (checks map accuracy against the answer key)
cd backend; .venv\Scripts\python -m pytest -q
```

*(The UI steps will be added when the screens are rebuilt.)*

---

## 3. Architecture overview

```
 Bank of Anthos repo (real code)      Catalog (YAML, synthetic)       Jira CRs (JSON)
        │                                     │                             │
        ▼                                     │                             │
 ┌───────────────── MAP BUILDER (backend/app/mapbuild) ─────────────┐       │
 │ 1 Inventory     k8s.py            services + databases            │       │
 │ 2 Code facts    python_extract.py  java_extract.py                │       │
 │ 3 Config/schema k8s.py  schema.py                                 │       │
 │ 4 Join links    build.py          calls→endpoints, DB, tokens     │◄──────┘ (later: impact)
 │ 5 AI enrich     enrich.py  (next step)                            │
 │ 6 Check         mapcheck.py       accuracy vs answer key          │
 └───────────────────────────────────────────────────────────────────┘
        │  ProjectMap (nodes + edges + evidence)
        ▼
 Impact Analyzer (next steps) ──► API (FastAPI) ──► UI (React): Board · Impact page · Map
```

### Folders

| Folder / file | What it does |
|---|---|
| `demo_data/project.yaml` | Which repo we analyse and the pinned commit |
| `demo_data/catalog/*.yaml` | Knowledge not in the code: owners, outside systems, data labels, approval rules, business words (**synthetic**) |
| `demo_data/jira/issues.json` | 9 plain-language change requests |
| `demo_data/map_truth.yaml` | **Answer key**: the true links, hand-checked against the code |
| `backend/app/mapbuild/` | Builds the dependency map (section 5) |
| `backend/app/engine/` | Shared pieces: evidence store, catalog loader, control rules |
| `backend/app/llm/` | Local AI client and the verifier that checks AI output |
| `backend/tests/` | Automatic checks (map accuracy, verifier) |
| `scripts/fetch_repo.ps1` | Downloads Bank of Anthos at the pinned commit |
| `deferred/self_healing_docs/` | Parked Self-Healing Docs engine |
| `workspace/` | Generated or downloaded files (not committed) |

---

## 4. Demo project: Bank of Anthos

**What it is:** Google's open-source sample bank (Apache 2.0). Customers sign up, log in, see their balance, send money, deposit and see history. It's finance, but everyone understands it.
Source: <https://github.com/GoogleCloudPlatform/bank-of-anthos>, pinned at commit `db35fea` (release v0.6.11).

| Part | Language | Plain role |
|---|---|---|
| **frontend** | Python (Flask) | The website: login, sign-up, home, send money, deposit |
| **userservice** | Python | Creates accounts, checks passwords, **signs login tokens** |
| **contacts** | Python | Saved payees ("send money to Mum") |
| **ledgerwriter** | Java (Spring) | Checks and **records every payment / deposit** |
| **balancereader** | Java (Spring) | Gives the **balance** (fast cached copy) |
| **transactionhistory** | Java (Spring) | Gives **past transactions** (cached) |
| **accounts-db** | PostgreSQL | Tables `users`, `contacts` |
| **ledger-db** | PostgreSQL | Table `transactions` |

**Real vs synthetic:**

| Real (from the GitHub code) | Synthetic (written by us for the demo) |
|---|---|
| Services, APIs, calls, databases, tables, columns, settings, tests, token signing/checking | Owners/teams, outside systems (Regulatory Reporting, Finance Ledger, Fraud, CRM, SMS provider), data labels (Personal/Financial), approval rules, Jira CRs |

At a real bank, the synthetic parts would be **imported** from existing registers: the CMDB, the interface catalogue, the data classification register and the change policies.

---

## 5. The dependency map

### 5.1 What the map contains (4 zoom levels)

| Level | Shows | Example |
|---|---|---|
| **L1 System** | services, databases, outside systems, the customer | frontend → ledgerwriter → ledger-db |
| **L2 Interfaces** | API endpoints, tables, settings | `POST /transactions`, table `transactions`, `BALANCES_API_ADDR` |
| **L3 Code** | functions, tests | `LedgerWriterController.addTransaction()` |
| **L4 Data** | table columns with sensitivity labels | `users.ssn` (Personal, highly sensitive) |

**Link types (shown as plain verbs):**

| Link | Meaning | Example |
|---|---|---|
| uses | the customer uses a service | Customer → frontend |
| calls | one service calls another's API | frontend → ledgerwriter `POST /transactions` |
| reads / writes | a service reads or saves a table | ledgerwriter **writes** `transactions` |
| needs setting | a service reads a configuration value | ledgerwriter needs `BALANCES_API_ADDR` |
| trusts login tokens from | security dependency | balancereader trusts tokens from userservice |
| handled by | an endpoint's code | `POST /transactions` → `addTransaction()` |
| tests | a test checks this code | `TransactionValidatorTest` → `validateTransaction()` |
| reads (outside system) | an outside system uses our data (catalog) | Regulatory Reporting reads `transactions` |

**Every link stores:**
- **origin**: where the fact came from: `code`, `config`, `schema`, `catalog`, `ai` or `human`
- **confidence**: 1.0 = exact; lower = inferred
- **evidence**: IDs of the exact file lines that prove it (shown in the UI's "Why?" panel)

### 5.2 How it's built, step by step

**Step 1: Inventory** (`mapbuild/k8s.py`)
Reads every Kubernetes file in `kubernetes-manifests/`. Each *Deployment* is a **service** and each *StatefulSet* (database image) is a **database**. It also records which settings each service receives (from ConfigMaps).
Result: 6 services, 2 databases.

**Step 2: Read the code**
- **Python** (`python_extract.py`, Python's built-in parser `ast`):
  - routes: `@app.route('/payment', methods=['POST'])`
  - settings: `os.environ.get('X')`
  - **two-step URL wiring** (the frontend's style): first `app.config["TRANSACTIONS_URI"] = 'http://{}/transactions'.format(os.environ.get('TRANSACTIONS_API_ADDR'))`, then `requests.post(url=app.config["TRANSACTIONS_URI"])`. The extractor follows both steps.
  - database tables: `Table("users", ...)` then `self.users_table.insert()` = write, `.select()` = read
  - login tokens: `jwt.encode` = signs tokens, `jwt.decode` = checks tokens
  - tests: `test_*` functions and the URLs they request
- **Java** (`java_extract.py`, the **tree-sitter** parser):
  - routes: `@PostMapping("/transactions")`
  - settings: `@Value("${LOCAL_ROUTING_NUM}")`
  - **URL wiring**: `@Value("http://${BALANCES_API_ADDR}/balances") String balancesApiUri`, then `String uri = balancesApiUri + "/" + fromAcct;`, then `restTemplate.exchange(uri, HttpMethod.GET, ...)`
  - database: `@Entity @Table(name = "TRANSACTIONS")` + repository interfaces; `repository.save(...)` = write, `@Query("SELECT ...")` = read
  - tests: methods marked `@Test` and the methods they call

**Step 3: Config and schema** (`k8s.py`, `schema.py`)
- `config.yaml` says `BALANCES_API_ADDR: "balancereader:8080"`, so that setting **points to the balancereader service**.
- `ACCOUNTS_DB_URI: postgresql://...@accounts-db:5432/...` **points to the accounts-db database**.
- Database init scripts (`CREATE TABLE users (...)`) give the **tables and columns**.

**Step 4: Join the dots** (`build.py`)
- *call + setting + endpoint*: the frontend calls `<TRANSACTIONS_API_ADDR>/transactions` with POST; the setting points to ledgerwriter; ledgerwriter offers `POST /transactions`. So the link is **frontend → ledgerwriter `POST /transactions`**, with evidence: the call line, the config line and the endpoint code.
- *table use + database setting*: userservice writes `users` and connects to accounts-db, so the link is **userservice writes accounts-db.users**.
- *tokens*: userservice signs; 5 services verify, so they each get **"trusts login tokens from userservice"**.
- *catalog*: outside systems are attached to the tables they read.

**Step 5: AI enrichment** *(next build step)*: resolves what the parsers can't, writes plain-English descriptions, business labels, groups and journeys. **Every AI suggestion is checked before it's drawn.**

**Step 6: Accuracy check** (`mapcheck.py` vs `demo_data/map_truth.yaml`). See section 10.

### 5.3 What the code alone could NOT resolve (and why the AI step exists)

| Unresolved call | Why the parser can't decide | What the AI step will do |
|---|---|---|
| frontend home page → contacts `/contacts/{username}` | The call goes through a helper class (`ApiRequest` → `ApiCall.make_call`) that hides the HTTP method, and contacts offers **both GET and POST** on that path | Read the helper's code, decide GET, quote the line `get(url=...)`. The verifier checks that the quote exists and that the endpoint exists |
| `requests.get(metadata_url + ...)` | URL built from a cloud metadata server address | Classify as infrastructure (cloud platform), not a business dependency |
| `requests.post(url=redirect_uri)` | URL comes from the user's browser (OAuth login callback) | Classify as an external login callback |

---

## 6. Impact analysis *(to be built: steps 6-9)*
Planned 6 stages: understand the CR (AI) → find entry points (glossary + meaning-based search) → follow the map (blast radius) → AI judges each candidate (*must change / likely affected / retest / not impacted*, with **how**) → rules + AI assess business, testing, compliance and risk → verify and show.

## 7. AI layer *(to be extended)*
- `llm/ollama_client.py`: talks to the local Ollama server and asks for answers in a fixed JSON format.
- `llm/verify.py`: **code that checks the AI**:
  - cited evidence must exist
  - quotes must appear word-for-word in that evidence
  - targets must exist in the map
  - doc edits must stay inside their section

## 8. Data files
- `project.yaml`: repo, pinned commit, excluded folders (load generator, monolith variant), health endpoints hidden by default.
- `catalog/services.yaml`: owner team, business capability, criticality per service.
- `catalog/external.yaml`: outside systems and the tables they read (Regulatory Reporting, Finance General Ledger, Fraud Screening, CRM, SMS/Email provider).
- `catalog/data_classification.yaml`: labels on real columns (`users.ssn` = Personal (highly sensitive), `transactions.amount` = Financial, …).
- `catalog/controls.yaml`: approval rules (Personal-data review, Payments-logic approval, API contract sign-off, Regulatory reporting review, New vendor integration).
- `catalog/glossary.yaml`: business words → system parts ("payee" → contacts).
- `jira/issues.json`: 9 CRs in the real Jira REST format (key, summary, description, acceptance criteria, components, labels, priority, assignee):

| Key | Change request | Why it's in the demo |
|---|---|---|
| BOA-101 | Daily limit: max $5,000 sent per day | Payments logic + data read; payments approval |
| BOA-102 | Show payee name in history | Crosses 3 services |
| BOA-103 | Delete a saved contact | New API (contract change) |
| BOA-104 | Block payments to own account | Small, local change |
| BOA-105 | Phone number at sign-up | **Personal data** + outside systems (CRM, Regulatory) |
| BOA-106 | Download history as CSV | Read-only, low risk |
| BOA-107 | SMS when balance < $100 | **New outside vendor** |
| BOA-108 | "Make the balance show faster" | **Vague**, so the AI raises open questions |
| BOA-109 | Minimum deposit $10 | Small payments rule |

## 9. UI walkthrough *(screens to be rebuilt: Board · Impact Analysis · Dependency Map)*

## 10. Testing and accuracy
Tests (`backend/tests/`), run with `pytest -q`:
- `test_map.py`: the map vs the answer key, and every link has proof
- `test_verify.py`: the AI checker rejects fake evidence and made-up quotes

**Map accuracy (code + config only, before AI):**

| Category | Expected | Found | Wrong links |
|---|---|---|---|
| Services / databases / tables | 6 / 2 / 3 | 6 / 2 / 3 | 0 |
| Endpoints (business) | 18 | 18 | 0 |
| Service → API calls | 8 | **7** | 0 |
| Table reads/writes | 7 | 7 | 0 |
| Token trust | 5 | 5 | 0 |
| **Overall** | **49** | **48 (98%)** | **0 (100% precision)** |

The 1 missing link is the ambiguous helper call in 5.3, which the AI step is designed to close.

## 11. Limits and adapting to a real bank
- **Languages:** Python and Java are supported now. Other languages need their own extractor with the same `ServiceFacts` shape (tree-sitter has grammars for most languages).
- **Wiring styles:** HTTP calls wired through settings (Kubernetes ConfigMaps) are exact. Messaging (Kafka/MQ topics) and other styles need extra patterns.
- **Multi-repo:** run the builder per repo and merge the maps. Links join on API paths, settings, table and topic names.
- **Catalog:** import it from real registers instead of hand-written YAML.

## 12. Change log

| Step | What was done |
|---|---|
| v1 (earlier) | First prototype on a fake bank (NovaBank) with Impact, Release Readiness and Doc Health screens. The team found it too broad and cluttered. |
| Re-plan | Focus on Impact Analysis + Dependency Map; demo project switched to Bank of Anthos; Release Readiness removed; Self-Healing Docs parked |
| Chunk 1: Purge | Removed Release Readiness, Doc Health, NovaBank data and old tests; parked `docdrift.py` in `deferred/` |
| Chunk 2: Demo data | Pinned Bank of Anthos (`db35fea`), wrote catalog, 9 CRs, map answer key |
| Chunk 3: Map builder | Kubernetes, Python and Java extractors, schema reader, link joining, accuracy checker. **48/49 facts, 0 wrong links** |
