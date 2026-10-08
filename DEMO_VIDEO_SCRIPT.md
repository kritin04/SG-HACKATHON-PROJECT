# Demo Video Script: Change Impact Copilot (~6 min)

**Hero ticket:** BOA-9 "Collect the customer's phone number at sign-up" (starts in *To analyse*)
**Supporting tickets:** BOA-8 "Block payments to your own account", BOA-12 "Make the balance show faster"
Format: 🎬 on screen · 🖱️ do · 🎙️ say (word for word)

---

## Before every take (2 minutes)
1. Ollama running (tray icon) → start the backend and frontend:
   ```powershell
   cd backend;  .venv\Scripts\python -m uvicorn app.main:app --port 8000
   cd frontend; npm run dev
   ```
2. Reset the demo state (puts BOA-9 back in *To analyse*, clears rehearsal edits, removes copilot comments from Jira):
   ```powershell
   backend\.venv\Scripts\python scripts\reset_demo.py
   ```
3. Browser, one window, F11 full screen, zoom 100–110%:
   - **Tab 1:** Jira → Payments Platform → **Board** (refresh)
   - **Tab 2:** http://localhost:5173/board (refresh)
4. Do not disturb on; Teams and Outlook closed; recorder at 1080p with mic on.

---

## Scene 1: Title (0:00–0:10)
🎬 Title card: **"Change Impact Copilot: know what a change will affect, before writing a line of code."**

## Scene 2: The problem (0:10–0:40)
🎬 Jira board. 🖱️ Slowly scroll the To Do column.
🎙️ *"Every software change starts as a ticket like these. Before anyone writes code, someone has to answer a hard question: what will this change affect? Which systems, which customer data, which other teams, which approvals? Today that takes developers, leads, testers and analysts hours of meetings and code reading, and things still get missed. Those misses become incidents, rework and delays."*

## Scene 3: The ticket (0:40–1:00)
🎬 Jira → open **BOA-9**. 🖱️ Point at the description, then the acceptance criteria.
🎙️ *"Here's a simple-sounding request: collect the customer's phone number when they sign up. It's required, it's stored with their profile, and existing customers aren't forced to add one. Let's see what it really affects."*

## Scene 4: Tickets flow into the Copilot (1:00–1:25)
🎬 Copilot board (tab 2). 🖱️ Point at **Connected to Jira**, click **Sync from Jira**, point at "Synced 9 issue(s)".
🎙️ *"This is the Change Impact Copilot. It connects to Jira through Jira's official API and pulls in the change requests. Everything you're about to see runs on this laptop, including the AI. No code or data is sent to the cloud."*

## Scene 5: Run the analysis (1:25–2:00)
🎬 BOA-9 card in **To analyse**. 🖱️ Click **✨ Analyse impact**. The card moves to **Analysing** and shows the steps (about 5 seconds; the AI's answers were prepared earlier, while a full fresh run on a laptop CPU takes several minutes).
🎙️ *"Each ticket goes through six steps. First, a local AI reads the request and works out what it really means. Then the Copilot finds where the change starts in the code, follows a verified map of how the whole system connects, and the AI judges every part it reaches: must change, likely affected, or just needs re-testing. Rules then check sensitive data, outside systems, approvals and tests, and the AI writes a plain-English summary."*
🖱️ When the card moves to **Analysed**, click **Open analysis →**.

## Scene 6: The answer at a glance (2:00–2:50)
🎬 BOA-9 Impact page. 🖱️ Point at **High risk · Size M**, read the summary, then point at the six cards.
🎙️ *"In ten seconds, a manager has the answer. High risk, medium size. Three parts of the system must change, and two more are likely affected. The change touches personal data, so a privacy review is required. Two systems outside our code, the customer relationship system and regulatory reporting, read customer data, so those teams must be told and regulatory reporting must sign off. And it lists ten existing tests to re-run, plus two gaps where nothing is tested today."*

## Scene 7: Questions nobody asked yet (2:50–3:10)
🎬 Yellow box **Questions to answer before development**.
🎙️ *"It also spots what the ticket doesn't say. How will the phone number be validated? Is there a required format? What happens if it's missing? These questions usually come up halfway through development. Here, they're raised on day one."*

## Scene 8: What changes, and how, with proof (3:10–4:00)
🎬 **What changes, and how**. 🖱️ Point at **POST /signup** (must change), read its sentence, click **Why?** (path + code with line numbers), then close.
🎙️ *"For engineers, every item says exactly how it's affected. And every claim has proof. 'Why' shows the path through the system and the exact lines of real code it's based on. The AI is only allowed to judge parts found on a verified map, and every answer is checked by code. If something can't be proven, it's marked as a rule-based result, not passed off as AI."*
🖱️ On **userservice** (likely affected), change the verdict to **Must change** → point at the **Reviewer** badge and "(AI said: Likely affected)".
🎙️ *"And people stay in control. A lead can change any verdict, remove items or add missing ones, and every change is recorded."*

## Scene 9: The impact on the map (4:00–4:50)
🎬 🖱️ Click **Show on map**. Hover **userservice**, then hover the line to the customer relationship system.
🎙️ *"Here's the whole application on one screen: the website, the services behind it, the databases, and the systems outside our code. The map is built automatically from the source code, and we verified it against a hand-checked list of every dependency: forty-nine out of forty-nine correct. Red shows what must change for this ticket; yellow shows what needs re-testing."*
🖱️ **Data** view → point at the red **users** table.
🎙️ *"Sensitive data is highlighted, with every system that reads or writes it."*
🖱️ **System** view → click **ledgerwriter** → **What if this changes?**
🎙️ *"Anyone can also ask 'what if this changes?' and instantly see the knock-on effects."*

## Scene 10: Customer journeys (4:50–5:10)
🎬 🖱️ **Customer journeys** → **Make a payment**.
🎙️ *"Business users can follow exactly what happens when a customer sends money: save the payee, check there's enough balance, record the payment. Step by step, straight from the code."*

## Scene 11: Proportionate (5:10–5:35)
🎬 🖱️ Board → point at **BOA-8 (Medium risk)** → open **BOA-12** → questions box.
🎙️ *"It's also proportionate. Blocking payments to your own account is a small rule change, so it's rated medium, with only the payments sign-off. And when a ticket is vague, like 'make the balance show faster', it's rated low and asks the right questions: how much faster, and what's today's baseline? It pushes back before effort is wasted."*

## Scene 12: Back into Jira (5:35–6:00)
🎬 🖱️ Open BOA-9 → **Post summary to Jira** → Jira tab → refresh BOA-9 → scroll to the comment.
🎙️ *"Finally, the summary goes straight back into Jira, where the team already works: risk, what changes, who to involve, open questions, and a link to the full evidence."*

## Scene 13: Close (6:00–6:20)
🎬 Board, then end card: **"Change Impact Copilot · Local AI · Proof for every claim · Works with Jira"**
🎙️ *"Impact analysis in minutes instead of hours. Fewer surprises in delivery. Proof for every claim. And it runs privately on a laptop, ready to work on any multi-service codebase. Thank you."*

---

## Tips
- Record scene by scene and join the clips in Clipchamp.
- Pause a second after each click; move the mouse slowly.
- If something goes wrong, run `scripts\reset_demo.py`, refresh both tabs and redo the scene.
