# Change Impact Copilot: Project Guide

> A plain-language guide to **everything** in this project: what it does, why, how every part works, what's real and what's synthetic, how accurate it is, and what was built in which step. It's updated after every build step (see [Change log](#12-change-log)).

---

## 1. Summary

**What it is:** a local AI assistant that answers one question for a Jira change request (CR):
> **"If we make this change, what will it affect, how, and who needs to be involved?"**

It answers **before any code is written**, which is when impact analysis is cheapest and most useful.

**Who it's for:** Business Analysts, Product Owners, Lead Engineers, Developers, Testers and Risk/Compliance. Today they spend hours tracing the impact of every CR by hand, across code, databases, other teams' systems and company rules.

**Problem statement covered:** *#8 AI Change-Impact and Testing Intelligence*. (Self-Healing Documentation is parked in `deferred/`; Release Readiness was removed.)

| # | Feature | Status |
|---|---|---|
| 1 | **Impact Analysis of a Jira CR**: what must change, what is likely affected, what to re-test, HOW each part is affected, data sensitivity, outside systems, approvals, tests, people, risk, size | ✅ built |
| 2 | **Interactive dependency map** of the whole project: 4 views, what-if, customer journeys, CR impact overlay | ✅ built |
| 3 | Self-Healing Docs | parked |

**Key principles:**
1. **Code finds the facts, AI adds understanding, code checks the AI's structure.** The AI never invents a dependency; it only judges candidates found in the verified map, and names it gives that aren't on the map are dropped.
2. **Every link and every item points to proof**: a file and line in the real code, config or schema ("Show proof" / "Why?" buttons). The AI's free text (summary, "how" sentences, test ideas) is written from those facts but not checked line by line.
3. **The AI runs 100% locally** with Ollama: no code or data is sent to an AI provider, and there are no paid APIs. The only internet traffic is the optional Jira Cloud connection (tickets in, summary comments out).
4. **No model training.** We use retrieval, structured prompts, JSON-schema answers and verification.
5. **Honest about uncertainty.** Every item says where it came from: *From code*, *From config*, *From catalog*, *AI*, *Rules* or *Reviewer*.

---

## 2. How to run

