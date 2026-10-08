"""Generate the synthetic NovaBank demo repository with scripted git history.

Domain content lives only here and in demo_data/*. The engine is domain-agnostic.

History (deterministic dates/authors so SHAs are stable):
  C1  v1.0      initial platform (payments, ledger, customer, reporting, docs, tests)
  C2  PAY-120   SMS notification on transfer completion (docs updated - clean)
  C3  PAY-131   channel-based fee pricing: renames calculate_fee, renames response field,
                adds FEE_RATE_MOBILE - docs NOT updated (stale + missing docs)
  C4  PAY-135   daily transfer limit, adds MAX_DAILY_LIMIT - docs NOT updated (missing doc)
  feature/PAY-142-crossborder-fee (PR #57, 2 commits on top of C4):
                cross-border fee + fx_markup in ledger; also reads a PII column (surprise);
                does not touch reporting/extract.py (miss); one new test only.

Tags pr-<n>-base / pr-<n>-head mark PR ranges.

Usage: python demo_data/generate_repo.py [target_dir]
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT / "workspace" / "demo_repo"

PEOPLE = {
    "priya.nair": "Priya Nair",
    "arjun.k": "Arjun Kumar",
    "wei.chen": "Wei Chen",
    "sara.ong": "Sara Ong",
}


def _t(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


# --------------------------------------------------------------------------- C1
C1 = {
    "README.md": _t("""
        # NovaBank Payments Platform (synthetic demo)

        Services: payments_service, ledger_service, customer_service, reporting.
        All data in this repository is synthetic.
        """),
    "CODEOWNERS": _t("""
        /payments_service/ @payments-team
        /ledger_service/ @ledger-team
        /customer_service/ @customer-team
        /notification_service/ @notifications-team
        /reporting/ @regreport-team
        /migrations/ @ledger-team
        /docs/ @tech-writers
        """),
    "shared/__init__.py": "",
    "shared/settings.py": _t('''
        """Central configuration access for NovaBank services."""
        import os

        DEFAULTS = {
            "FEE_RATE_DOMESTIC": "0.002",
            "FEE_MIN_SGD": "0.50",
            "LEDGER_TIMEOUT_SECONDS": "5",
        }


        def get(key, default=None):
            return os.getenv(key, DEFAULTS.get(key, default))
        '''),
    "shared/db.py": _t('''
        """Thin database helper (synthetic, in-memory)."""
        _ROWS = []


        def execute(sql, params=()):
            _ROWS.append((sql, params))
            return len(_ROWS)


        def query(sql, params=()):
            return []
        '''),
    "shared/bus.py": _t('''
        """In-process event bus."""
        _HANDLERS = {}


        def publish(topic, payload):
            for handler in _HANDLERS.get(topic, []):
                handler(payload)


        def subscribe(topic):
            def register(fn):
                _HANDLERS.setdefault(topic, []).append(fn)
                return fn
            return register
        '''),
    "shared/http.py": _t('''
        """Service-to-service HTTP client (synthetic)."""
        SENT = []


        def post(url, payload, timeout=5):
            SENT.append((url, payload, timeout))
            return {"ok": True}


        def get(url, timeout=5):
            return {"ok": True}
        '''),
    "shared/web.py": _t('''
        """Minimal route registry used by every service API."""


        class Router:
            def __init__(self):
                self.routes = {}

            def _add(self, method, path):
                def register(fn):
                    self.routes[(method, path)] = fn
                    return fn
                return register

            def get(self, path):
                return self._add("GET", path)

            def post(self, path):
                return self._add("POST", path)


        router = Router()
        '''),
    "payments_service/__init__.py": "",
    "payments_service/fees.py": _t('''
        """Transfer fee calculation."""
        from shared import settings


        def calculate_fee(amount, currency):
            """Return the fee for a domestic transfer, never below the minimum fee."""
            rate = float(settings.get("FEE_RATE_DOMESTIC"))
            minimum = float(settings.get("FEE_MIN_SGD"))
            return max(round(amount * rate, 2), minimum)
        '''),
    "payments_service/transfers.py": _t('''
        """Transfer orchestration: validate, price, persist, post to ledger, notify."""
        from shared import db, bus, http, settings
        from payments_service.fees import calculate_fee
        from customer_service.profile import get_customer


        def create_transfer(customer_id, amount, currency, beneficiary_account):
            customer = get_customer(customer_id)
            if customer is None:
                raise ValueError("unknown customer")
            fee = calculate_fee(amount, currency)
            transfer_id = db.execute(
                "INSERT INTO transfers (customer_id, amount, currency, fee, status) VALUES (?, ?, ?, ?, 'PENDING')",
                (customer_id, amount, currency, fee),
            )
            http.post(
                "http://ledger-service/entries",
                {"transfer_id": transfer_id, "account": beneficiary_account,
                 "amount": amount, "fee": fee, "currency": currency},
                timeout=float(settings.get("LEDGER_TIMEOUT_SECONDS")),
            )
            bus.publish("payments.transfer.completed",
                        {"transfer_id": transfer_id, "customer_id": customer_id, "amount": amount, "fee": fee})
            return {"transfer_id": transfer_id, "fee": fee, "status": "PENDING"}


        def get_transfer(transfer_id):
            rows = db.query("SELECT transfer_id, amount, currency, fee, status FROM transfers WHERE transfer_id = ?",
                            (transfer_id,))
            return rows[0] if rows else None
        '''),
    "payments_service/api.py": _t('''
        """Public Payments API."""
        from shared.web import router
        from payments_service.transfers import create_transfer, get_transfer
        from payments_service.fees import calculate_fee


        @router.post("/transfers")
        def post_transfer(body):
            result = create_transfer(body["customer_id"], body["amount"], body["currency"], body["beneficiary_account"])
            return {"transfer_id": result["transfer_id"], "fee": result["fee"], "status": result["status"]}


        @router.get("/transfers/{transfer_id}")
        def read_transfer(transfer_id):
            transfer = get_transfer(transfer_id)
            return {"transfer_id": transfer_id, "status": transfer["status"] if transfer else "NOT_FOUND"}


        @router.get("/fees/quote")
        def quote_fee(amount, currency):
            return {"amount": amount, "currency": currency, "fee": calculate_fee(amount, currency)}
        '''),
    "ledger_service/__init__.py": "",
    "ledger_service/ledger.py": _t('''
        """Ledger postings for every transfer."""
        from shared import db, bus


        def record_entry(transfer_id, account, amount, fee, currency):
            entry_id = db.execute(
                "INSERT INTO ledger_entries (transfer_id, account, amount, fee, currency) VALUES (?, ?, ?, ?, ?)",
                (transfer_id, account, amount, fee, currency),
            )
            bus.publish("ledger.entry.posted", {"entry_id": entry_id, "amount": amount, "fee": fee})
            return entry_id


        def get_balance(account):
            rows = db.query("SELECT SUM(amount) FROM ledger_entries WHERE account = ?", (account,))
            return rows[0] if rows else 0
        '''),
    "ledger_service/api.py": _t('''
        """Internal Ledger API."""
        from shared.web import router
        from ledger_service.ledger import record_entry, get_balance


        @router.post("/entries")
        def post_entry(body):
            entry_id = record_entry(body["transfer_id"], body["account"], body["amount"], body["fee"], body["currency"])
            return {"entry_id": entry_id}


        @router.get("/accounts/{account}/balance")
        def read_balance(account):
            return {"account": account, "balance": get_balance(account)}
        '''),
    "customer_service/__init__.py": "",
    "customer_service/profile.py": _t('''
        """Customer profile data (contains personal data)."""
        from shared import db


        def get_customer(customer_id):
            rows = db.query("SELECT customer_id, full_name, phone, status FROM customer_profile WHERE customer_id = ?",
                            (customer_id,))
            return rows[0] if rows else None


        def update_phone(customer_id, phone):
            return db.execute("UPDATE customer_profile SET phone = ? WHERE customer_id = ?", (phone, customer_id))
        '''),
    "reporting/__init__.py": "",
    "reporting/extract.py": _t('''
        """Daily regulatory extract of transfers and fees, sent to the Regulatory Reporting Hub."""
        from shared import db


        def build_daily_extract(business_date):
            rows = db.query(
                "SELECT entry_id, transfer_id, amount, fee, currency FROM ledger_entries WHERE posted_date = ?",
                (business_date,),
            )
            return [format_row(row) for row in rows]


        def format_row(row):
            return ",".join(str(value) for value in row)
        '''),
    "migrations/001_init.sql": _t("""
        CREATE TABLE customer_profile (customer_id TEXT PRIMARY KEY, full_name TEXT, id_number TEXT,
            phone TEXT, residency_country TEXT, status TEXT);
        CREATE TABLE transfers (transfer_id INTEGER PRIMARY KEY, customer_id TEXT, amount NUMERIC(18,2),
            currency TEXT, fee NUMERIC(18,2), status TEXT);
        CREATE TABLE ledger_entries (entry_id INTEGER PRIMARY KEY, transfer_id INTEGER, account TEXT,
            amount NUMERIC(18,2), fee NUMERIC(18,2), currency TEXT, posted_date DATE);
        """),
    "tests/__init__.py": "",
    "tests/test_fees.py": _t('''
        from payments_service.fees import calculate_fee


        def test_minimum_fee_applies():
            assert calculate_fee(10, "SGD") == 0.50


        def test_domestic_rate():
            assert calculate_fee(1000, "SGD") == 2.0
        '''),
    "tests/test_transfers.py": _t('''
        from payments_service.transfers import create_transfer


        def test_create_transfer_is_pending(monkeypatch):
            monkeypatch.setattr("payments_service.transfers.get_customer", lambda cid: {"customer_id": cid})
            result = create_transfer("C1", 100, "SGD", "ACC-9")
            assert result["status"] == "PENDING"
        '''),
    "tests/test_ledger.py": _t('''
        from ledger_service.ledger import record_entry, get_balance


        def test_record_entry_returns_id():
            assert record_entry(1, "ACC-1", 100, 0.5, "SGD") > 0


        def test_balance_defaults_to_zero():
            assert get_balance("ACC-404") == 0
        '''),
    "docs/fees.md": _t("""
        # Fee Calculation

        ## How fees are calculated

        Transfer fees are calculated by `calculate_fee(amount, currency)` in the Payments Service.
        The fee is the amount multiplied by `FEE_RATE_DOMESTIC`, but never lower than `FEE_MIN_SGD`.

        ## Examples

        | Amount (SGD) | Fee (SGD) |
        |---|---|
        | 10 | 0.50 (minimum) |
        | 1,000 | 2.00 |
        """),
    "docs/payments_api.md": _t("""
        # Payments API

        ## POST /transfers

        Creates a transfer, posts it to the ledger and emits `payments.transfer.completed`.

        Request body: `customer_id`, `amount`, `currency`, `beneficiary_account`.

        Response: `transfer_id`, `fee`, `status`.

        ## GET /transfers/{transfer_id}

        Returns the transfer status: `transfer_id`, `status`.

        ## GET /fees/quote

        Returns a fee quote for an amount: `amount`, `currency`, `fee`.
        """),
    "docs/ledger.md": _t("""
        # Ledger Service

        ## Posting entries

        The Payments Service calls `POST /entries`, handled by `record_entry`, which writes to
        `ledger_entries` and publishes `ledger.entry.posted` for the Finance General Ledger.

        ## Balances

        `GET /accounts/{account}/balance` returns the sum of `ledger_entries` for an account.
        """),
    "docs/reporting.md": _t("""
        # Regulatory Reporting Extract

        ## Daily extract

        `build_daily_extract` reads `ledger_entries` and produces the daily file sent to the
        Regulatory Reporting Hub. Columns: `entry_id`, `transfer_id`, `amount`, `fee`, `currency`.
        """),
    "docs/config.md": _t("""
        # Configuration

        ## Configuration keys

        | Key | Default | Description |
        |---|---|---|
        | `FEE_RATE_DOMESTIC` | 0.002 | Domestic transfer fee rate |
        | `FEE_MIN_SGD` | 0.50 | Minimum fee in SGD |
        | `LEDGER_TIMEOUT_SECONDS` | 5 | Timeout for ledger calls |
        """),
}

# --------------------------------------------------------------------------- C2 PAY-120
C2 = {
    "notification_service/__init__.py": "",
    "notification_service/sms.py": _t('''
        """SMS gateway adapter (synthetic)."""


        def send_sms(customer_id, message):
            return {"customer_id": customer_id, "message": message, "channel": "SMS"}
        '''),
    "notification_service/consumer.py": _t('''
        """Customer notifications for payment events."""
        from shared import bus
        from notification_service.sms import send_sms


        @bus.subscribe("payments.transfer.completed")
        def on_transfer_completed(event):
            return send_sms(event["customer_id"], f"Your transfer {event['transfer_id']} is complete.")
        '''),
    "tests/test_notifications.py": _t('''
        from notification_service.consumer import on_transfer_completed


        def test_sms_sent_on_completion():
            result = on_transfer_completed({"customer_id": "C1", "transfer_id": 7})
            assert result["channel"] == "SMS"
        '''),
    "docs/notifications.md": _t("""
        # Customer Notifications

        ## Transfer completed SMS

        `on_transfer_completed` listens to `payments.transfer.completed` and sends an SMS to the
        customer via `send_sms`.
        """),
}

# --------------------------------------------------------------------------- C3 PAY-131 (no doc updates)
C3 = {
    "shared/settings.py": C1["shared/settings.py"].replace(
        '"FEE_MIN_SGD": "0.50",\n', '"FEE_MIN_SGD": "0.50",\n    "FEE_RATE_MOBILE": "0.001",\n'),
    "payments_service/fees.py": _t('''
        """Transfer fee calculation."""
        from shared import settings


        def compute_transfer_fee(amount, currency, channel="BRANCH"):
            """Return the fee for a domestic transfer; mobile transfers use a discounted rate."""
            if channel == "MOBILE":
                rate = float(settings.get("FEE_RATE_MOBILE"))
            else:
                rate = float(settings.get("FEE_RATE_DOMESTIC"))
            minimum = float(settings.get("FEE_MIN_SGD"))
            return max(round(amount * rate, 2), minimum)
        '''),
    "payments_service/transfers.py": C1["payments_service/transfers.py"]
        .replace("from payments_service.fees import calculate_fee", "from payments_service.fees import compute_transfer_fee")
        .replace("def create_transfer(customer_id, amount, currency, beneficiary_account):",
                 'def create_transfer(customer_id, amount, currency, beneficiary_account, channel="BRANCH"):')
        .replace("fee = calculate_fee(amount, currency)", "fee = compute_transfer_fee(amount, currency, channel)"),
    "payments_service/api.py": _t('''
        """Public Payments API."""
        from shared.web import router
        from payments_service.transfers import create_transfer, get_transfer
        from payments_service.fees import compute_transfer_fee


        @router.post("/transfers")
        def post_transfer(body):
            result = create_transfer(body["customer_id"], body["amount"], body["currency"],
                                     body["beneficiary_account"], body.get("channel", "BRANCH"))
            return {"transfer_id": result["transfer_id"], "fee_amount": result["fee"], "status": result["status"]}


        @router.get("/transfers/{transfer_id}")
        def read_transfer(transfer_id):
            transfer = get_transfer(transfer_id)
            return {"transfer_id": transfer_id, "status": transfer["status"] if transfer else "NOT_FOUND"}


        @router.get("/fees/quote")
        def quote_fee(amount, currency, channel="BRANCH"):
            return {"amount": amount, "currency": currency, "fee": compute_transfer_fee(amount, currency, channel)}
        '''),
    "tests/test_fees.py": _t('''
        from payments_service.fees import compute_transfer_fee


        def test_minimum_fee_applies():
            assert compute_transfer_fee(10, "SGD") == 0.50


        def test_domestic_rate():
            assert compute_transfer_fee(1000, "SGD") == 2.0


        def test_mobile_rate_is_discounted():
            assert compute_transfer_fee(1000, "SGD", "MOBILE") == 1.0
        '''),
}

# --------------------------------------------------------------------------- C4 PAY-135 (no doc updates)
_c4_transfers = C3["payments_service/transfers.py"].replace(
    '''    fee = compute_transfer_fee(amount, currency, channel)''',
    '''    if amount > float(settings.get("MAX_DAILY_LIMIT")):
        raise ValueError("daily transfer limit exceeded")
    fee = compute_transfer_fee(amount, currency, channel)''')
C4 = {
    "shared/settings.py": C3["shared/settings.py"].replace(
        '"LEDGER_TIMEOUT_SECONDS": "5",\n', '"LEDGER_TIMEOUT_SECONDS": "5",\n    "MAX_DAILY_LIMIT": "200000",\n'),
    "payments_service/transfers.py": _c4_transfers,
    "tests/test_transfers.py": C1["tests/test_transfers.py"] + _t('''


        def test_daily_limit_enforced(monkeypatch):
            import pytest
            monkeypatch.setattr("payments_service.transfers.get_customer", lambda cid: {"customer_id": cid})
            with pytest.raises(ValueError):
                create_transfer("C1", 10_000_000, "SGD", "ACC-9")
        '''),
}

# --------------------------------------------------------------------------- PR #57 (PAY-142)
P1 = {
    "shared/settings.py": C4["shared/settings.py"].replace(
        '"FEE_RATE_MOBILE": "0.001",\n',
        '"FEE_RATE_MOBILE": "0.001",\n    "FEE_RATE_CROSSBORDER": "0.005",\n    "FX_MARKUP_BPS": "30",\n'),
    "payments_service/fees.py": C3["payments_service/fees.py"] + _t('''


        def compute_crossborder_fee(amount, currency, destination_country):
            """Cross-border fee: percentage fee plus an FX markup in basis points."""
            rate = float(settings.get("FEE_RATE_CROSSBORDER"))
            markup_bps = float(settings.get("FX_MARKUP_BPS"))
            fx_markup = round(amount * markup_bps / 10000, 2)
            return {"fee": round(amount * rate, 2), "fx_markup": fx_markup}
        '''),
    "payments_service/transfers.py": _t('''
        """Transfer orchestration: validate, price, persist, post to ledger, notify."""
        from shared import db, bus, http, settings
        from payments_service.fees import compute_transfer_fee, compute_crossborder_fee
        from customer_service.profile import get_customer


        def create_transfer(customer_id, amount, currency, beneficiary_account, channel="BRANCH",
                            destination_country="SG"):
            customer = get_customer(customer_id)
            if customer is None:
                raise ValueError("unknown customer")
            if amount > float(settings.get("MAX_DAILY_LIMIT")):
                raise ValueError("daily transfer limit exceeded")
            fx_markup = 0
            if destination_country != "SG":
                breakdown = compute_crossborder_fee(amount, currency, destination_country)
                fee, fx_markup = breakdown["fee"], breakdown["fx_markup"]
            else:
                fee = compute_transfer_fee(amount, currency, channel)
            transfer_id = db.execute(
                "INSERT INTO transfers (customer_id, amount, currency, fee, status) VALUES (?, ?, ?, ?, 'PENDING')",
                (customer_id, amount, currency, fee),
            )
            http.post(
                "http://ledger-service/entries",
                {"transfer_id": transfer_id, "account": beneficiary_account, "amount": amount,
                 "fee": fee, "fx_markup": fx_markup, "currency": currency},
                timeout=float(settings.get("LEDGER_TIMEOUT_SECONDS")),
            )
            bus.publish("payments.transfer.completed",
                        {"transfer_id": transfer_id, "customer_id": customer_id, "amount": amount, "fee": fee})
            return {"transfer_id": transfer_id, "fee": fee, "fx_markup": fx_markup, "status": "PENDING"}


        def get_transfer(transfer_id):
            rows = db.query("SELECT transfer_id, amount, currency, fee, status FROM transfers WHERE transfer_id = ?",
                            (transfer_id,))
            return rows[0] if rows else None
        '''),
    "payments_service/api.py": _t('''
        """Public Payments API."""
        from shared.web import router
        from payments_service.transfers import create_transfer, get_transfer
        from payments_service.fees import compute_transfer_fee, compute_crossborder_fee


        @router.post("/transfers")
        def post_transfer(body):
            result = create_transfer(body["customer_id"], body["amount"], body["currency"],
                                     body["beneficiary_account"], body.get("channel", "BRANCH"),
                                     body.get("destination_country"))
            return {"transfer_id": result["transfer_id"], "fee_amount": result["fee"], "status": result["status"]}


        @router.get("/transfers/{transfer_id}")
        def read_transfer(transfer_id):
            transfer = get_transfer(transfer_id)
            return {"transfer_id": transfer_id, "status": transfer["status"] if transfer else "NOT_FOUND"}


        @router.get("/fees/quote")
        def quote_fee(amount, currency, channel="BRANCH", destination_country="SG"):
            if destination_country != "SG":
                breakdown = compute_crossborder_fee(amount, currency, destination_country)
                return {"amount": amount, "currency": currency, "fee": breakdown["fee"],
                        "fx_markup": breakdown["fx_markup"]}
            return {"amount": amount, "currency": currency, "fee": compute_transfer_fee(amount, currency, channel)}
        '''),
    "ledger_service/ledger.py": _t('''
        """Ledger postings for every transfer."""
        from shared import db, bus


        def record_entry(transfer_id, account, amount, fee, currency, fx_markup=0):
            entry_id = db.execute(
                "INSERT INTO ledger_entries (transfer_id, account, amount, fee, fx_markup, currency) VALUES (?, ?, ?, ?, ?, ?)",
                (transfer_id, account, amount, fee, fx_markup, currency),
            )
            bus.publish("ledger.entry.posted", {"entry_id": entry_id, "amount": amount, "fee": fee, "fx_markup": fx_markup})
            return entry_id


        def get_balance(account):
            rows = db.query("SELECT SUM(amount) FROM ledger_entries WHERE account = ?", (account,))
            return rows[0] if rows else 0
        '''),
    "ledger_service/api.py": C1["ledger_service/api.py"].replace(
        'body["fee"], body["currency"])', 'body["fee"], body["currency"],\n                            body.get("fx_markup", 0))'),
    "migrations/003_add_fx_markup.sql": "ALTER TABLE ledger_entries ADD COLUMN fx_markup NUMERIC(18,2) DEFAULT 0;\n",
    "tests/test_fees.py": C3["tests/test_fees.py"].replace(
        "from payments_service.fees import compute_transfer_fee",
        "from payments_service.fees import compute_transfer_fee, compute_crossborder_fee") + _t('''


        def test_crossborder_fee_includes_fx_markup():
            result = compute_crossborder_fee(1000, "SGD", "MY")
            assert result == {"fee": 5.0, "fx_markup": 3.0}
        '''),
}

# Second PR commit: default destination from customer residency (reads a PII column - unplanned)
P2 = {
    "customer_service/profile.py": C1["customer_service/profile.py"] + _t('''


        def get_residency_country(customer_id):
            rows = db.query("SELECT residency_country FROM customer_profile WHERE customer_id = ?", (customer_id,))
            return rows[0] if rows else "SG"
        '''),
    "payments_service/transfers.py": P1["payments_service/transfers.py"]
        .replace("from customer_service.profile import get_customer",
                 "from customer_service.profile import get_customer, get_residency_country")
        .replace('                    destination_country="SG"):', '                    destination_country=None):')
        .replace('''        raise ValueError("unknown customer")
''', '''        raise ValueError("unknown customer")
    if destination_country is None:
        destination_country = get_residency_country(customer_id)
''', 1),
}


# --------------------------------------------------------------------------- git plumbing
def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    out = subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")


def _commit(repo: Path, files: dict[str, str], message: str, author: str, date: str) -> str:
    _write(repo, files)
    _git(repo, "add", "-A")
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": PEOPLE[author], "GIT_AUTHOR_EMAIL": f"{author}@novabank.example",
        "GIT_COMMITTER_NAME": PEOPLE[author], "GIT_COMMITTER_EMAIL": f"{author}@novabank.example",
        "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date,
    })
    _git(repo, "commit", "-q", "-m", message, env=env)
    return _git(repo, "rev-parse", "HEAD")


def _rmtree(path: Path) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        shutil.rmtree(path, onerror=onerror)


def generate(target: Path = DEFAULT_TARGET) -> Path:
    _rmtree(target)
    target.mkdir(parents=True)
    _git(target, "init", "-q", "-b", "main")
    _git(target, "config", "core.autocrlf", "false")

    c1 = _commit(target, C1, "Initial NovaBank payments platform", "priya.nair", "2026-08-03T09:00:00+08:00")
    _git(target, "tag", "v1.0")
    c2 = _commit(target, C2, "PAY-120: Send SMS when a transfer completes", "sara.ong", "2026-08-20T10:00:00+08:00")
    c3 = _commit(target, C3, "PAY-131: Channel-based fee pricing (mobile discount)", "wei.chen", "2026-09-08T14:30:00+08:00")
    c4 = _commit(target, C4, "PAY-135: Enforce daily transfer limit", "arjun.k", "2026-09-22T11:15:00+08:00")
    for n, base, head in ((51, c1, c2), (52, c2, c3), (53, c3, c4)):
        _git(target, "tag", f"pr-{n}-base", base)
        _git(target, "tag", f"pr-{n}-head", head)

    _git(target, "checkout", "-q", "-b", "feature/PAY-142-crossborder-fee")
    _commit(target, P1, "PAY-142: Cross-border fee with FX markup posted to ledger", "arjun.k", "2026-10-05T16:00:00+08:00")
    p2 = _commit(target, P2, "PAY-142: Default destination country from customer residency", "arjun.k", "2026-10-06T10:20:00+08:00")
    _git(target, "tag", "pr-57-base", c4)
    _git(target, "tag", "pr-57-head", p2)
    _git(target, "checkout", "-q", "main")
    return target


if __name__ == "__main__":
    out = generate(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET)
    print(f"Demo repo generated at {out}")
    print(_git(out, "log", "--oneline", "--all", "--graph"))
