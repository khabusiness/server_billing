# Billing Verify Backend

Unified backend for Android subscription verification via Google Play Developer API.

- Domain (target): `billing.rus-bridge.ru`
- Endpoint: `POST /v1/billing/android/verify`
- Healthcheck: `GET /health`
- Stack: FastAPI + PostgreSQL (Railway)

## 1. What it does

- Validates request payload (`app_id`, `package_name`, `subscription_id`, `purchase_token`, `user_id`).
- Enforces multi-app whitelist from `APP_REGISTRY_JSON`.
- Optionally enforces `X-Client-Key` from `CLIENT_KEYS_JSON`.
- Calls Google Play API (`purchases.subscriptionsv2.get`) and maps response to:
  - `active`
  - `status` (`TRIAL_ACTIVE`, `PAID_ACTIVE`, `ON_HOLD`, `EXPIRED`, `CANCELED_ACTIVE`, `UNKNOWN`)
  - `expiry_time_ms`, `is_trial`, `auto_renewing`
- Writes audit log into `subscription_verifications`.
- Upserts current state into `entitlements`.
- Returns cached verification if same `purchase_token_hash` was checked recently.
- Applies in-memory rate limits by IP / user / token hash.

## 2. Environment variables

Copy `.env.example` and set values:

- `DATABASE_URL`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `APP_REGISTRY_JSON`
- `CLIENT_KEYS_JSON` (optional but recommended)
- `PURCHASE_TOKEN_HASH_PEPPER`

`GOOGLE_SERVICE_ACCOUNT_JSON` supports:
- raw JSON
- file path to JSON
- base64 encoded JSON

`CLIENT_KEYS_JSON` supports values in formats:
- `sha256:<hex>` (recommended)
- `plain:<value>` (temporary migration mode)
- `<value>` (legacy plain mode)

Hash example for a client key:

```bash
python -c "import hashlib; print(hashlib.sha256(b'your-client-key').hexdigest())"
```

Generate `CLIENT_KEYS_JSON` automatically:

```bash
python scripts/generate_client_keys_json.py \
  --pair talktype=my-secret-key-1 \
  --pair live_captions=my-secret-key-2 \
  --pretty
```

From file (`keys.txt`, each line `app_id=plain_key`):

```bash
python scripts/generate_client_keys_json.py --pairs-file keys.txt --pretty
```

Generate random keys and JSON in one shot:

```bash
python scripts/generate_client_keys_json.py \
  --generate talktype \
  --generate live_captions \
  --generate srt_studio \
  --pretty
```

## 3. Local run

```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 4. Database schema

Migration SQL is in:
- `migrations/001_init.sql`

Tables:
- `subscription_verifications` (audit)
- `entitlements` (current state)

## 5. API Example

Request:

```bash
curl -X POST http://localhost:8000/v1/billing/android/verify \
  -H "Content-Type: application/json" \
  -H "X-Client-Key: change-me-talktype" \
  -d '{
    "app_id":"talktype",
    "package_name":"com.company.talktype",
    "subscription_id":"pro_monthly",
    "purchase_token":"xxxxx_xxxxxxxxxxxxxxxxxxxxx",
    "user_id":"uuid-installation"
  }'
```

Success response:

```json
{
  "active": true,
  "status": "TRIAL_ACTIVE",
  "is_trial": true,
  "auto_renewing": true,
  "expiry_time_ms": 1730000000000,
  "app_id": "talktype",
  "package_name": "com.company.talktype",
  "subscription_id": "pro_monthly"
}
```

## 6. Railway deploy

1. Create service from this repository.
2. Attach PostgreSQL in Railway.
3. Set variables from `.env.example`.
4. Apply `migrations/001_init.sql` to the Railway Postgres.
5. Railway will run command from `railway.json` / `Procfile`.
6. Add custom domain `billing.rus-bridge.ru`.

## 7. Notes

- The service never logs raw `purchase_token`.
- `purchase_token_hash` uses HMAC-SHA256 with `PURCHASE_TOKEN_HASH_PEPPER`.
- For strict production limits across multiple instances, move rate limit and cache to Redis.