> Windows / PowerShell. Prerequisites: Python 3.12, Node 20+, git, [Ollama](https://ollama.com).

```powershell
# 1. Local AI models (one-off)
ollama pull qwen2.5:3b          # fast model, used live
ollama pull qwen2.5:7b          # better model, used to pre-compute demo results
ollama pull nomic-embed-text    # turns text into vectors for meaning-based search

# 2. The project we analyse (Bank of Anthos, pinned commit)
.\scripts\fetch_repo.ps1

# 3. Backend + frontend dependencies
python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..

# 4. Pre-compute the AI parts once with the 7B model. Results are cached.
#    CPU laptop: map about 20 min; each CR about 10-14 min, so 1.5-2 hours for all 9.
backend\.venv\Scripts\python scripts\build_map.py        # AI enrichment of the map
backend\.venv\Scripts\python scripts\precompute_crs.py   # impact analysis of the 9 demo CRs

# 5. Optional: connect Jira (section 8b). Copy .env.example to .env and fill it in.

# 6. Start
cd backend;  .venv\Scripts\python -m uvicorn app.main:app --port 8000     # terminal 1
cd frontend; npm run dev                                                   # terminal 2
# open http://localhost:5173

# Tests (20: map accuracy, impact rules, AI verifier, Jira parsing, AI answers vs answer key)
cd backend; .venv\Scripts\python -m pytest -q

# Before a demo take: sync Jira, clear edits/comments, put BOA-9 back in "To analyse"
backend\.venv\Scripts\python scripts\reset_demo.py
```

Without step 4 everything still works. The map shows code facts only, and impact analysis runs live when you click **Analyse impact**, using the faster 3B model (several minutes on a CPU laptop, with weaker results than 7B). If Ollama is stopped, the app falls back to rule-based results and says so.

---

## 3. Architecture overview

```
 Bank of Anthos repo (REAL code)   Catalog YAML (SYNTHETIC)      Jira CRs (JSON, written by us)
   │                                  │                               │
   ▼                                  │                               │
 ┌──────────── MAP BUILDER  backend/app/mapbuild ─────────────┐        │
 │ 1 Inventory      k8s.py         services + databases        │        │
 │ 2 Code facts     python_extract.py · java_extract.py        │        │
 │ 3 Config/schema  k8s.py · schema.py                         │        │
 │ 4 Join links     build.py   calls→APIs, DB, tokens, catalog │        │
 │ 5 AI enrich      enrich.py  resolve · describe · journeys   │        │
 │ 6 Check          mapcheck.py   vs answer key (49/49)        │        │
 └─────────────────────────────────────────────────────────────┘        │
              │ ProjectMap: nodes + links + evidence                    │
              ▼                                                         ▼
 ┌──────────── IMPACT ANALYZER  backend/app/engine/impact.py ──────────────┐
 │ 1 Understand (AI) → 2 Entry points (glossary + names + AI + embeddings)  │
 │ → 3 Blast radius (map) → 4 Judge (AI) → 5 Assess (rules + AI) → 6 Verify │
 └──────────────────────────────────────────────────────────────────────────┘
              │                         ▲
              ▼                         │  llm/: ollama_client (local model) · prompts · service (cache) · verify
   FastAPI  backend/app/main.py ──► React UI  frontend/src: Board · Impact page · Dependency Map
```

### Folders and files

| Path | What it does |
|---|---|
| `demo_data/project.yaml` | Which repo we analyse, the pinned commit, excluded folders |
| `demo_data/catalog/*.yaml` | Knowledge that isn't in the code (owners, outside systems, data labels, approval rules, business words). **Synthetic** |
| `demo_data/jira/issues.json` | 9 plain-language change requests (Jira REST format) |
| `demo_data/map_truth.yaml` | **Answer key for the map**: 49 hand-checked facts |
| `demo_data/ground_truth.yaml` | **Answer key for impact**: what an engineer expects for each CR |
| `backend/app/mapbuild/` | Builds the dependency map (section 5) |
| `backend/app/engine/impact.py` | The 6-stage impact pipeline (section 6) |
| `backend/app/engine/graph.py` | "If X changes, what else is affected?" propagation rules |
| `backend/app/engine/embeddings.py` | Meaning-based search (local embedding model) |
| `backend/app/engine/cochange.py` | Learns which services change together from git history |
| `backend/app/engine/catalog.py` | Loads the catalog |
| `backend/app/engine/evaluate.py` | Scores impact analyses against the answer key |
| `backend/app/llm/` | Local AI client, prompts, cache, **verifier** |
| `backend/app/jira/` | Jira connector: REST client, rich-text conversion, issue parsing, sync, posting comments (section 8b) |
| `backend/app/store.py` | SQLite: cached AI answers, analyses, reviewer edits, audit trail |
| `backend/app/main.py` | The API used by the screens |
| `frontend/src/pages/` | `Board.tsx`, `ImpactPage.tsx`, `DependencyMap.tsx` (+ `mapLayout.ts`) |
| `scripts/` | `fetch_repo.ps1`, `build_map.py`, `precompute_crs.py`, `seed_jira.py`, `link_jira_keys.py`, `reset_demo.py` |
| `jira_sim/` | Optional local Jira-compatible tracker for offline demos (not Atlassian Jira) |
| `deferred/self_healing_docs/` | Parked Self-Healing Docs engine |
| `workspace/` | Downloaded repo, database, embedding cache (not committed) |

---

## 4. Demo project: Bank of Anthos

**What it is:** Google's open-source sample bank (Apache 2.0). Customers sign up, log in, see their balance, send money, deposit and see history. It's finance, but everyone understands it. In the app it's shown under the neutral name **Payments Platform**.
Source: <https://github.com/GoogleCloudPlatform/bank-of-anthos>, pinned at commit `db35fea` (release v0.6.11). The code isn't copied into this repo; `scripts/fetch_repo.ps1` downloads it into `workspace/`.

| Part | Language | Plain role |
|---|---|---|
| **frontend** | Python (Flask) | The website: login, sign-up, home, send money, deposit |
| **userservice** | Python | Creates accounts, checks passwords, **signs login tokens** |
| **contacts** | Python | Saved payees ("send money to Mum") |
| **ledgerwriter** | Java (Spring) | Checks and **records every payment / deposit** |
| **balancereader** | Java (Spring) | Gives the **balance** (fast cached copy) |
| **transactionhistory** | Java (Spring) | Gives **past transactions** (cached) |
| **accounts-db** | PostgreSQL | Tables `users` (11 columns, 8 personal/secret), `contacts` |
| **ledger-db** | PostgreSQL | Table `transactions` |

**Real vs synthetic:**

| REAL (read from the GitHub code) | SYNTHETIC (written by us for the demo) |
|---|---|
| Services, APIs, calls between services, databases, tables, columns, settings, tests, login-token signing/checking | Owner teams, outside systems (Regulatory Reporting, Finance General Ledger, Fraud Screening, CRM, SMS/Email provider), data labels (Personal/Financial/Secret), approval rules, Jira CRs |

In a real organisation, the synthetic parts would be **imported** from existing sources: the CMDB / application inventory, the interface catalogue, the data classification register and the change-management policies.

**Why Bank of Anthos:** it's a realistic multi-service finance application (Python and Java services, two databases, Kubernetes config) that needs no domain expertise, so the CRs stay simple while the pipeline stays realistic. The same pipeline runs on other Python/Java services deployed with Kubernetes; other stacks need new parsers (section 11).

---

## 5. The dependency map

### 5.1 What it contains (4 zoom levels)

| Level | Shows | Example |
|---|---|---|
| **L1 System** | services, databases, outside systems, the customer | frontend → ledgerwriter → ledger-db |
| **L2 Interfaces** | API endpoints, tables, settings | `POST /transactions`, table `transactions`, `BALANCES_API_ADDR` |
| **L3 Code** | functions, tests | `LedgerWriterController.addTransaction()` |
| **L4 Data** | columns with sensitivity labels | `users.ssn` (Personal, highly sensitive) |

Totals for Bank of Anthos: 6 services, 2 databases, 3 tables, 23 columns, 33 APIs, 29 settings, 136 functions, 74 tests, 5 outside systems, **348 links**.

**Link types:**

| Link | Meaning | Example |
|---|---|---|
| uses | the customer uses a service | Customer → frontend |
| calls | a service calls another service's API | frontend → ledgerwriter `POST /transactions` |
| reads / writes | a service reads or saves a table | ledgerwriter **writes** `transactions` |
| needs setting | a service needs a configuration value | ledgerwriter needs `BALANCES_API_ADDR` |
| trusts login tokens from | security dependency | balancereader trusts tokens from userservice |
| handled by | the code behind an API | `POST /transactions` → `addTransaction()` |
| calls (code) | a function calls another function | `addTransaction()` → `getAvailableBalance()` |
| tests | a test checks this code | `TransactionValidatorTest` → `validateTransaction()` |
| reads (outside system) | an outside system uses our data (catalog) | Regulatory Reporting reads `transactions` |

**Every link stores** its *origin* (`code` · `config` · `schema` · `catalog` · `ai` · `human`), a *confidence* (1.0 = exact) and *evidence* (exact file lines).

### 5.2 How it's built (6 steps)

**Step 1: Inventory** (`mapbuild/k8s.py`)
Reads every Kubernetes file in `kubernetes-manifests/`. A *Deployment* is a **service** and a *StatefulSet* or database image is a **database**. It also records the settings each one receives (ConfigMaps).
Result: **6 services, 2 databases**.

**Step 2: Read the code**
- **Python** (`python_extract.py`, Python's own parser `ast`):
  - routes: `@app.route('/payment', methods=['POST'])`
  - settings: `os.environ.get('X')`
  - **two-step URL wiring** (the frontend's style): first `app.config["TRANSACTIONS_URI"] = 'http://{}/transactions'.format(os.environ.get('TRANSACTIONS_API_ADDR'))`, then `requests.post(url=app.config["TRANSACTIONS_URI"])`. The extractor follows both steps, including local variables and f-strings.
  - database: `Table("users", ...)` then `self.users_table.insert()` = write, `.select()` = read
  - login tokens: `jwt.encode` = signs, `jwt.decode` = checks
  - tests: `test_*` functions and the URLs or functions they exercise
  - **call order**: the line of every call, so journeys are in real order
- **Java** (`java_extract.py`, the **tree-sitter** parser):
  - routes: `@PostMapping("/transactions")`
  - settings: `@Value("${LOCAL_ROUTING_NUM}")`
  - **URL wiring**: `@Value("http://${BALANCES_API_ADDR}/balances") String balancesApiUri`, then `String uri = balancesApiUri + "/" + fromAcct`, then `restTemplate.exchange(uri, HttpMethod.GET, …)`
  - database: `@Entity @Table(name="TRANSACTIONS")` + repositories; `save()` = write, `@Query("SELECT…")` = read
  - tests: `@Test` methods and the methods they call

**Step 3: Config and schema** (`k8s.py`, `schema.py`)
- `BALANCES_API_ADDR: "balancereader:8080"` **points to the balancereader service**.
- `ACCOUNTS_DB_URI: postgresql://…@accounts-db:5432/…` **points to the accounts-db database**.
- `CREATE TABLE users (…)` gives **tables and columns**.

**Step 4: Join the dots** (`build.py`)
- *call + setting + endpoint*: the frontend calls `<TRANSACTIONS_API_ADDR>/transactions` (POST); the setting points to ledgerwriter; ledgerwriter offers `POST /transactions`. So the link is **frontend → ledgerwriter `POST /transactions`**. Its evidence is the call line, the config line and the endpoint code.
- *table use + database setting*: userservice writes `users` and connects to accounts-db, so **userservice writes accounts-db.users**.
- *tokens*: userservice signs; 5 services verify, so each **trusts login tokens from userservice**.
- *catalog*: owners, capability and outside systems are attached.

**Step 5: AI enrichment** (`enrich.py`, run once by `scripts/build_map.py` with qwen2.5:7b, cached). The **AI proposes and code verifies**; only verified results are applied.

| AI task | What it did on Bank of Anthos | How it's checked |
|---|---|---|
| **Resolve unclear calls** | The frontend home page calls contacts through a helper class (`ApiRequest` → `ApiCall.make_call`) that hides GET/POST, and contacts offers both. The AI read `api_call.py` and chose **GET /contacts/{username}**, quoting `get(url=self.api_request.url`. It also classed 4 other calls as *not internal* (cloud metadata server, browser login callback, generic helper). | The answer must be one of the code-derived candidates, and the quote must appear word-for-word in the code. The link is drawn dashed as "AI-resolved". |
| **Plain-English descriptions** | 6 services, 18 business APIs, 3 tables | Only for IDs that exist in the map; anything else is dropped |
| **Business labels on links** | e.g. ledgerwriter → balancereader: *"Checks there is enough money before paying"* | Only for existing links |
| **Customer journeys** | Named and narrated *View home*, *Make a payment*, *Deposit money*, *Log in*, *Sign up* | The **steps are computed by code** from verified links in real call order. The AI only names and words them; if its step count differs, its wording is ignored. |
| **Sensitive-data suggestions** | Suggested `users.accountid` may be Personal | Shown as **"AI suggests"**, never as fact, until the data register confirms |

**Step 6: Accuracy check** (`mapcheck.py` vs `demo_data/map_truth.yaml`). See section 10.

### 5.3 The map screen (how to read and use it)
- **4 views:**
  - **System** (default): services, databases, outside systems, left to right like a story
  - **Services & APIs**: each service box lists its APIs; links show which API each service calls and which tables it uses
  - **Data**: tables, sensitive columns (red = personal/secret data), and who reads or writes them, including outside systems
  - **Customer journeys**: pick a journey and the map shows its numbered steps; the side panel explains each step
- **Hover:** focuses on the part and its neighbours, with a plain-English description.
- **Click:** a details panel lists the APIs it offers, what it calls, who calls it, data, settings, token trust, code and tests. Every row has a **proof** button showing the exact code or config.
- **What if this changes?** Lights up everything that depends on the selected part (red strong, orange medium, yellow weak) and explains why.
- **Show impact of a change request:** colours the map by a CR's analysis (must change / likely affected / re-test / not impacted).
- **Also:** search, outside-systems and login-token toggles, health-endpoint toggle, legend, double-click a service to open its APIs.

---

## 6. Impact analysis of a Jira CR (the core feature)

### 6.1 What "impact analysis" means here
Before a CR is built, each role asks different questions. The report answers all of them in one place:

| Role | Their question | Where it's answered |
|---|---|---|
| Business Analyst | What does it really mean? What's unclear? Which other teams are affected? | *What the request means*, *Open questions*, *Outside systems* |
| Product Owner | What will customers notice? How big is it? | *Business* card, *Size* |
| Lead Engineer / Developer | Which parts must change, and how? Which APIs change for other teams? | *What changes, and how*, API contract warning |
| Tester | What to re-test? Where are the gaps? What new tests are needed? | *Testing* |
| Risk / Compliance | Personal data? Regulators? Which approvals? | *Data*, *Approvals needed* |

### 6.2 The 6-stage pipeline (`engine/impact.py`)

| Stage | Done by | What happens | Example: BOA-9 "Collect the customer's phone number at sign-up" |
|---|---|---|---|
| **1 Understand** | AI | Reads the CR and returns change type, intent, business terms, parts likely to change, **new data** (with sensitivity), outside systems, **open questions**, assumptions. Names are checked against the map; unknown names are dropped. | new feature; new field `phone_number` (Personal) in `users`; likely parts: frontend, userservice, accounts-db; 3 open questions |
| **2 Entry points** | Rules + AI + embeddings | Where the change starts: (a) **glossary** words ("sign-up" → `POST /signup`, `POST /users`); (b) names in the text; (c) parts named by the AI; (d) **meaning-based search**: the CR text and 206 map items are turned into vectors by `nomic-embed-text`, and the closest are picked | glossary: `POST /signup`, `POST /users`, `users`; AI: frontend, userservice; meaning search: `signup()`, CRM, and some contact functions (`add_contact()`…), which is noise |
| **3 Blast radius** | Map | `propagate()` follows **verified links** with per-link weights ("if a table changes, its readers are affected", "if an API changes, its callers are affected"), weakening with each hop (max 3 hops, up to 24 candidates). Git history is checked for services that usually change together (see 6.4). | adds Regulatory Reporting and CRM (both read `users`), contacts (from the contact-function matches), and ledgerwriter, balancereader, transactionhistory (they trust userservice's login tokens) |
| **4 Judge** | AI | **One call** gets every candidate with why it's a candidate and the code of the APIs and tables involved. It decides *must change / likely affected / re-test only / not impacted* and **HOW** in one sentence. Rule: a service is at least as affected as its APIs. | **must change:** `users`, `POST /signup`, frontend; **likely:** `POST /users`, userservice; 13 re-test. "POST /signup must accept and process a new 'phone_number' field" |
| **5 Assess** | Rules | **Data:** sensitivity from the data register + new fields. **API contract changes:** a changing API that another service calls. **Outside systems:** owner and actions (notify, test interface, sign-off). **Approval rules** from the catalog. **Tests:** existing tests covering impacted APIs/code, and **gaps**. **People:** owners + approvers. **Risk:** points (below). | CTRL-PII (personal data), CTRL-REG (Regulatory Reporting reads `users`); 10 userservice tests to re-run; 2 gaps (`POST /signup`, frontend); risk High (12 points) |
| **5b Write** | AI | From the facts above: 2-3 sentence summary, business impact, 3-5 **test scenarios**, **T-shirt size** with reason, risks | Size M; "Test attempting to sign up without providing a phone number", "Test providing an invalid phone number format" |
| **6 Check + save** | Code | AI verdicts are kept only for real candidates with allowed values. Cited evidence IDs must exist. Inline evidence IDs are stripped. **Candidates the AI didn't answer get the rule-based verdict and are labelled "Rules".** The free text is AI-written and not checked line by line. | 2 of BOA-9's items were decided by rules |

**Risk points** (simple and adjustable): personal or secret data +3 · financial data +1 · each outside system +2 (max 4) · each approval rule +1 · test gaps +1 · API contract change +1 · open questions +1 · high-criticality part changes +1. **6+ = High, 3-5 = Medium, 0-2 = Low.** The reasons are always listed under "Why this risk level".

### 6.3 Human in the loop
On the Impact page a reviewer can:
- **change any verdict**, with the AI's original verdict kept and shown,
- **remove** an item from scope,
- **add to scope** anything from the map (search), with a reason.

Each edit is saved with name and time, shown with a **Reviewer** badge, and recorded in the audit trail. Edits are stored separately and laid over the saved analysis. The risk level, approvals and cards are **not** recalculated after an edit; only the Technical card's counts are.

### 6.4 Learning from git history (honest result)
`cochange.py` counts which services were changed in the same commits (only real source files, not dependency-update or build files). For Bank of Anthos, **only 1 of the last 600 commits changed source code**; the rest are dependency and version bumps. So there's **no reliable "changes together" signal**, and the app says so instead of inventing coupling. On a real bank repo with active development this signal becomes useful.

### 6.5 The report (Impact page)
1. **Header:** CR, priority, labels, **risk badge**, **size**, *Show on map*, *Re-run*
2. **Impact at a glance:** AI summary + **6 traffic-light cards**: Business · Technical · Data · Outside systems · Testing · Approvals
3. **What the request means:** intent, business terms, **questions to answer before development**, assumptions
4. **What changes, and how** (open): grouped by *Must change / Likely affected / Re-test only*. Each row has HOW, why it was found, source badge (AI / Rules / Reviewer), a verdict dropdown, **Why?** (dependency path + code proof) and remove
5. Accordions: **Data** · **Outside systems** (with notify/test/sign-off actions) · **Testing** (tests to re-run per service, gaps, AI test scenarios) · **Approvals needed** · **People to involve** · **How this analysis was worked out** (entry points and their sources, pipeline steps, models and timings)
6. Right column: **mini impact map** (only impacted parts, coloured by verdict) + **why this risk level**

---

## 7. The AI layer
- `llm/ollama_client.py`: calls the local Ollama server with a **JSON schema**, so answers always have the fixed structure.
- `llm/prompts.py`: one system prompt per task. All share the rule: *use only the evidence blocks, cite their IDs, quote exactly, never invent names, write plain English.*
- `llm/service.py`: builds **evidence packs** (labelled code snippets) and **caches** every answer, keyed by the task and the full prompt text (which includes the evidence). Modes: `cache` (never call), `auto` (use the cache or call), `force` (always call; the **Re-run** button). The model name is **not** part of the key, so answers pre-computed with 7B are reused by live runs. That's why **Analyse impact** on BOA-9 in the demo takes seconds.
- `llm/verify.py`: **code that checks the AI**:
  - cited evidence exists
  - quotes appear word-for-word (it corrects a quote cited against the wrong evidence block, but never rescues a forged citation)
  - targets exist in the map (this check is only used by the tests)
  - inline evidence IDs are stripped from prose
- **What is and isn't checked:** map links proposed by the AI must quote real code; impact verdicts must be for real candidates; cited IDs must exist. The judge isn't required to cite evidence, and the free text (summary, "how", test scenarios, size) isn't verified.
- **Models:** `qwen2.5:7b` for pre-computing demo results (quality); `qwen2.5:3b` for live runs (speed); `nomic-embed-text` for meaning-based search. On this CPU laptop, a full 7B analysis (3 AI calls) takes about 10-14 minutes; BOA-9 took 817 seconds.
- **Offline:** if Ollama is down, everything still renders from code facts and rules, labelled as such.

---

## 8. Data files
- `project.yaml`: repo, pinned commit, excluded folders (load generator, monolith variant), health endpoints hidden by default.
- `catalog/services.yaml`: owner team, business capability, criticality.
- `catalog/external.yaml`: outside systems and the tables they read.
- `catalog/data_classification.yaml`: labels on real columns.
- `catalog/controls.yaml`:
  - **CTRL-PII** personal data review
  - **CTRL-PAY** payments logic approval
  - **CTRL-API** API contract sign-off
  - **CTRL-REG** regulatory reporting review
  - **CTRL-VENDOR** new third-party integration
- `catalog/glossary.yaml`: business words → system parts. Words were chosen to avoid false matches, e.g. *"saved contact"*, not *"contact"*, which also means "phone the customer".
- `jira/issues.json`: CRs in Jira REST format. Fields used: summary, description, acceptance criteria, components, labels, priority, assignee, reporter. New CRs typed in the app (when Jira isn't connected) are saved to `workspace/new_crs.json`.

Demo keys are BOA-101…109. When the same CRs were created in the real Jira site, Jira numbered them BOA-5…13.

| Demo key | Jira key | Change request | What it shows |
|---|---|---|---|
| BOA-101 | BOA-5 | Daily limit: max $5,000 sent per day | Payments logic + reading transactions; payments approval |
| BOA-102 | BOA-6 | Show payee name in history | Data already on the page: frontend-only change, others re-test |
| BOA-103 | BOA-7 | Delete a saved contact | New API → contract change |
| BOA-104 | BOA-8 | Block payments to own account | Small, local validation change |
| BOA-105 | BOA-9 | Phone number at sign-up | **Personal data**, CRM + Regulatory Reporting, 2 approvals (privacy, regulatory reporting) |
| BOA-106 | BOA-10 | Download history as CSV | Read-only, low risk |
| BOA-107 | BOA-11 | SMS when balance < $100 | **New outside vendor**; also needs a phone number that doesn't exist yet |
| BOA-108 | BOA-12 | "Make the balance show faster" | **Vague**, so the AI raises open questions |
| BOA-109 | BOA-13 | Minimum deposit $10 | Small payments rule |

## 8b. Jira connection
- **Connector** (`backend/app/jira/`): Jira REST API v3. `client.py` handles search (`/rest/api/3/search/jql`), get issue, create issue and add comment. `adf.py` converts Jira rich text (ADF) to plain text and back. `parse.py` turns an issue into the analyzer's format; acceptance criteria come from a custom field (`JIRA_AC_FIELD`) or an "Acceptance criteria" heading in the description. `sync.py` handles sync, status, add-to-active-sprint and **publish** (impact summary posted as a Jira comment).
- **Settings** in `.env` (never committed; see `.env.example`): `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_JQL`, optional `JIRA_AC_FIELD`. Without them, the app uses `demo_data/jira/issues.json`.
- **Real Jira Cloud** (used for the demo): free site, space key `BOA`, work type *Change Request*. `scripts/seed_jira.py` creates the 9 demo CRs (and adds them to the active sprint); `scripts/link_jira_keys.py` reuses existing analyses for Jira's new keys (BOA-5…13) by matching titles.
- **Local demo tracker** (`jira_sim/`, port 8090): a small tracker with a board, issues and comments that speaks the same API. Useful offline; not Atlassian Jira.
- **In the UI:** *Connected to Jira* bar and **Sync from Jira** (board), **Jira** links on cards, **Open in Jira** / **Post summary to Jira** (Impact page). **New change request** creates the ticket in Jira.

## 9. UI walkthrough (3 screens)
> **Full element-by-element walkthrough: [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md). Demo video narration: [DEMO_VIDEO_SCRIPT.md](DEMO_VIDEO_SCRIPT.md).**

1. **Change Requests (board):** Jira-like columns *To analyse / Analysing / Analysed*. Cards show risk, number of parts that must change, outside systems, approvals, open questions and size. **New change request** lets you type a CR in plain English, and analysis starts right away. While analysing, the card shows the live step (1-6).
2. **Impact Analysis page:** see 6.5.
3. **Dependency Map:** see 5.3.

The header always shows: local AI status, analysed project and commit, and **map accuracy against the answer key**.

## 10. Testing and accuracy
Run `cd backend; .venv\Scripts\python -m pytest -q`:
20 tests in total:
- `test_map.py` (5): map vs answer key; every link has proof; config wiring exact
- `test_impact.py` (5):
  - rule-based stages (no AI): payments rule for BOA-101; personal data, privacy rule, CRM and High risk for BOA-105; new vendor for BOA-107; every candidate is a real map node with a reason
  - **cached AI analyses scored against `ground_truth.yaml`** (needs the local database, so it's skipped on a fresh checkout)
- `test_verify.py` (7): the AI checker rejects forged evidence and made-up quotes
- `test_jira.py` (3): Jira rich text and acceptance-criteria parsing

**Map accuracy:**

| Category | Expected | Code + config only | After AI step | Wrong links |
|---|---|---|---|---|
| Services / databases / tables | 6 / 2 / 3 | 6 / 2 / 3 | 6 / 2 / 3 | 0 |
| Business endpoints | 18 | 18 | 18 | 0 |
| Service → API calls | 8 | 7 | **8** | 0 |
| Table reads/writes | 7 | 7 | 7 | 0 |
| Token trust | 5 | 5 | 5 | 0 |
| **Overall** | **49** | **48 (98%)** | **49 (100%)** | **0** |

**Impact accuracy** (qwen2.5:7b analyses of all 9 CRs vs `ground_truth.yaml`, via `GET /api/eval`; final version with stricter prompts and tuned rules):

| Measure | Result | Meaning |
|---|---|---|
| Involved parts found (must change or likely affected) | **100%** | Nothing that should be on the radar was missed |
| Approval rules that should fire | **100%** | |
| Outside systems that should be flagged | **100%** | and none flagged wrongly on read-only or validation-only changes |
| Wrongly marked "must change" (from the "not" lists) | **0** | |
| "Must change" placed on the expected part | **67%** | The AI sometimes puts the main change in a different (also valid) service, e.g. `transactionhistory` instead of `frontend` for BOA-102/106, and `frontend` as *likely* for BOA-103. A reviewer fixes it with one click |
| Risk level | realistic | **High** only for BOA-105 (personal data + CRM + regulator) and BOA-107 (new SMS vendor); payment-rule CRs **Medium**; vague BOA-108 **Low** with 3 open questions |

**Read these numbers with care:** both answer keys were written by us, the sample is small (9 CRs, 49 map facts), and the rules below were tuned on the same 9 CRs. Only the "likely affected" recall and the "not" lists are measured, so the precision of the re-test lists isn't. Treat this as a sanity check, not a benchmark.

**How over-caution was reduced** (first run: every payment change was "High"):
1. **Stricter judge prompt:** smallest correct set; a table only "must change" if its columns or stored data change; outside systems only if the data they receive changes. Average "must change" items per CR fell from 3.4 to 2.4.
2. **Outside-system rule:** affected only if a table they read gains fields or itself must change.
3. **Data rules** (e.g. personal data) only for tables that actually change.
4. **API-contract rule:** an internal logic change does not change a service's API; only changing endpoints, or new features/integrations wired between services, count.
5. The previous run is kept in `workspace/analyses_backup_v1.json` for comparison (local only, not in the repo).

## 11. Limits and adapting to a real bank
- **Languages:** Python and Java are supported now. Others need an extractor that produces the same `ServiceFacts` (tree-sitter has grammars for most languages).
- **Wiring styles:** HTTP via settings (Kubernetes ConfigMaps) is exact. Messaging (Kafka/MQ topics), stored procedures and batch jobs need extra patterns.
- **Many repos:** run the builder per repo and merge the maps; links join on API paths, settings, tables and topics. The external-systems catalog becomes the bridge to systems you don't own.
- **Catalog:** import it from real registers instead of hand-written YAML.
- **CPU speed:** a 7B model on a laptop takes minutes per answer; a GPU or server makes live analysis take seconds.
- **The AI can be wrong:** it only judges real candidates, its structured answers are checked, the source of every verdict is shown, and a reviewer can override anything.

**Known issues (honest list):**
- **Results can vary between runs.** The ticket key is part of the prompt, so the same CR analysed under BOA-105 and BOA-9 got slightly different verdicts (e.g. userservice *must change* vs *likely affected*).
- **The re-test list is broad.** Services that only trust userservice's login tokens, and parts found by loose meaning matches (e.g. contact functions for the phone-number CR), show up as "re-test".
- **Outside systems marked "re-test only" still count as affected:** they add risk points and can trigger approvals (that's how CRM and Regulatory Reporting appear on BOA-9).
- **Some "must change" verdicts can come from the rule fallback** when the AI skips a candidate; they're badged "Rules".
- **Wording can be inconsistent:** an item marked "must change" may have a "how" sentence starting "May need to…".
- **Not production-ready:** no login, the API accepts requests from any origin, jobs run in one process (lost on restart), scripts are Windows/PowerShell, and the Jira token is stored in plain text in `.env`.
- **Placeholders and leftovers:** the backend still records "Priya Nair" for Jira sync/comment audit entries and as the default reviewer name; `engine/controls.py` and `engine/gitrepo.py` are unused leftovers from the first version; `networkx` is listed in `requirements.txt` but unused.
- **New CRs** are created in Jira with the issue type "Change Request", which fails if a project doesn't have that type.

## 12. Change log

| Step | What was done |
|---|---|
| v1 (earlier) | First prototype on a fake bank (NovaBank) with Impact, Release Readiness and Doc Health screens. Found too broad and cluttered. |
| Re-plan | Focus on Impact Analysis + Dependency Map; Bank of Anthos; Release Readiness removed; Self-Healing Docs parked |
| Chunk 1: Purge | Removed Release Readiness, Doc Health, NovaBank data and old tests; parked `docdrift.py` |
| Chunk 2: Demo data | Pinned Bank of Anthos (`db35fea`), catalog, 9 CRs, map answer key |
| Chunk 3: Map builder | Kubernetes, Python (ast) and Java (tree-sitter) extractors, schema reader, link joining, accuracy check: **48/49, 0 wrong links** |
| Chunk 4: Map screen | Cytoscape map: System / Services & APIs / Data / Journeys views, hover, details panel with proof, what-if, search, legend |
| Chunk 5: AI enrichment | Resolve unclear calls (closed the last link: **49/49**), descriptions, business labels, journeys in real call order, sensitivity suggestions. 7B run: 21 min, cached |
| Chunk 6: Search + history | Embeddings (nomic-embed-text, 206 items), git co-change (honest: no signal in this repo) |
| Chunk 7: Impact pipeline | 6 stages, evidence-checked AI, rule fallbacks, risk points, API contract detection, tests/gaps, people, cards; background jobs with live progress |
| Chunk 8-9: Board + Impact page | Jira-like board, new CR dialog, impact report (summary first), reviewer edits and add to scope, mini impact map |
| Chunk 10: Overlay | CR impact overlay on the full map |
| Chunk 12: Screens + Jira | Screen fixes (mini map, journey steps from verified links, AI-time footer); stricter judge prompt; Jira connector, demo tracker, real Jira Cloud (9 CRs seeded, sprint, comments posted back); DEMO_WALKTHROUGH.md |
| Chunk 11: Precompute + tuning | All 9 CRs analysed with 7B (~10 min each). Rules tuned: outside systems only when their data changes; data rules only for changing tables (AI), cautious for rule fallback; board shows jobs from any process. **Scores: 100% involved parts, 100% approvals, 100% outside systems, 0 wrong "must change"** |
| Chunk 13: Demo prep | Neutral name **Payments Platform** in the app, demo user, `reset_demo.py` (puts BOA-9 back in *To analyse* with its AI answers cached), final narration in `DEMO_VIDEO_SCRIPT.md`; BOA-9 re-analysed with 7B under its own Jira key (817 s) |
| Docs refresh | Guides updated to match the app (current BOA-9 numbers, timings, what the verifier does and doesn't check, known issues); `.gitignore` hardened for secrets before publishing to GitHub |
