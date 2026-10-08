# Change Impact Copilot

A local AI assistant that answers, **before any code is written**:

> **"If we make this Jira change, what will it affect, how, and who needs to be involved?"**

It runs on a real open-source banking app ([Bank of Anthos](https://github.com/GoogleCloudPlatform/bank-of-anthos)) and gives you:
- **Impact Analysis of a Jira CR:** what must change, what's likely affected, what to re-test, HOW each part is affected, data sensitivity, outside systems, approvals, tests and gaps, people to involve, risk and size.
- **An interactive dependency map** of the whole system, built from the code and **100% accurate against a hand-checked answer key (49/49 facts, 0 wrong links)**, with the CR's impact drawn on it.

**Principles:**
- Code finds the facts, the local AI judges and explains, and code checks the AI.
- Every link and claim has proof (file and line).
- Runs fully locally with Ollama: no paid APIs, no data leaves the machine, no model training.

➡️ **Read [PROJECT_GUIDE.md](PROJECT_GUIDE.md)**: every step, every detail, and the summary, in plain language.
➡️ **Screens + demo video script: [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md)**

## Quick start (Windows / PowerShell)

```powershell
ollama pull qwen2.5:3b; ollama pull qwen2.5:7b; ollama pull nomic-embed-text
.\scripts\fetch_repo.ps1
python -m venv backend\.venv; backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..
backend\.venv\Scripts\python scripts\build_map.py        # optional: AI map enrichment (cached)
backend\.venv\Scripts\python scripts\precompute_crs.py   # optional: analyse the 9 demo CRs (cached)
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000    # terminal 1
cd frontend; npm run dev                                                 # terminal 2 -> http://localhost:5173
```
