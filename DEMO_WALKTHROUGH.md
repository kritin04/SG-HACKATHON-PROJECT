# Change Impact Copilot: App Walkthrough

> **Who this is for:** anyone who wants to understand every screen of the app, and whoever presents or records the demo.
> **The demo video narration** is in [DEMO_VIDEO_SCRIPT.md](DEMO_VIDEO_SCRIPT.md) (section 3 below lists its scene order).

---

## 0. The story in 30 seconds

> *"Before anyone writes code, a team has to know what a change will affect: which systems, which data, which teams, which approvals. Today that takes several people hours or days of manual digging. The Change Impact Copilot does it in minutes. It reads the Jira ticket, follows a verified map of the real code, uses a local AI to judge what changes and how, and posts the answer back into Jira, with the code behind every item. The AI runs on the laptop: no code or data is sent to an AI provider."*

**Three ideas to repeat:**
1. **Before coding**: impact is known at the cheapest moment.
2. **Proof, not guesses**: every item links to the exact lines of code or config it's based on.
3. **Private AI**: the models run on the laptop. The only internet traffic is to Jira (tickets in, summary comment out).

---

## 1. How a ticket flows through the system (big picture)

```
 ┌──────────────┐  1. Ticket written   ┌───────────────────────────┐
 │  Jira Cloud  │ ───────────────────► │  Change Impact Copilot    │
 │ (BOA space)  │  2. "Sync from Jira" │  (runs on this laptop)    │
 │              │ ◄─────────────────── │                           │
 │  ticket gets │  6. "Post summary    │  3. Analyse impact        │
 │  an AI       │     to Jira"         │     (6 steps, local AI)   │
 │  comment     │                      │  4. Show report + map     │
 └──────────────┘                      │  5. Reviewer adjusts      │
                                       └───────────┬───────────────┘
                                                   │ reads
                                   ┌───────────────┴────────────────┐
                                   │ Dependency map of the REAL code │
                                   │ (open-source, 49/49 accurate)   │
                                   └─────────────────────────────────┘
```

| Step | Where | What happens | Who sees it |
|---|---|---|---|
| **1. Ticket written** | Jira | A BA or product owner writes a change request in plain English, e.g. *"Collect the customer's phone number at sign-up"*, with acceptance criteria | Everyone in Jira |
| **2. Sync** | Copilot board → **Sync from Jira** | The copilot reads all *Change Request* items from the Jira space through Jira's official REST API. Descriptions are converted from Jira's rich-text format, and acceptance criteria are picked out | Copilot board |
| **3. Analyse** | Copilot card → **Analyse impact** | 6 steps run in the background (card moves to *Analysing*, shows "Step 4/6…"): **understand** the request (AI) → **find where it starts** in the code → **follow the dependency map** → **judge** each part (AI) → **check** data, outside systems, approval rules and tests (rules) → **write** the summary (AI) | Copilot board, live |
| **4. Report** | Copilot Impact page | Risk, size, what must change and **how**, open questions for the BA, data sensitivity, outside systems, approvals, tests, people to involve, and a picture of the impact on the map | Lead engineer, BA, tester, risk |
| **5. Review** | Copilot Impact page | A person can change any verdict, remove items or add missing ones. Each edit is badged "Reviewer" and logged | Reviewer |
| **6. Post back** | Copilot → **Post summary to Jira** | A short impact summary is added as a **comment on the Jira ticket**, with a link back to the full analysis | Everyone in Jira |

