# **referral system**

this project implements a referral-based fee-sharing engine similar to what centralized exchanges use:
each spot trade generates a fee, and that fee is split into cashback, multi-level commissions (L1/L2/L3), and treasury revenue.
all splits are journaled, aggregated, and exposed via clean HTTP APIs.


---

## **1. requirements**

* Python **3.10+**
* PostgreSQL **14+**
* `pip` / `venv`
* **FastAPI** + **Uvicorn** (installed via requirements)

---

## **2. installation**

clone the repo:

```bash
git clone https://github.com/itsknk/referral_system_assesment.git
cd referral_system_assesment
```

create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## **3. database setup**

start PostgreSQL and create your DB:

```bash
createdb nika
```

run the schema and seed files:

```bash
psql nika < db/schema.sql
psql nika < db/seed.sql
```

verify the seed users:

```sql
SELECT id, username, referral_code FROM users;
```

you should see:

```
A, B, C, D, treasury
```

---

## **4. running the API**

launch FastAPI with uvicorn:

```bash
uvicorn app:app --reload
```

your local server is now running at:

```
http://localhost:8000
```

---

## **5. testing the system manually (postman / cURL)**

below are minimal examples for each API.

---

### **5.1 register a referral**

attach user **child_user_id** under the parent who owns `referral_code`.

```http
POST /api/referral/register
Content-Type: application/json

{
  "child_user_id": 3,
  "referral_code": "REF_A"
}
```

expected: `{"child":3,"parent":1}`

---

### **5.2 generate or fetch referral code**

```http
POST /api/referral/generate
Content-Type: application/json

{
  "user_id": 5
}
```

---

### **5.3 ingest a trade**

```http
POST /api/webhook/trade
Content-Type: application/json

{
  "trade_id": "T1001",
  "trader_id": 4,
  "chain": "arbitrum",
  "fee_token": "USDC",
  "fee_amount": "200.000000",
  "executed_at": "2025-01-15T10:00:00Z"
}
```

response includes lineage & the full fee split.

---

### **5.4 view downline referral network**

```http
GET /api/referral/network?user_id=1&max_levels=3&limit_per_level=50
```

shows Level 1 → Level 3 downline users.

---

### **5.5 get earnings (no filters)**

```http
GET /api/referral/earnings?user_id=4
```

---

### **5.6 get earnings with date range (journal mode)**

```http
GET /api/referral/earnings?user_id=4&from=2025-01-01T00:00:00&to=2025-02-01T00:00:00
```

---

### **5.7 UI-Only Claim Validation**

does **not** modify balances. simply checks claimable amount.

```http
POST /api/referral/claim
Content-Type: application/json

{
  "user_id": 4,
  "token": "USDC"
}
```

---

### **5.8 execute a claim**

real claim processing.

```http
POST api/referral/claim/execute
Content-Type: application/json

{
  "user_id": 4,
  "token": "USDC"
}
```

---

## **NEW ADDITION: TESTING VIA FRONTEND**

along with the backend api running, navigate to the fronend directory and run spin up the frontend 
```
cd frontend
python3 -m http.server 5500
```

now navigate to `http://localhost:5500/index.html` and Set the API base URL at the top of the page (default: http://localhost:8000) and use the forms to:

- generate referral codes

- register referrals

- submit trades

- view referral network

- view earnings (with optional date range + breakdown)

- validate claimable rewards (UI-only)

## **6. running the automated test suite**

execute all unit + integration tests:

```bash
python -m pytest -q
```

you will see tests covering:

* fee engine
* referral engine
* trade processor
* DB-powered lineage
* end-to-end API flow

---


## **7. project structure**

```
.
├── app.py                 # FastAPI application
├── fee_engine.py          # deterministic split logic
├── referral_engine.py     # in-memory model for early tests
├── trade_engine_db.py     # transactional DB trade processor
├── db/
│   ├── db.py              # Postgres pool
│   ├── repositories.py    # lineage, ledger, entries
│   ├── schema.sql
│   ├── seed.sql
├── tests/
│   ├── test_app.py
│   ├── test_fee_engine.py
│   ├── test_referral_db.py
│   └── test_trade_engine_db.py
└── README.md
```

---

## **8. troubleshooting**

**“duplicate” response on trade ingestion**
→ the trade was already processed. this is expected idempotency behavior.

**postman shows “Invalid HTTP request received”**
→ make sure you’re using `http://localhost:8000` — not `https://`.

**referencing missing users**
→ confirm your DB is freshly seeded.

---

## **add-ons**

### **1. real claim processing** [DONE]

what “real claim processing” means in this system,

currently:

* `accrual_entries` is our journal of every fee split.
* `accrual_ledger` has `accrued_amount` and `claimed_amount` per `(user_id, kind, token)`.
* `/api/referral/claim` just calculates “unclaimed = accrued − claimed” and returns it; it doesn’t mutate anything.

instead “real claim processing” should do three things inside a single DB transaction:

1. **lock the relevant ledger rows for a user+token** so two concurrent claims can’t both spend the same unclaimed balance.
2. **move unclaimed into claimed** by updating `claimed_amount` for the applicable kinds.
3. **record a payout batch** so an off-chain/on-chain payment system knows how much to actually send.

can keep this simple: a single row per claim in `payout_batches`, representing “this user has requested N USDC out.” could later add a `payout_batch_items` table keyed to trades or ledger rows, but we don’t need that to get the core correctness.