**What's real and what's demo data** (say it honestly if asked):
- **Real:** the code we analyse (Google's open-source *Bank of Anthos*, shown in the app as **Payments Platform**), the map built from it, the Jira Cloud site, the local AI models.
- **Demo:** the 9 change requests, team owners, outside systems (Regulatory Reporting, CRM…), data-sensitivity labels and approval rules. In a real organisation these would come from existing registers.

---

## 2. The screens, element by element

The app has **3 screens**, all reached from the dark sidebar on the left.

### 2.1 Always visible: the frame

| Element | Where | What it means |
|---|---|---|
| **Change Impact Copilot** logo | top-left | App name |
| **Change Requests** (Jira board + impact) | sidebar | Screen 1: the board |
| **Dependency Map** (How everything connects) | sidebar | Screen 3: the map |
| *"AI runs locally. No data leaves this machine."* | sidebar bottom | The privacy promise. True for the AI; Jira Cloud is still reached over the internet |
| *"Analysing Payments Platform (open-source)"* | sidebar bottom | Which codebase is analysed (Google's Bank of Anthos) |
| 🟢 **Local AI ready** | top bar | The AI engine (Ollama) is running on the laptop. Red = offline; the app then falls back to rule-based results |
| **Payments Platform @ db35fea (release/v0.6.11)** | top bar | The exact version of the code that was analysed |
| ✅ **Map accuracy 49/49 · 100% precise** | top bar | The map was checked against a hand-made answer key (written by us): all 49 facts right, no wrong links |
| **Kritin Goyal · Lead Engineer** | top-right | The demo user (shown on reviewer edits) |

---

### 2.2 Screen 1: Change Requests (the board)

**Purpose:** the inbox of change requests from Jira, and where analysis starts.

**Header**
- **"Jira · Payments Platform / Change requests"** and one line explaining the screen.
- **+ New change request**: opens a form (title, description, acceptance criteria, priority). **Create and analyse** creates the ticket **in Jira**, adds it to the active sprint, syncs it back, and starts the analysis immediately.

**Jira connection bar**

| Element | Meaning |
|---|---|
| 🔗 **Connected to Jira** + green dot | The copilot can reach your Jira Cloud site |
| `https://…atlassian.net · project = BOA AND issuetype = "Change Request" … · 9 issue(s) · last sync … · as kritin goyal` | Which site, which tickets (a Jira query), how many, when last synced, and as whom |
| **Open Jira ↗** | Opens your Jira site |
| **Sync from Jira** | Pulls the latest tickets now (a message shows "Synced 9 issue(s)") |

**Three columns**

| Column | Holds |
|---|---|
| **To analyse** | Tickets with no analysis yet. Each card has **✨ Analyse impact** |
| **Analysing** | Tickets the local AI is working on. Shows **Step n/6 · what it's doing** live |
| **Analysed** | Tickets with a finished report |

**A card in "Analysed"**

| Element | Meaning |
|---|---|
| **BOA-9** | Jira key |
| **High risk** (red / amber / green) | Overall risk from the analysis |
| **High** | Jira priority (from the ticket) |
| Title | Ticket summary |
| ⚠ **3 must change** | Number of parts that must be edited |
| **2 outside system(s)** | Systems outside our code that are affected |
| **2 approval(s)** | Company rules that require sign-off |
| ? **3 open question(s)** | Things the BA must clarify |
| **Size M** | T-shirt size of the work (S / M / L / XL) |
| 👤 assignee · **Jira** link | Who owns it, and a link to the real ticket |
| **Open analysis →** | Opens Screen 2 |

---

### 2.3 Screen 2: Impact Analysis (one ticket)

**Purpose:** everything every role needs to know about one change, **summary first, details on demand**.

#### Header
| Element | Meaning |
|---|---|
| **← Change requests** | Back to the board |
| **BOA-9 · High priority · labels** | From Jira |
| Title + description | From Jira |
| **High risk** · **Size M** | The result |
| **Open in Jira ↗** | The real ticket |
| **Post summary to Jira** (then "Posted to Jira 19:06 · post again") | Writes the summary as a Jira comment |
| **Show on map** | Opens the map coloured by this ticket's impact |
| **↻ Re-run** | Runs the analysis again |

*If the ticket isn't analysed yet:* a panel says **"No impact analysis yet"** with **Run impact analysis**. While running, it shows the 6 steps with ticks and a spinner, plus elapsed time.

#### "Impact at a glance" (top card)
- A **2-3 sentence summary** written by the local AI *from verified facts* (the note on the right says so).
- **6 traffic-light cards** (🔴 needs attention, 🟠 caution, 🟢 fine). Click any card to jump to its section:

| Card | Answers | Example (BOA-9) |
|---|---|---|
| **Business** | What changes for customers or the business? | "This change will enhance customer data completeness but requires careful handling to protect sensitive information…" |
| **Technical** | How many parts change? Any API changes? | "3 must change · 2 likely affected · 13 re-test" |
| **Data** | Is sensitive data involved? | "Personal, Personal (highly sensitive), Secret data · 2 table(s) involved" |
| **Outside systems** | Which systems we don't own are affected? | "Customer Relationship Management (CRM), Regulatory Reporting" |
| **Testing** | Tests to re-run, gaps, new test ideas | "10 existing tests to re-run · 2 gap(s) · 5 new scenarios suggested" |
| **Approvals** | Which company rules apply? | "CTRL-PII Personal data change review, CTRL-REG Regulatory reporting impact review" |

#### "What the request means"
- **Change type + intent** in one line (AI), e.g. *"New feature: Collect and store customer phone numbers during sign-up."*
- **Business terms** as chips.
- 🟨 **Questions to answer before development**: what's unclear in the ticket (AI). *This is what a BA normally discovers late.*
- **Assumptions made**: what the AI had to assume.

#### "What changes, and how" (open by default)
Grouped into **🔴 Must change**, **🟠 Likely affected** and **🟡 Re-test only**. Each row:

| Element | Meaning |
|---|---|
| Icon (⬢ service, ⇄ API, ▤ table, ◇ outside system) | What kind of part |
| **Name** · *in service* · type | e.g. **POST /signup** *in frontend* API |
| Badge **AI** / **Rules** / **Reviewer** | Who decided: the local AI, the rule-based fallback (used when the AI didn't answer for that item), or a person |
| *(AI said: …)* | Shown when a reviewer changed the AI's verdict |
| **How** sentence | *How* it's affected, written by the AI, e.g. "POST /signup must accept and process a new 'phone_number' field" |
| *Found because:* | Why it was considered, e.g. "Business word 'sign-up' (glossary)" or "CRM reads users" |
| **Verdict dropdown** | Change the verdict (saved as a reviewer edit) |
| **Why?** | Opens the **proof drawer** (below) |
| **×** | Remove from scope |

Under the list:
- **+ Add to scope**: search any service, API, table or outside system, pick a verdict, give a reason.
- **Show checked but not impacted (n)**: what was considered and ruled out (transparency).
- ⚠ **API contract change**: shown only when an API that another service calls will change (BOA-9 has none).

#### Collapsible sections
| Section | Shows |
|---|---|
| **Data** | Each table involved: sensitivity labels (🔒 Personal / Financial / Secret), who writes and reads it, **new fields** (e.g. "New field phone_number · Personal data") |
| **Outside systems** | Each outside system: owner, what it does, how it's affected, and actions: ✓ Notify the owner · ✓ Test the interface · ✓ Get sign-off |
| **Testing** | **Existing automated tests to re-run**, per service (expand to see test names) · **Test gaps** (parts that change but have no test) · **Suggested new test scenarios** (AI) |
| **Approvals needed** | Each triggered rule (e.g. CTRL-PII), **why** it triggered, and **who must approve** |
| **People to involve** | Owner teams and approvers, with the reason for each |
| **How this analysis was worked out** | Where the change starts (entry points) and how each was found (glossary word, name in text, AI, meaning-based search) · the pipeline steps with model and time · a note on git history · *"The AI can only judge candidates from the verified map; it cannot invent new ones."* |

#### Right column
- **Impact on the system**: a small map showing only the impacted parts, coloured by verdict, with a legend and **Open full map →**.
- **Why this risk level**: the exact reasons that added risk points (personal data, outside systems, approvals, test gaps, API change, open questions, high-criticality parts), the **size reason**, and *analysed at commit · model · local AI time*.

#### The proof drawer ("Why?" / "Show proof")
Slides in from the right:
- **"Why is this here?"** + title + source badge (Auto-detected / From catalog / Human-confirmed).
- **Reason** in a blue box.
- **Dependency path**: the chain followed on the map, e.g. `Customer Relationship Management (CRM) → reads (outside system) → users`. Links that came from the catalog or the AI are badged.
- **Evidence (n)**: each piece of proof with a type badge (**Code**, **Configuration**, **Database schema**, **Jira**, **Curated catalog**…), its **file:line @ commit**, an ID, and the **actual code with line numbers**.

---

### 2.4 Screen 3: Dependency Map

**Purpose:** see how the whole system fits together, and what a change touches.

#### Toolbar
| Element | Meaning |
|---|---|
| **System / Services & APIs / Data / Customer journeys** | The 4 views (below) |
| ☑ **Outside systems** | Show or hide systems we don't own |
| ☐ **Login-token links** | Show which services trust login tokens from userservice (security dependency) |
| ☐ **Health endpoints** (APIs view) | Show technical status endpoints (hidden by default to reduce noise) |
| **Show impact of a change request…** | Colour the map by a ticket's analysis |
| 🔍 **Find a service, API, table…** | Search; zooms to the match |

#### The 4 views
| View | What you see | Best for |
|---|---|---|
| **System** | Left to right like a story: **Customer → website (frontend) → 5 services → 2 databases → 5 outside systems**. Labels on links explain *why*, e.g. "checks there is enough money before paying" | Managers: the whole system on one slide |
| **Services & APIs** | Each service as a box listing its APIs; arrows show which API each service calls; databases show their tables | Developers: exact API dependencies |
| **Data** | Databases and tables; **red tables hold personal or secret data** ("🔒 8 personal / secret"); who reads and writes each table, including outside systems | Risk and compliance |
| **Customer journeys** | Pick **View home / Make a payment / Deposit money / Log in / Sign up**; the path lights up with **numbered steps**, and the panel lists each step in plain words | Everyone: "what happens when a customer pays?" |

#### Shapes and colours (legend, bottom-left)
- **Blue rounded box** = service · **Amber cylinder** = database · **Purple dashed box** = outside system · **Red box** = sensitive data.
- **Blue line** = calls API · **Green** = reads · **Orange** = writes · **Teal** = reads & writes · **Purple dashed** = an outside system reads our data · **Grey dashed** = link resolved by AI (and verified).

#### Interactions
| Action | Result |
|---|---|
| **Hover** a box | Everything unrelated fades; a tooltip gives a plain-English description |
| **Hover** a line | "frontend calls ledgerwriter" + why + where the fact came from |
| **Click** a box | Details panel: description (AI-written from the code), owner, business area, criticality; **APIs it offers**, **Calls**, **Called by**, **Data**, **Used by**, **Settings it needs**, **Trusts login tokens from**, **Code & tests**. Every row has **proof** |
| **Click** a line | How we know it (e.g. the setting that wires it), confidence, **Show proof** |
| **Double-click** a service | Jumps to Services & APIs |
| **What if this changes?** (in the panel) | Everything that depends on that part lights up 🔴 strong · 🟠 medium · 🟡 weak, and the panel lists affected services, APIs, tables, outside systems and tests to re-run, each with *why?* |
| **Show impact of a change request** | Boxes coloured 🔴 must change · 🟠 likely · 🟡 re-test · faded = not impacted; hover shows *how* |

---

### 2.5 Jira Cloud (what you show there)
- **Board** (BOA space): the Change Requests in **To Do**.
- **A ticket**: description, **Acceptance criteria**, details (type *Change Request*, priority, labels).
- **Comments**: the copilot's comment: *"Impact analysis by Change Impact Copilot…"*, risk, must change, outside systems, approvals, tests, open questions, and **a link back to the full analysis**.

---

## 3. Demo video

The narration is in **[DEMO_VIDEO_SCRIPT.md](DEMO_VIDEO_SCRIPT.md)** (plain-text copy: `DEMO_VIDEO_SCRIPT.txt`). It shows the screens in this order:

1. Jira board, then open **BOA-9** "Collect the customer's phone number at sign-up"
2. Copilot board → **Sync from Jira**
3. **Analyse impact** on BOA-9 (takes seconds, because its AI answers are cached; see the checklist)
4. Open the analysis: risk, size and the 6 cards
5. **Questions to answer before development**
6. **Must change**: users, POST /signup, frontend
7. **Why?** on POST /signup (the code behind it)
8. Change **userservice** from Likely affected to Must change (the Reviewer badge appears)
9. **Show on map**, then the **Data** view
10. **System** view → select **ledgerwriter** → **What if this changes?**
11. **Customer journeys** → Make a payment
12. Board: **BOA-8** (Medium risk), then open **BOA-12** "Make the balance show faster" (Low risk, with questions)
13. BOA-9 → **Post summary to Jira**, then show the comment in Jira

---

## 4. Before you record: checklist

1. **Start everything:**
   ```powershell
   # Ollama is already running as a Windows app (check the tray icon)
   cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000
   cd frontend; npm run dev                         # http://localhost:5173
   ```
2. **Reset the demo before every take:**
   ```powershell
   backend\.venv\Scripts\python scripts\reset_demo.py
   ```
   It syncs from Jira, clears reviewer edits and the copilot's Jira comments, and puts **BOA-9** back in *To analyse*. It also checks that BOA-9's AI answers are cached, so clicking **Analyse impact** on camera finishes in seconds. Then refresh both browser tabs.
3. **Jira:** logged in, the BOA board shows BOA-5…13 in *To Do*.
4. **Copilot board:** every ticket in **Analysed** except BOA-9 in **To analyse**.
5. **Browser:** zoom 100–110%, full-screen (F11), close other tabs, hide bookmarks (Ctrl+Shift+B).
6. **Resolution:** 1920×1080; the map views fit best there.
7. **Avoid live AI waits:** a fresh 7B analysis takes about 14 minutes on this laptop (BOA-9 took 817 seconds). Only use tickets whose AI answers are cached.

---

## 5. Questions judges may ask (short answers)

| Question | Answer |
|---|---|
| *Is the AI making things up?* | It can only judge parts found in the **verified map**; names that aren't on the map are dropped. Cited evidence IDs are checked, and anything the AI doesn't answer gets a rule-based verdict labelled "Rules". The written text (summary, "how" sentences, test ideas) is AI-written from those facts and isn't checked line by line, which is why a reviewer can change anything. |
| *How accurate is the impact analysis?* | On 9 test tickets against an answer key we wrote: **100%** of the parts that should be involved were found, **100%** of required approvals and outside systems, **0** parts wrongly marked "must change", and **67%** with the main change on the expected part. The rules were tuned on these same 9 tickets, so it's a sanity check, not a benchmark. |
| *Does data leave the machine?* | Not to any AI provider: the models run locally (Ollama). Jira Cloud is reached over the internet through its API with your token: tickets come in, the summary goes back as a comment. |
| *Did you train a model?* | No training. It uses existing open models with retrieval, structured prompts and checks. |
| *Will it work on our codebase?* | Today it reads Python (Flask) and Java (Spring) services deployed with Kubernetes. Other stacks need a new parser that produces the same facts; the rest of the app stays the same. Owners, outside systems and rules would be imported from existing registers (CMDB, interface catalogue, data register, change policy). |
| *Why was it fast in the demo?* | The AI answers for BOA-9 were computed earlier (about 14 minutes with the 7B model on a laptop CPU) and cached. On a GPU server a fresh analysis would take seconds to a minute. |
| *What's real?* | The code (Google's open-source Bank of Anthos), the map, Jira Cloud and the AI are real. The tickets, owners, outside systems and rules are demo data. |

---

## 6. Ten-second glossary
| Term | Plain meaning |
|---|---|
| **Change request (CR)** | A Jira ticket asking for a change |
| **Service** | One program in the system (e.g. *ledgerwriter* records payments) |
| **API / endpoint** | A door into a service (e.g. `POST /transactions` = "record a payment") |
| **Outside system** | A system we don't own but which uses our data (e.g. Regulatory Reporting) |
| **Must change / Likely affected / Re-test only** | Must be edited / probably needs a look / no edit, but test it again |
| **Approval rule (control)** | A company rule: "if a change touches X, Y must approve" |
| **Dependency map** | The picture of what talks to what, built from the code |
| **Evidence / proof** | The exact code or config lines behind a claim |
| **Local AI** | AI models running on this laptop, not in the cloud |
